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
  const ConnectionBootstrap({required this.api});

  final TenantApi api;

  /// Fail closed before fetching any credential-bearing profile.
  /// This intentionally re-reads entitlements immediately before a connect
  /// attempt; a cached UI selection is not authorization.
  Future<ConnectionCandidate> prepare({
    required PanelDirectoryEntry panel,
    required String sessionToken,
    required String serverId,
    required String protocolCode,
    required VpnPolicy policy,
    required NativeVpnCapabilities capabilities,
    required NativeProtocolReadiness nativeProtocols,
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
    final catalog = await api.loadSessionProtocolCatalog(
      panel: panel, sessionToken: sessionToken);
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
  }
}

class ConnectionCandidate {
  const ConnectionCandidate({
    required this.server,
    required this.protocol,
    required this.profiles,
  });
  final AppServer server;
  final VpnProtocolDefinition protocol;
  final ClientProtocolProfiles profiles;
}

class ConnectionBootstrapException implements Exception {
  const ConnectionBootstrapException(this.code);
  final String code;
  @override
  String toString() => code;
}
