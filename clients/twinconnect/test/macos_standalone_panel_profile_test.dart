import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/macos_standalone_panel_profile.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/server_inventory.dart';
import 'package:twinconnect/tenant_api.dart';
import 'package:twinconnect/tenant_models.dart';

final panel = PanelDirectoryEntry(
  namespace: 'TPABCDEF',
  apiOrigin: Uri.parse('https://panel.example.org'),
);
const sessionToken = '0123456789012345678901234567890123456789';

class FakeStandalonePanel extends TenantApi {
  FakeStandalonePanel()
      : super(vendorOrigin: Uri.parse('https://vendor.example.org'));

  bool authorized = true;
  bool nodeAssigned = true;
  bool duplicateProfile = false;
  int catalogCalls = 0;
  int serverCalls = 0;
  int secretCalls = 0;
  String? lastNativeProtocol;

  @override
  Future<PanelProtocolCatalog> loadSessionProtocolCatalog({
    required PanelDirectoryEntry panel,
    required String sessionToken,
  }) async {
    catalogCalls++;
    return PanelProtocolCatalog.fromJson({
      'schema': 1, 'namespace': panel.namespace,
      'protocols': [
        {'code': 'hysteria2', 'selected': authorized,
         'config_record_present': authorized}
      ],
    });
  }

  @override
  Future<AppServerInventory> refreshSessionServers({
    required PanelDirectoryEntry panel,
    required String sessionToken,
  }) async {
    serverCalls++;
    return AppServerInventory.fromJson({
      'schema': 1, 'namespace': panel.namespace,
      'servers': [
        {'id': nodeAssigned ? '17' : '18', 'name': 'Germany',
         'country_code': 'DE', 'node_online': true, 'latency_ms': null}
      ],
    });
  }

  @override
  Future<ClientProtocolProfiles> loadSessionNativeProfiles({
    required PanelDirectoryEntry panel,
    required String sessionToken,
    required VpnProtocolDefinition protocol,
    required NativeProtocolReadiness native,
  }) async {
    secretCalls++;
    lastNativeProtocol = protocol.code;
    expect(native.supports(protocol.code), isTrue);
    final item = <String, dynamic>{
      'node_id': 17,
      'outbound': <String, dynamic>{
        'type': 'hysteria2', 'server': 'original.example',
        'server_port': 443, 'password': 'private-secret',
        'tls': {'enabled': true, 'server_name': 'original.example'},
      },
    };
    return ClientProtocolProfiles.fromJson({
      'schema': 1, 'namespace': panel.namespace,
      'protocol': protocol.code,
      'items': [item, if (duplicateProfile) item],
    });
  }
}

void main() {
  test('fetches current entitlement, server and exact-node secret from panel',
      () async {
    final api = FakeStandalonePanel();
    final prepared = await MacStandalonePanelProfile(api: api).prepare(
      panel: panel, sessionToken: sessionToken, serverId: '17',
      protocolCode: 'hysteria2', engineInstalled: true,
    );
    expect([api.catalogCalls, api.serverCalls, api.secretCalls], [1, 1, 1]);
    expect(prepared.serverId, '17');
    expect(prepared.protocolCode, 'hysteria2');
    final config = jsonDecode(prepared.configJson) as Map<String, dynamic>;
    expect(config['dns'], isNull);
    expect(config['inbounds'], [
      {'type': 'mixed', 'tag': 'local-proxy',
       'listen': '127.0.0.1', 'listen_port': 10808}
    ]);
    expect((config['outbounds'] as List).single['server'], 'original.example');
    expect((config['outbounds'] as List).single['password'], 'private-secret');
    expect((config['route'] as Map)['final'], 'proxy');
    expect(prepared.configJson, isNot(contains('auto_route')));
  });

  test('missing native engine does not fetch any private data', () async {
    final api = FakeStandalonePanel();
    await expectLater(
      MacStandalonePanelProfile(api: api).prepare(
        panel: panel, sessionToken: sessionToken, serverId: '17',
        protocolCode: 'hysteria2', engineInstalled: false,
      ), throwsA(isA<FormatException>()),
    );
    expect([api.catalogCalls, api.serverCalls, api.secretCalls], [0, 0, 0]);
  });

  test('revoked entitlement stops before node inventory and secrets', () async {
    final api = FakeStandalonePanel()..authorized = false;
    await expectLater(
      MacStandalonePanelProfile(api: api).prepare(
        panel: panel, sessionToken: sessionToken, serverId: '17',
        protocolCode: 'hysteria2', engineInstalled: true,
      ), throwsA(isA<FormatException>()),
    );
    expect(api.catalogCalls, 1);
    expect(api.serverCalls, 0);
    expect(api.secretCalls, 0);
  });

  test('unassigned server stops before private profile request', () async {
    final api = FakeStandalonePanel()..nodeAssigned = false;
    await expectLater(
      MacStandalonePanelProfile(api: api).prepare(
        panel: panel, sessionToken: sessionToken, serverId: '17',
        protocolCode: 'hysteria2', engineInstalled: true,
      ), throwsA(isA<FormatException>()),
    );
    expect(api.secretCalls, 0);
  });

  test('ambiguous same-node records are never selected automatically', () async {
    final api = FakeStandalonePanel()..duplicateProfile = true;
    await expectLater(
      MacStandalonePanelProfile(api: api).prepare(
        panel: panel, sessionToken: sessionToken, serverId: '17',
        protocolCode: 'hysteria2', engineInstalled: true,
      ), throwsA(isA<FormatException>()),
    );
    expect(api.secretCalls, 1);
  });

  test('unsupported family does not request credentials', () async {
    final api = FakeStandalonePanel();
    await expectLater(
      MacStandalonePanelProfile(api: api).prepare(
        panel: panel, sessionToken: sessionToken, serverId: '17',
        protocolCode: 'wireguard', engineInstalled: true,
      ), throwsA(isA<FormatException>()),
    );
    expect(api.secretCalls, 0);
  });
}
