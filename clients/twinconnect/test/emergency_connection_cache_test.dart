import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/account_snapshot.dart';
import 'package:twinconnect/emergency_connection_cache.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/server_inventory.dart';
import 'package:twinconnect/tenant_models.dart';

final _panel = PanelDirectoryEntry(
    namespace: 'TPABCDEF', apiOrigin: Uri.parse('https://panel.example.org'));
const _user = 'TPABCDEF_A_demo';
final _server = AppServer.fromJson({
  'id': '17', 'name': 'Germany', 'country_code': 'DE',
  'node_online': true, 'latency_ms': null, 'probe_ip': '8.8.8.8',
});
final _profiles = ClientProtocolProfiles(
  namespace: 'TPABCDEF', protocol: VpnProtocols.byCode('wireguard')!,
  items: [
    {'node_id': 17, 'config': '[Interface]\nPrivateKey = test\n[Peer]\nEndpoint = example.org:51820'},
  ],
);

AppAccountSnapshot _account(DateTime now, {
  String status = 'active', DateTime? expiry, int limit = 100, int used = 5,
}) => AppAccountSnapshot(
  namespace: 'TPABCDEF', trafficLimitBytes: limit, trafficUsedBytes: used,
  expiresAt: expiry ?? now.add(const Duration(days: 1)),
  activationDurationDays: 30, status: status,
);

void main() {
  late String? state;
  late EmergencyConnectionCache cache;
  final now = DateTime.utc(2026, 11, 18, 12);

  setUp(() {
    state = null;
    cache = EmergencyConnectionCache(
      reader: () async => state,
      writer: (value) async { state = value; },
    );
  });

  test('a peer becomes available only after a verified connect save', () async {
    expect(await cache.restoreAccess(
        username: _user, panel: _panel, now: now), isNull);
    await cache.saveVerified(
      username: _user, panel: _panel, server: _server,
      profiles: _profiles, account: _account(now), now: now);
    final record = await cache.match(
      username: _user, panel: _panel, serverId: '17',
      protocolCode: 'wireguard', now: now.add(const Duration(hours: 1)));
    expect(record, isNotNull);
    expect(record!.profiles.items.single['node_id'], 17);
    expect(record.server.probeIp, '8.8.8.8');
    final view = await cache.restoreAccess(
      username: _user, panel: _panel, now: now);
    expect(view!.catalog.entries.where((e) => e.selected)
        .map((e) => e.protocol.code), ['wireguard']);
    expect(view.inventory.servers.single.id, '17');
  });

  test('account, origin, username and protocol are all scoped', () async {
    await cache.saveVerified(
      username: _user, panel: _panel, server: _server,
      profiles: _profiles, account: _account(now), now: now);
    expect(await cache.match(
        username: 'other', panel: _panel, serverId: '17',
        protocolCode: 'wireguard', now: now), isNull);
    expect(await cache.match(
        username: _user,
        panel: PanelDirectoryEntry(namespace: 'TPABCDEF',
            apiOrigin: Uri.parse('https://different.example.org')),
        serverId: '17', protocolCode: 'wireguard', now: now), isNull);
    expect(await cache.match(
        username: _user, panel: _panel, serverId: '17',
        protocolCode: 'openvpn', now: now), isNull);
    expect(await cache.match(
        username: _user, panel: _panel, serverId: '55',
        protocolCode: 'wireguard', now: now), isNull);
  });

  test('six hour limit and account expiry cannot be extended offline', () async {
    await cache.saveVerified(
      username: _user, panel: _panel, server: _server,
      profiles: _profiles,
      account: _account(now, expiry: now.add(const Duration(hours: 3))),
      now: now);
    expect(await cache.match(
        username: _user, panel: _panel, serverId: '17',
        protocolCode: 'wireguard',
        now: now.add(const Duration(hours: 4))), isNull);
    await cache.saveVerified(
      username: _user, panel: _panel, server: _server,
      profiles: _profiles, account: _account(now), now: now);
    expect(await cache.match(
        username: _user, panel: _panel, serverId: '17',
        protocolCode: 'wireguard',
        now: now.add(const Duration(hours: 7))), isNull);
    expect(await cache.match(
        username: _user, panel: _panel, serverId: '17',
        protocolCode: 'wireguard',
        now: now.subtract(const Duration(minutes: 1))), isNull);
  });

  test('suspended, expired and exhausted accounts never seed emergency vault',
      () async {
    for (final account in [
      _account(now, status: 'suspended'),
      _account(now, expiry: now.subtract(const Duration(minutes: 1))),
      _account(now, limit: 100, used: 100),
    ]) {
      await cache.saveVerified(username: _user, panel: _panel,
          server: _server, profiles: _profiles, account: account, now: now);
      expect(state, isNull);
    }
  });

  test('corrupt vault fails closed and logout removes all secrets', () async {
    state = '{broken';
    expect(await cache.available(
        username: _user, panel: _panel, now: now), isEmpty);
    await cache.saveVerified(username: _user, panel: _panel,
        server: _server, profiles: _profiles, account: _account(now),
        now: now);
    expect(state, isNotNull);
    await cache.clear();
    expect(state, isNull);
  });
}
