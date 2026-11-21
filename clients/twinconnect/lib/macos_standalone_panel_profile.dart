import 'dart:convert';

import 'protocols.dart';
import 'singbox_macos_config.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';

/// Authenticated panel -> unsigned local SOCKS test profile.
///
/// This deliberately bypasses the *full-tunnel* NetworkExtension capability
/// gate only for profile preparation. It never starts a VPN or marks a
/// connection as successful. Credentials stay in memory until handed to
/// an explicitly permitted local execution backend.
class MacStandalonePanelProfile {
  const MacStandalonePanelProfile({required this.api});

  final TenantApi api;

  static const supportedCodes = <String>{
    'hysteria2', 'tuic', 'anytls', 'naive', 'snell', 'socks5',
  };

  /// Always retrieve current entitlements, node list and credentials from the
  /// owning panel. Never use UI cache as a security gate for a connect attempt.
  Future<MacStandalonePreparedProfile> prepare({
    required PanelDirectoryEntry panel,
    required String sessionToken,
    required String serverId,
    required String protocolCode,
    required bool engineInstalled,
    int localPort = 10808,
  }) async {
    if (sessionToken.trim() != sessionToken || sessionToken.length < 40) {
      throw const FormatException('INVALID_APP_SESSION');
    }
    if (!supportedCodes.contains(protocolCode)) {
      throw const FormatException('MAC_STANDALONE_ENGINE_NOT_INTEGRATED');
    }
    if (!engineInstalled) {
      throw const FormatException('MAC_STANDALONE_ENGINE_NOT_INSTALLED');
    }
    if (localPort < 1024 || localPort > 65535) {
      throw const FormatException('MAC_STANDALONE_LOCAL_PORT_INVALID');
    }
    final definition = VpnProtocols.byCode(protocolCode);
    if (definition == null) {
      throw const FormatException('UNKNOWN_PROTOCOL');
    }

    final catalog = await api.loadSessionProtocolCatalog(
      panel: panel, sessionToken: sessionToken);
    if (catalog.namespace != panel.namespace ||
        catalog.entries.where((entry) =>
            entry.protocol.code == protocolCode &&
            entry.selected && entry.configRecordPresent).length != 1) {
      throw const FormatException('MAC_STANDALONE_PROTOCOL_NOT_ALLOWED');
    }

    final inventory = await api.refreshSessionServers(
      panel: panel, sessionToken: sessionToken);
    if (inventory.namespace != panel.namespace ||
        inventory.servers.where((node) => node.id == serverId).length != 1) {
      throw const FormatException('MAC_STANDALONE_SERVER_NOT_ALLOWED');
    }

    // Allow only the one protocol confirmed by the just-fetched catalog.
    // This is distinct from claiming an installed full-TUN engine.
    final profiles = await api.loadSessionNativeProfiles(
      panel: panel,
      sessionToken: sessionToken,
      protocol: definition,
      native: NativeProtocolReadiness(supportedCodes: {protocolCode}),
    );
    if (profiles.namespace != panel.namespace ||
        profiles.protocol.code != protocolCode) {
      throw const FormatException('MAC_STANDALONE_PROFILE_SCOPE_MISMATCH');
    }
    final items = profiles.items.where((item) =>
        item['node_id']?.toString() == serverId).toList(growable: false);
    if (items.length != 1) {
      // Inbound variants and multi-hop protocols must have a separate,
      // explicit selection policy before launching any traffic.
      throw const FormatException('MAC_STANDALONE_PROFILE_AMBIGUOUS');
    }
    final config = buildLocalProxy(
      protocolCode: protocolCode, item: items.single, localPort: localPort);
    return MacStandalonePreparedProfile(
      serverId: serverId, protocolCode: protocolCode, localPort: localPort,
      configJson: jsonEncode(config),
    );
  }

  /// Pure config conversion used for unit tests; TLS and credentials are
  /// validated by the existing native sing-box profile composer.
  static Map<String, dynamic> buildLocalProxy({
    required String protocolCode,
    required Map<String, dynamic> item,
    required int localPort,
  }) {
    if (!supportedCodes.contains(protocolCode)) {
      throw const FormatException('MAC_STANDALONE_ENGINE_NOT_INTEGRATED');
    }
    if (localPort < 1024 || localPort > 65535) {
      throw const FormatException('MAC_STANDALONE_LOCAL_PORT_INVALID');
    }

    final signedTunnelConfig = switch (protocolCode) {
      'hysteria2' => SingBoxMacConfig.composeHysteria2(item: item),
      'tuic' => SingBoxMacConfig.composeTuic(item: item),
      'anytls' => SingBoxMacConfig.composeAnyTls(item: item),
      'naive' => SingBoxMacConfig.composeNaive(item: item),
      'snell' => SingBoxMacConfig.composeSnell(item: item),
      'socks5' => SingBoxMacConfig.composeSocks5(item: item),
      _ => throw const FormatException('MAC_STANDALONE_ENGINE_NOT_INTEGRATED'),
    };

    final outboundRows = signedTunnelConfig['outbounds'];
    if (outboundRows is! List || outboundRows.length != 1 ||
        outboundRows.first is! Map) {
      throw const FormatException('MAC_STANDALONE_OUTBOUND_MISSING');
    }
    // Reuse the reviewed outbound exactly; never send TUN, DNS routing or
    // signed-extension settings to a standalone executable.
    final outbound = Map<String, dynamic>.from(outboundRows.first as Map);
    if (outbound['tag'] != 'proxy') {
      throw const FormatException('MAC_STANDALONE_OUTBOUND_TAG_INVALID');
    }
    return <String, dynamic>{
      'log': {'level': 'error'},
      'inbounds': [
        {'type': 'mixed', 'tag': 'local-proxy', 'listen': '127.0.0.1',
         'listen_port': localPort}
      ],
      'outbounds': [outbound],
      'route': {'final': 'proxy'},
    };
  }
}

/// Secret-bearing connection test input. Never persist or log configJson.
class MacStandalonePreparedProfile {
  const MacStandalonePreparedProfile({
    required this.serverId,
    required this.protocolCode,
    required this.localPort,
    required this.configJson,
  });
  final String serverId;
  final String protocolCode;
  final int localPort;
  final String configJson;
}
