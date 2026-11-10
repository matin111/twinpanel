import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/native_vpn_bridge.dart';
import 'package:twinconnect/protocol_catalog_view.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/tenant_api.dart';
import 'package:twinconnect/tenant_models.dart';
import 'package:twinconnect/vpn_policy.dart';

Map<String, dynamic> _catalog() => {
  'schema': 1,
  'namespace': 'TP0123456789ABCDEF',
  'protocols': [
    for (final protocol in VpnProtocols.all)
      {
        'code': protocol.code,
        'title': protocol.name,
        'engine_family': protocol.engine.name,
        'selected': protocol.code != 'l2tp',
        'config_record_present': protocol.code != 'l2tp',
        'client_engine_ready': true, // forged vendor field must be ignored
      }
  ],
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('canonical TwinPanel catalog contains all 16 protocols once', () {
    final codes = VpnProtocols.all.map((p) => p.code).toList();
    expect(codes.length, 16);
    expect(codes.toSet().length, 16);
    expect(codes, containsAll([
      'cisco', 'openvpn', 'wireguard', 'l2tp', 'v2ray', 'hysteria2',
      'tuic', 'anytls', 'naive', 'shadowtls', 'snell', 'socks5',
      'mieru', 'trusttunnel', 'amneziawg', 'sudoku',
    ]));
    expect(VpnProtocols.byCode('xray')!.code, 'v2ray');
    expect(VpnProtocols.byCode('openconnect')!.code, 'cisco');
    expect(VpnProtocols.byCode('awg')!.code, 'amneziawg');
    expect(VpnProtocols.byCode('grpc'), isNull);
  });

  test('different engines are assigned to non-interchangeable profiles', () {
    expect(VpnProtocols.byCode('amneziawg')!.engine,
        VpnEngineFamily.amneziawg);
    expect(VpnProtocols.byCode('wireguard')!.engine,
        VpnEngineFamily.wireguard);
    expect(VpnProtocols.byCode('v2ray')!.engine, VpnEngineFamily.xray);
    expect(VpnProtocols.byCode('mieru')!.engine, VpnEngineFamily.mieru);
    expect(VpnProtocols.byCode('sudoku')!.engine, VpnEngineFamily.sudoku);
    expect(VpnProtocols.byCode('shadowtls')!.profileFormat,
        'singbox_chain');
  });

  test('panel claiming engine ready is never authoritative', () {
    final catalog = PanelProtocolCatalog.fromJson(_catalog());
    expect(catalog.entries.length, 16);
    expect(catalog.entries.every((e) => !e.clientEngineReady), true);
    final l2tp =
        catalog.entries.singleWhere((e) => e.protocol.code == 'l2tp');
    expect(l2tp.selected, false);
    expect(l2tp.configRecordPresent, false);
  });

  test('unknown, incomplete, and duplicate catalogs fail closed', () {
    final unknown = _catalog();
    (unknown['protocols'] as List)[0]['code'] = 'unknown';
    expect(() => PanelProtocolCatalog.fromJson(unknown), throwsFormatException);

    final missing = _catalog();
    (missing['protocols'] as List).removeLast();
    expect(() => PanelProtocolCatalog.fromJson(missing), throwsFormatException);

    final duplicated = _catalog();
    (duplicated['protocols'] as List)[1]['code'] = 'cisco';
    expect(() => PanelProtocolCatalog.fromJson(duplicated), throwsFormatException);
  });

  test('native engines must provide a valid complete handshake', () {
    final wrong = NativeProtocolReadiness.fromNative({
      'contractVersion': 2,
      'supportedProtocols': ['wireguard']
    });
    expect(wrong.supportedCodes, isEmpty);

    final unknown = NativeProtocolReadiness.fromNative({
      'contractVersion': 1,
      'supportedProtocols': ['wireguard', 'fakeproto']
    });
    expect(unknown.supportedCodes, isEmpty);

    final valid = NativeProtocolReadiness.fromNative({
      'contractVersion': 1,
      'supportedProtocols': ['wireguard', 'openvpn']
    });
    expect(valid.supports('wireguard'), true);
    expect(valid.supports('sudoku'), false);
  });

  test('secret profiles cannot be requested without verified engine', () async {
    final api = TenantApi(
      vendorOrigin: Uri.parse('https://vendor.example.org'),
    );
    final panel = PanelDirectoryEntry(
      namespace: 'TP0123456789ABCDEF',
      apiOrigin: Uri.parse('https://panel.example.org'),
    );
    try {
      await api.loadNativeProfiles(
        panel: panel,
        username: 'TP0123456789ABCDEF_R1_alice',
        shareToken: 'some-private-token',
        protocol: VpnProtocols.byCode('wireguard')!,
        native: const NativeProtocolReadiness(supportedCodes: {}),
      );
      fail('Must reject before any network call');
    } on TenantApiException catch (error) {
      expect(error.message, 'ENGINE_NOT_READY');
    }
  });

  test('Xray inbound variants and ShadowTLS chain remain intact', () {
    final xray = ClientProtocolProfiles.fromJson({
      'schema': 1,
      'namespace': 'TP0123456789ABCDEF',
      'protocol': 'v2ray',
      'items': [
        {
          'node_id': 1,
          'profiles': [
            {'id': 'websocket_tls', 'uri': 'vless://ws'},
            {'id': 'xhttp_reality', 'uri': 'vless://xhttp'},
            {'id': 'tcp_simple', 'uri': 'vless://tcp'},
          ],
        },
      ],
    });
    final variants =
        xray.items.first['profiles'] as List<dynamic>;
    expect(variants.length, 3);
    expect(variants.map((e) => (e as Map)['id']).toSet(), {
      'websocket_tls', 'xhttp_reality', 'tcp_simple'
    });

    final shadowtls = ClientProtocolProfiles.fromJson({
      'schema': 1,
      'namespace': 'TP0123456789ABCDEF',
      'protocol': 'shadowtls',
      'items': [{
        'config': '{"outbounds":[{"type":"shadowsocks","detour":"transport"},'
            '{"type":"shadowtls","tag":"transport"}]}'
      }],
    });
    expect(shadowtls.items.single['config'], contains('"detour"'));
  });

  test('native policy and protocol must both be ready', () {
    const policy = VpnPolicy();
    const capabilities = NativeVpnCapabilities(
      platform: VpnPlatform.android,
      engineReady: false,
      fullTunnel: false,
    );
    expect(
      () => NativeVpnBridge.requireProtocolSafeToConnect(
        policy,
        capabilities,
        VpnProtocols.byCode('wireguard')!,
        const NativeProtocolReadiness(supportedCodes: {'wireguard'}),
      ),
      throwsStateError,
    );
  });

  testWidgets('app shows only plan-selected protocols in horizontal chips',
      (tester) async {
    final catalog = PanelProtocolCatalog.fromJson(_catalog());
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ProtocolCatalogCard(catalog: catalog),
        ),
      ),
    ));
    expect(find.byKey(const Key('protocolCatalogCard')), findsOneWidget);
    expect(find.byKey(const Key('allowedProtocolFilters')), findsOneWidget);
    expect(find.byType(ListTile), findsNothing);
    expect(find.byKey(const Key('protocol_l2tp')), findsNothing);
    expect(find.byKey(const Key('protocol_openvpn')), findsOneWidget);
    expect(catalog.entries.where((entry) => entry.selected).length, 15);
    expect(find.byType(FilledButton), findsNothing);
  });
}
