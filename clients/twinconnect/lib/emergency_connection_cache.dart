import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'account_snapshot.dart';
import 'protocols.dart';
import 'server_inventory.dart';
import 'tenant_models.dart';

/// Offline access is deliberately limited to previously *verified* WireGuard
/// handshakes. No fresh enrollment, new entitlement, or quota reset is possible.
class EmergencyConnectionRecord {
  const EmergencyConnectionRecord({
    required this.server,
    required this.profiles,
    required this.storedAt,
    required this.expiresAt,
  });

  final AppServer server;
  final ClientProtocolProfiles profiles;
  final DateTime storedAt;
  final DateTime expiresAt;
}

class EmergencyCachedAccess {
  const EmergencyCachedAccess({required this.catalog, required this.inventory});

  final PanelProtocolCatalog catalog;
  final AppServerInventory inventory;
}

/// OS-encrypted emergency cache. The only authority it conveys is a bounded
/// ability to retry an already authenticated, natively verified WireGuard peer.
/// Remote suspension cannot be learned during a network partition; the server
/// must still enforce its own peer/account restrictions.
class EmergencyConnectionCache {
  const EmergencyConnectionCache({this.reader, this.writer});

  final Future<String?> Function()? reader;
  final Future<void> Function(String?)? writer;

  static const _secure = FlutterSecureStorage();
  static const _key = 'twinconnect_emergency_verified_wg_v1';
  static const maxOfflineAge = Duration(hours: 6);
  static const _maxBytes = 512 * 1024;

  Future<String?> _readRaw() async =>
      reader != null ? reader!() : _secure.read(key: _key);

  Future<void> _writeRaw(String? value) async {
    if (writer != null) {
      await writer!(value);
    } else if (value == null) {
      await _secure.delete(key: _key);
    } else {
      await _secure.write(key: _key, value: value);
    }
  }

  static bool _validAccount(AppAccountSnapshot account, String namespace,
      DateTime now) {
    return account.namespace == namespace &&
        account.status == 'active' &&
        account.expiresAt != null &&
        account.expiresAt!.isAfter(now) &&
        (account.trafficLimitBytes == 0 ||
            account.trafficUsedBytes < account.trafficLimitBytes);
  }

  Future<void> saveVerified({
    required String username,
    required PanelDirectoryEntry panel,
    required AppServer server,
    required ClientProtocolProfiles profiles,
    required AppAccountSnapshot account,
    DateTime? now,
  }) async {
    final at = (now ?? DateTime.now()).toUtc();
    // This feature does not cache credentials for other transport families.
    if (profiles.protocol.code != 'wireguard' ||
        profiles.namespace != panel.namespace ||
        !_validAccount(account, panel.namespace, at) ||
        !profiles.items.any((item) => item['node_id'].toString() == server.id)) {
      return;
    }
    final expiry = account.expiresAt!.toUtc();
    final record = <String, dynamic>{
      'schema': 1,
      'username': username,
      'namespace': panel.namespace,
      'origin': panel.apiOrigin.origin,
      'protocol': profiles.protocol.code,
      'saved_at': at.millisecondsSinceEpoch,
      'expires_at': expiry.millisecondsSinceEpoch,
      'server': {
        'id': server.id,
        'name': server.name,
        'country_code': server.countryCode,
        'node_online': server.nodeOnline,
        'latency_ms': null,
        'probe_ip': server.probeIp,
      },
      'profiles': {
        'schema': 1,
        'namespace': profiles.namespace,
        'protocol': 'wireguard',
        'items': profiles.items.where(
            (item) => item['node_id'].toString() == server.id).toList(),
      },
    };
    // Fail safe on a corrupt/unavailable vault, but do not interrupt VPN.
    try {
      final existing = await _rawEntries();
      final scoped = existing.where((entry) =>
          !(entry['username'] == username &&
              entry['namespace'] == panel.namespace &&
              entry['origin'] == panel.apiOrigin.origin &&
              entry['protocol'] == 'wireguard' &&
              (entry['server'] is Map &&
                  (entry['server'] as Map)['id'] == server.id))).toList();
      final entries = [record, ...scoped.take(7)];
      final body = jsonEncode({'schema': 1, 'entries': entries});
      if (body.length <= _maxBytes) await _writeRaw(body);
    } catch (_) {
      // Never allow an OS-vault failure to break a verified active tunnel.
    }
  }

