import 'dart:async' show TimeoutException;

import 'emergency_connection_cache.dart';
import 'protocols.dart';
import 'server_inventory.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';
import 'vpn_policy.dart';
import 'native_vpn_bridge.dart';
import 'singbox_profile_validator.dart';
import 'cisco_openconnect_profile.dart';

/// A validated, subscription-scoped connection candidate. These checks do
/// not start a VPN tunnel and must never be shown as "connected".
class ConnectionBootstrap {
  const ConnectionBootstrap({required this.api,
      this.emergency = const EmergencyConnectionCache()});

  final TenantApi api;
  final EmergencyConnectionCache emergency;

  /// Fail closed before fetching any credential-bearing profile.
  /// This intentionally re-reads entitlements immediately before a connect
  /// attempt; a cached UI selection is not authorization.
  Future<ConnectionCandidate> prepare({
    required PanelDirectoryEntry panel,
    required String sessionToken,
    String? username,
    required String serverId,
    required String protocolCode,
    required VpnPolicy policy,
    required NativeVpnCapabilities capabilities,
    required NativeProtocolReadiness nativeProtocols,
    // A new authenticated catalog read issued DURING this same connect
    // attempt may overlap local native checks. Never pass UI-cached data.
    Future<PanelProtocolCatalog>? currentAttemptCatalog,
  }) async {
    if (sessionToken.trim().length < 40 || sessionToken != sessionToken.trim()) {
      throw const ConnectionBootstrapException('INVALID_APP_SESSION');
    }
    final definition = VpnProtocols.byCode(protocolCode);
    if (definition == null || definition.code != protocolCode) {
      throw const ConnectionBootstrapException('UNKNOWN_PROTOCOL');
    }

    // Do not ask the panel for secrets if the local device is not capable
    // of applying the requested policy and supporting the exact protocol.
    try {
      NativeVpnBridge.requireProtocolSafeToConnect(
        policy, capabilities, definition, nativeProtocols);
    } on StateError {
      throw const ConnectionBootstrapException('NATIVE_ENGINE_UNAVAILABLE');
    }

    // Refresh the entitlement gate before asking for any node metadata.
    // Revoked plans must NOT cause a speculative server lookup, even when
    // such a request would not include connection secrets.
    try {
    final catalog = await (currentAttemptCatalog ??
        api.loadSessionProtocolCatalog(
          panel: panel, sessionToken: sessionToken));
    if (catalog.namespace != panel.namespace) {
      throw const ConnectionBootstrapException('PROTOCOL_CATALOG_SCOPE_MISMATCH');
    }
    final allowed = catalog.entries.where((entry) =>
        entry.protocol.code == definition.code &&
        entry.selected && entry.configRecordPresent);
    if (allowed.length != 1) {
      throw const ConnectionBootstrapException('PROTOCOL_NOT_ALLOWED');
    }

    final inventory = await api.refreshSessionServers(
      panel: panel, sessionToken: sessionToken);

    // A node-health heartbeat is advisory and is not proof the VPN endpoint
    // works or fails. Authorization comes from this subscription-scoped
    // inventory; the native peer handshake determines real connectivity.
    final selected = inventory.servers.where((server) =>
        server.id == serverId);
    if (selected.length != 1) {
      throw const ConnectionBootstrapException('SERVER_NOT_AVAILABLE');
    }

    // Profiles are sensitive, never persist or log this object. They are
    // fetched only after all local and panel-side gates have passed.
    final profiles = await api.loadSessionNativeProfiles(
      panel: panel, sessionToken: sessionToken,
      protocol: definition, native: nativeProtocols);

    if (profiles.namespace != panel.namespace ||
        profiles.protocol.code != definition.code) {
      throw const ConnectionBootstrapException('PROFILE_SCOPE_MISMATCH');
    }

    // Never pass the complete subscription profile bundle to a native
    // adapter that is connecting to only one selected node.
    final nodeItems = profiles.items.where((item) {
      final id = item['node_id'];
      return (id is int && id.toString() == serverId) ||
          (id is String && id == serverId);
    }).toList(growable: false);
    if (nodeItems.isEmpty) {
      throw const ConnectionBootstrapException('SERVER_PROFILE_MISSING');
    }
    if (definition.code == 'cisco') {
      // Never pass an incomplete manual-credential profile into the native
      // OpenConnect transport once that engine becomes available.
      for (final item in nodeItems) {
        try {
          CiscoOpenConnectProfile.fromItem(item);
        } on FormatException {
          throw const ConnectionBootstrapException(
              'CISCO_PROFILE_NOT_NATIVE_READY');
        }
      }
    }
    if (SingBoxProfileValidator.supportsFamily(definition.code)) {
      // Do not attempt a mixed-engine or lossy URI conversion. Once the
      // native engine advertises readiness, profiles must be valid native
      // sing-box outbounds before they reach it.
      for (final item in nodeItems) {
        try {
          SingBoxProfileValidator.validateOutbound(
            protocolCode: definition.code, item: item);
        } on FormatException {
          throw const ConnectionBootstrapException(
              'SINGBOX_PROFILE_NOT_NATIVE_READY');
        }
      }
    }
    return ConnectionCandidate(
      server: selected.single,
      protocol: definition,
      profiles: ClientProtocolProfiles(
        namespace: profiles.namespace,
        protocol: definition,
        items: List.unmodifiable(nodeItems),
      ),
    );
    } on TenantApiException catch (error) {
      // Only genuine network loss is eligible. Explicit denial (401/403),
      // invalid TLS, server errors or changed permissions MUST NOT fall back.
      if (error.message != 'NETWORK_UNAVAILABLE') rethrow;
      return _prepareEmergency(username, panel, serverId, definition);
    } on TimeoutException {
      return _prepareEmergency(username, panel, serverId, definition);
    }
  }

  Future<ConnectionCandidate> _prepareEmergency(
      String? username, PanelDirectoryEntry panel, String serverId,
      VpnProtocolDefinition protocol) async {
    if (username == null || username.isEmpty || protocol.code != 'wireguard') {
      throw const ConnectionBootstrapException('EMERGENCY_PROFILE_NOT_AVAILABLE');
    }
    final record = await emergency.match(
      username: username, panel: panel,
      serverId: serverId, protocolCode: protocol.code,
    );
    if (record == null) {
      throw const ConnectionBootstrapException('EMERGENCY_PROFILE_NOT_AVAILABLE');
    }
    // This candidate still goes through normal native policy/readiness gates,
    // then through the native peer handshake. It is never a "connected" flag.
    return ConnectionCandidate(
      server: record.server, protocol: protocol,
      profiles: record.profiles, fromEmergencyCache: true,
    );
  }
}

class ConnectionCandidate {
  const ConnectionCandidate({
    required this.server,
    required this.protocol,
    required this.profiles,
    this.fromEmergencyCache = false,
  });
  final AppServer server;
  final VpnProtocolDefinition protocol;
  final ClientProtocolProfiles profiles;
  final bool fromEmergencyCache;
}

class ConnectionBootstrapException implements Exception {
  const ConnectionBootstrapException(this.code);
  final String code;
  @override
  String toString() => code;
}
