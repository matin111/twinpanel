import 'dart:convert';

import 'server_inventory.dart';

/// Official SUDOKU-ASCII standalone client format; NOT sing-box / Xray.
/// Only the panel's active centrally shared, per-subscription credentials
/// are accepted. The public endpoint may use a per-node tunnel-forwarded
/// port; never replace its delivered port with the internal shared 18553. This parser never changes account keys or node settings.
class SudokuClientProfile {
  const SudokuClientProfile({
    required this.nodeId,
    required this.host,
    required this.port,
    required this.config,
  });

  final String nodeId;
  final String host;
  final int port;
  final Map<String, dynamic> config;

  static SudokuClientProfile? fromItem(
      Map<String, dynamic> item, String nodeId) {
    if (nodeId.isEmpty || item['node_id']?.toString() != nodeId ||
        item['config_format'] != 'sudoku-json') return null;
    dynamic raw = item['config'];
    if (raw is! String || raw.isEmpty || raw.length > 16384) return null;
    try {
      raw = jsonDecode(raw);
      if (raw is! Map<String, dynamic> ||
          raw['mode'] != 'client' || raw['transport'] != 'tcp') return null;
      final endpoint = raw['server_address'];
      final key = raw['key'];
      if (endpoint is! String || endpoint.length > 300 ||
          key is! String ||
          !RegExp(r'^(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{128})$')
              .hasMatch(key)) return null;
      final parsed = Uri.tryParse('tcp://$endpoint');
      if (parsed == null || parsed.userInfo.isNotEmpty ||
          parsed.host.isEmpty || !parsed.hasPort ||
          parsed.port < 1 || parsed.port > 65535 ||
          parsed.path.isNotEmpty ||
          parsed.query.isNotEmpty || parsed.fragment.isNotEmpty) return null;
      // Fail closed on unsupported or intentionally weakened crypto.
      if (raw['aead'] != 'chacha20-poly1305' &&
          raw['aead'] != 'aes-128-gcm') return null;
      if (raw['enable_pure_downlink'] != true) return null;
      final ascii = raw['ascii'];
      if (ascii != 'prefer_entropy' && ascii != 'prefer_ascii') return null;
      final paddingMin = raw['padding_min'], paddingMax = raw['padding_max'];
      if (paddingMin is! int || paddingMax is! int ||
          paddingMin < 0 || paddingMax > 100 || paddingMax < paddingMin) {
        return null;
      }
      final mask = raw['httpmask'];
      if (mask is! Map || mask['disable'] != false ||
          mask['mode'] != 'auto') return null;
      if (raw['multiplex'] != 'off') return null;
      // Keep the original node-approved obfuscation settings, but never
      // accept controller, routing or server-mode instructions in a user
      // profile. Only known fields will be serialized for the core.
      return SudokuClientProfile(
        nodeId: nodeId, host: parsed.host, port: parsed.port,
        config: Map<String, dynamic>.from(raw),
      );
    } catch (_) {
      return null;
    }
  }

  /// Keep an explicitly chosen node when it has a valid delivered profile.
  /// If the panel still lists a legacy Sudoku node without a deliverable
  /// identity, use only another ONLINE node from the SAME country whose
  /// profile was actually issued to this subscription. Never invent keys or
  /// silently cross country boundaries.
  static SudokuClientProfile? resolveDeliveredProfile({
    required String requestedNodeId,
    required List<Map<String, dynamic>> items,
    required AppServerInventory? inventory,
  }) {
    final direct = items.where(
      (item) => item['node_id']?.toString() == requestedNodeId,
    ).toList(growable: false);
    if (direct.isNotEmpty) {
      // Duplicate or malformed records are not a reason to change servers.
      return direct.length == 1
          ? fromItem(direct.single, requestedNodeId)
          : null;
    }
    final servers = inventory?.servers;
    if (servers == null) return null;
    AppServer? requested;
    for (final server in servers) {
      if (server.id == requestedNodeId) {
        requested = server;
        break;
      }
    }
    if (requested == null) return null;
    final alternatives = servers.where(
      (server) => server.id != requestedNodeId &&
          server.nodeOnline &&
          server.countryCode.toUpperCase() ==
              requested!.countryCode.toUpperCase(),
    ).toList(growable: false)
      ..sort((a, b) {
        final ap = a.latencyMs ?? 1000000;
        final bp = b.latencyMs ?? 1000000;
        final latency = ap.compareTo(bp);
        return latency != 0 ? latency : a.id.compareTo(b.id);
      });
    for (final candidate in alternatives) {
      final matches = items.where(
        (item) => item['node_id']?.toString() == candidate.id,
      ).toList(growable: false);
      if (matches.length != 1) continue;
      final valid = fromItem(matches.single, candidate.id);
      if (valid != null) return valid;
    }
    return null;
  }

  /// Set a new loopback port, preserve the original per-user Sudoku split key
  /// and mask; pin the public server IPv4 before Windows TUN routing begins.
  Map<String, dynamic> runtimeConfig({
    required String serverIpv4,
    required int localPort,
  }) {
    if (localPort < 1024 || localPort > 65535) {
      throw const FormatException('SUDOKU_LOCAL_PORT_INVALID');
    }
    final mask = Map<String, dynamic>.from(config['httpmask'] as Map);
    return {
      'mode': 'client',
      'transport': 'tcp',
      'server_address': '$serverIpv4:$port',
      'local_address': '127.0.0.1',
      'local_port': localPort,
      'key': config['key'],
      'aead': config['aead'],
      'padding_min': config['padding_min'],
      'padding_max': config['padding_max'],
      'ascii': config['ascii'],
      'enable_pure_downlink': true,
      'multiplex': 'off',
      'httpmask': {
        'disable': false,
        'mode': 'auto',
        if (mask['tls'] is bool) 'tls': mask['tls'],
        if (mask['host'] is String &&
            (mask['host'] as String).trim().isNotEmpty)
          'host': mask['host'],
        if (mask['path_root'] is String &&
            (mask['path_root'] as String).trim().isNotEmpty)
          'path_root': mask['path_root'],
      },
      // Never fetch external rule lists or allow a direct egress decision
      // from the standalone core: the TUN's SOCKS proxy is full tunnel.
      'rule_urls': ['global'],
    };
  }
}
