import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/connection_bootstrap.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/server_inventory.dart';
import 'package:twinconnect/tenant_api.dart';
import 'package:twinconnect/tenant_models.dart';
import 'package:twinconnect/vpn_policy.dart';

final _panel = PanelDirectoryEntry(
  namespace: 'TPABCDEF',
  apiOrigin: Uri.parse('https://panel.example.org'),
);
const _session = '0123456789012345678901234567890123456789';

class FakePanel extends TenantApi {
  FakePanel() : super(vendorOrigin: Uri.parse('https://vendor.example.org'));

  bool authorized = true;
  bool online = true;
  bool profileForNode = true;
  int catalogCalls = 0;
  int serverCalls = 0;
  int profileCalls = 0;

  @override
  Future<PanelProtocolCatalog> loadSessionProtocolCatalog({
    required PanelDirectoryEntry panel, required String sessionToken,
  }) async {
    catalogCalls++;
    return PanelProtocolCatalog.fromJson({
      'schema': 1, 'namespace': panel.namespace,
      'protocols': [
        for (final p in VpnProtocols.all) {
          'code': p.code, 'selected': authorized && p.code == 'wireguard',
          'config_record_present': authorized && p.code == 'wireguard',
        },
      ],
    });
  }

  @override
  Future<AppServerInventory> refreshSessionServers({
    required PanelDirectoryEntry panel, required String sessionToken,
  }) async {
    serverCalls++;
    return AppServerInventory.fromJson({
      'schema': 1, 'namespace': panel.namespace,
      'servers': [{
        'id': '17', 'name': 'Germany',
        'country_code': 'DE', 'node_online': online,
        'latency_ms': null,
      }],
    });
  }

  @override
  Future<ClientProtocolProfiles> loadSessionNativeProfiles({
    required PanelDirectoryEntry panel,
    required String sessionToken,
    required VpnProtocolDefinition protocol,
    required NativeProtocolReadiness native,
  }) async {
    profileCalls++;
    return ClientProtocolProfiles.fromJson({
      'schema': 1, 'namespace': panel.namespace,
      'protocol': protocol.code,
      'items': [
        {'node_id': profileForNode ? 17 : 22, 'config': '[Interface]'},
        {'node_id': 23, 'config': '[Interface] other node'},
      ],
    });
  }
}

const _native = NativeVpnCapabilities(
  platform: VpnPlatform.windows,
  engineReady: true,
  fullTunnel: true,
  dnsGuard: true,
  ipv6Guard: true,
);
const _ready = NativeProtocolReadiness(supportedCodes: {'wireguard'});