  Future<List<Map<String, dynamic>>> _rawEntries() async {
    final raw = await _readRaw();
    if (raw == null || raw.length > _maxBytes) return [];
    final parsed = jsonDecode(raw);
    if (parsed is! Map<String, dynamic> ||
        parsed['schema'] != 1 || parsed['entries'] is! List) return [];
    return [
      for (final item in (parsed['entries'] as List).take(8))
        if (item is Map<String, dynamic>) item,
    ];
  }

  Future<List<EmergencyConnectionRecord>> available({
    required String username,
    required PanelDirectoryEntry panel,
    DateTime? now,
  }) async {
    final at = (now ?? DateTime.now()).toUtc();
    try {
      final records = <EmergencyConnectionRecord>[];
      for (final item in await _rawEntries()) {
        if (item['username'] != username ||
            item['namespace'] != panel.namespace ||
            item['origin'] != panel.apiOrigin.origin ||
            item['protocol'] != 'wireguard' ||
            item['schema'] != 1) continue;
        final saved = item['saved_at'];
        final expires = item['expires_at'];
        if (saved is! int || expires is! int) continue;
        final storedAt = DateTime.fromMillisecondsSinceEpoch(saved, isUtc: true);
        final expiry = DateTime.fromMillisecondsSinceEpoch(expires, isUtc: true);
        final age = at.difference(storedAt);
        if (age.isNegative || age > maxOfflineAge || !expiry.isAfter(at)) continue;
        final rawServer = item['server'];
        final rawProfiles = item['profiles'];
        if (rawServer is! Map<String, dynamic> ||
            rawProfiles is! Map<String, dynamic>) continue;
        final server = AppServer.fromJson(rawServer);
        final profiles = ClientProtocolProfiles.fromJson(rawProfiles);
        if (profiles.namespace != panel.namespace ||
            profiles.protocol.code != 'wireguard' ||
            profiles.items.isEmpty ||
            profiles.items.any((entry) =>
                entry['node_id'].toString() != server.id)) continue;
        records.add(EmergencyConnectionRecord(
          server: server, profiles: profiles,
          storedAt: storedAt, expiresAt: expiry,
        ));
      }
      return records;
    } catch (_) {
      return [];
    }
  }

  Future<EmergencyConnectionRecord?> match({
    required String username,
    required PanelDirectoryEntry panel,
    required String serverId,
    required String protocolCode,
    DateTime? now,
  }) async {
    if (protocolCode != 'wireguard') return null;
    for (final record in await available(
        username: username, panel: panel, now: now)) {
      if (record.server.id == serverId) return record;
    }
    return null;
  }

  Future<EmergencyCachedAccess?> restoreAccess({
    required String username,
    required PanelDirectoryEntry panel,
    DateTime? now,
  }) async {
    final records = await available(
        username: username, panel: panel, now: now);
    if (records.isEmpty) return null;
    final seen = <String>{};
    final servers = <AppServer>[];
    for (final record in records) {
      if (seen.add(record.server.id)) servers.add(record.server);
    }
    return EmergencyCachedAccess(
      catalog: PanelProtocolCatalog.fromJson({
        'schema': 1,
        'namespace': panel.namespace,
        'protocols': [
          {'code': 'wireguard', 'selected': true,
            'config_record_present': true},
        ],
      }),
      inventory: AppServerInventory(
        namespace: panel.namespace,
        servers: List.unmodifiable(servers),
      ),
    );
  }

  Future<void> clear() async => _writeRaw(null);
}
