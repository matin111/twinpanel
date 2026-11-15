import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'xray_inbound_profiles.dart';

/// OS-encrypted, short-lived V2Ray inbound display cache.
/// VLESS URIs contain credentials: never use SharedPreferences, logs or files.
/// Cache is display-only. Connection requires a fresh authenticated fetch.
class XrayInboundSecureCache {
  const XrayInboundSecureCache();
  static const _secure = FlutterSecureStorage();
  static const _key = 'twinconnect_xray_inbounds_v1';
  static const _ttl = Duration(hours: 12);
  static const _maxBytes = 256 * 1024;

  Future<List<XrayServerProfiles>?> read({
    required String username,
    required String namespace,
    required Uri panelOrigin,
    DateTime? now,
  }) async {
    try {
      final raw = await _secure.read(key: _key);
      if (raw == null || raw.length > _maxBytes) return null;
      final data = jsonDecode(raw);
      if (data is! Map<String, dynamic> ||
          data['schema'] != 1 ||
          data['username'] != username ||
          data['namespace'] != namespace ||
          data['origin'] != panelOrigin.origin) return null;
      final savedAt = data['saved_at'];
      if (savedAt is! int) return null;
      final age = (now ?? DateTime.now().toUtc())
          .difference(DateTime.fromMillisecondsSinceEpoch(savedAt, isUtc: true));
      if (age.isNegative || age > _ttl) return null;
      final groups = data['server_groups'];
      if (groups is! List || groups.isEmpty || groups.length > 200) return null;
      return XrayServerProfiles.fromResponse({
        'schema': 1,
        'protocol': 'v2ray',
        'server_groups': groups,
      });
    } catch (_) {
      // An unavailable/corrupt OS vault must not make an inbound look live.
      return null;
    }
  }

  Future<void> save({
    required String username,
    required String namespace,
    required Uri panelOrigin,
    required List<XrayServerProfiles> groups,
    DateTime? now,
  }) async {
    // Cache only independently validated server_groups, not tokens or the
    // complete API response. Persist them exclusively in OS secure storage.
    final encodedGroups = [
      for (final group in groups)
        {
          'node_id': group.serverId,
          'profiles': [
            for (final inbound in group.inbounds)
              {
                'id': inbound.id,
                'title': inbound.title,
                'uri': inbound.uri.toString(),
              },
          ],
        },
    ];
    final body = jsonEncode({
      'schema': 1,
      'username': username,
      'namespace': namespace,
      'origin': panelOrigin.origin,
      'saved_at': (now ?? DateTime.now().toUtc()).millisecondsSinceEpoch,
      'server_groups': encodedGroups,
    });
    if (body.length > _maxBytes) return;
    await _secure.write(key: _key, value: body);
  }

  Future<void> clear() async => _secure.delete(key: _key);
}