void main() {
  test('no native Windows engine means no API request for private profiles', () async {
    final api = FakePanel();
    final bootstrap = ConnectionBootstrap(api: api);
    await expectLater(
      bootstrap.prepare(
        panel: _panel, sessionToken: _session, serverId: '17',
        protocolCode: 'wireguard', policy: const VpnPolicy(),
        capabilities: NativeVpnCapabilities.unavailable(VpnPlatform.windows),
        nativeProtocols: const NativeProtocolReadiness(supportedCodes: {}),
      ),
      throwsA(isA<ConnectionBootstrapException>()
          .having((e) => e.code, 'code', 'NATIVE_ENGINE_UNAVAILABLE')),
    );
    expect(api.catalogCalls, 0);
    expect(api.serverCalls, 0);
    expect(api.profileCalls, 0);
  });

  test('plan revoked: refuse before server lookup or secrets', () async {
    final api = FakePanel()..authorized = false;
    await expectLater(
      ConnectionBootstrap(api: api).prepare(
        panel: _panel, sessionToken: _session, serverId: '17',
        protocolCode: 'wireguard', policy: const VpnPolicy(),
        capabilities: _native, nativeProtocols: _ready,
      ),
      throwsA(isA<ConnectionBootstrapException>()
          .having((e) => e.code, 'code', 'PROTOCOL_NOT_ALLOWED')),
    );
    expect(api.serverCalls, 0);
    expect(api.profileCalls, 0);
  });

  test('WireGuard reuses a freshly fetched same-attempt catalog', () async {
    final api = FakePanel();
    final fresh = await api.loadSessionProtocolCatalog(
      panel: _panel, sessionToken: _session,
    );
    final candidate = await ConnectionBootstrap(api: api).prepare(
      panel: _panel, sessionToken: _session, serverId: '17',
      protocolCode: 'wireguard', policy: const VpnPolicy(),
      capabilities: _native, nativeProtocols: _ready,
      currentAttemptCatalog: Future.value(fresh),
    );
    expect(candidate.server.id, '17');
    expect(api.catalogCalls, 1); // no duplicate catalog API request
    expect(api.serverCalls, 1);
    expect(api.profileCalls, 1);
  });

  test('WireGuard pre-fetched revoked catalog still blocks secrets', () async {
    final api = FakePanel()..authorized = false;
    final revoked = await api.loadSessionProtocolCatalog(
      panel: _panel, sessionToken: _session,
    );
    await expectLater(ConnectionBootstrap(api: api).prepare(
      panel: _panel, sessionToken: _session, serverId: '17',
      protocolCode: 'wireguard', policy: const VpnPolicy(),
      capabilities: _native, nativeProtocols: _ready,
      currentAttemptCatalog: Future.value(revoked),
    ), throwsA(isA<ConnectionBootstrapException>().having(
        (e) => e.code, 'code', 'PROTOCOL_NOT_ALLOWED')));
    expect(api.serverCalls, 0);
    expect(api.profileCalls, 0);
  });

  test('unassigned node refuses before downloading secrets', () async {
    final api = FakePanel();
    await expectLater(
      ConnectionBootstrap(api: api).prepare(
        panel: _panel, sessionToken: _session, serverId: '99',
        protocolCode: 'wireguard', policy: const VpnPolicy(),
        capabilities: _native, nativeProtocols: _ready,
      ),
      throwsA(isA<ConnectionBootstrapException>()
          .having((e) => e.code, 'code', 'SERVER_NOT_AVAILABLE')),
    );
    expect(api.profileCalls, 0);
  });

  test('offline heartbeat is advisory; exact assigned node is still eligible',
      () async {
    final api = FakePanel()..online = false;
    final candidate = await ConnectionBootstrap(api: api).prepare(
      panel: _panel, sessionToken: _session, serverId: '17',
      protocolCode: 'wireguard', policy: const VpnPolicy(),
      capabilities: _native, nativeProtocols: _ready,
    );
    expect(candidate.server.nodeOnline, isFalse);
    expect(candidate.profiles.items, hasLength(1));
  });

  test('matching authorized native configuration becomes a candidate, not a connection', () async {
    final api = FakePanel();
    final candidate = await ConnectionBootstrap(api: api).prepare(
      panel: _panel, sessionToken: _session, serverId: '17',
      protocolCode: 'wireguard', policy: const VpnPolicy(),
      capabilities: _native, nativeProtocols: _ready,
    );
    expect(candidate.server.id, '17');
    expect(candidate.protocol.code, 'wireguard');
    expect(candidate.profiles.items, hasLength(1));
    expect(api.profileCalls, 1);
  });

  test('profile bundle for wrong node is rejected', () async {
    final api = FakePanel()..profileForNode = false;
    await expectLater(
      ConnectionBootstrap(api: api).prepare(
        panel: _panel, sessionToken: _session, serverId: '17',
        protocolCode: 'wireguard', policy: const VpnPolicy(),
        capabilities: _native, nativeProtocols: _ready,
      ),
      throwsA(isA<ConnectionBootstrapException>()
          .having((e) => e.code, 'code', 'SERVER_PROFILE_MISSING')),
    );
  });
}
