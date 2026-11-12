/// Real, independently selectable Xray inbounds from TwinPanel's live
/// server_groups projection. Parsing does not create or start a VPN tunnel.
class XrayInboundProfile {
  const XrayInboundProfile({
    required this.id,
    required this.title,
    required this.uri,
    required this.serverId,
  });

  final String id;
  final String title;
  final Uri uri;
  final String serverId;

  static const supported = {
    'websocket_tls': ('ws', 'tls'),
    'xhttp_reality': ('xhttp', 'reality'),
    'tcp_tls': ('tcp', 'tls'),
  };

  static XrayInboundProfile? tryParse(
      Map<String, dynamic> row, String serverId) {
    final id = row['id'];
    final raw = row['uri'];
    if (id is! String || raw is! String ||
        !supported.containsKey(id) || serverId.isEmpty) {
      return null;
    }
    final uri = Uri.tryParse(raw);
    if (uri == null || uri.scheme != 'vless' ||
        uri.userInfo.isEmpty || uri.host.isEmpty ||
        !uri.hasPort || uri.port < 1 || uri.port > 65535) {
      return null;
    }
    final expected = supported[id]!;
    if (uri.queryParameters['type'] != expected.$1 ||
        uri.queryParameters['security'] != expected.$2 ||
        uri.queryParameters['encryption'] != 'none') {
      return null;
    }
    if ((id == 'websocket_tls' || id == 'xhttp_reality') &&
        !(uri.queryParameters['path'] ?? '').startsWith('/')) {
      return null;
    }
    if ((uri.queryParameters['sni'] ?? '').trim().isEmpty) {
      return null;
    }
    if (id == 'xhttp_reality' &&
        ((uri.queryParameters['pbk'] ?? '').isEmpty ||
            (uri.queryParameters['sid'] ?? '').isEmpty)) {
      return null;
    }
    return XrayInboundProfile(
      id: id,
      title: (row['title'] is String &&
              (row['title'] as String).trim().isNotEmpty)
          ? (row['title'] as String) : id,
      uri: uri,
      serverId: serverId,
    );
  }
}

class XrayServerProfiles {
  const XrayServerProfiles({required this.serverId, required this.inbounds});

  final String serverId;
  final List<XrayInboundProfile> inbounds;

  static List<XrayServerProfiles> fromResponse(Map<String, dynamic> json) {
    if (json['protocol'] != 'v2ray' || json['schema'] != 1) {
      throw const FormatException('XRAY_RESPONSE_INVALID');
    }
    final groups = json['server_groups'];
    if (groups is! List || groups.length > 200) {
      throw const FormatException('XRAY_SERVER_GROUPS_MISSING');
    }
    final result = <XrayServerProfiles>[];
    final seenNodes = <String>{};
    for (final group in groups) {
      if (group is! Map<String, dynamic>) {
        throw const FormatException('XRAY_SERVER_GROUP_INVALID');
      }
      final nodeId = group['node_id']?.toString() ?? '';
      if (!RegExp(r'^[1-9][0-9]{0,19}$').hasMatch(nodeId) ||
          !seenNodes.add(nodeId) || group['profiles'] is! List) {
        throw const FormatException('XRAY_SERVER_GROUP_INVALID');
      }
      final inbounds = <XrayInboundProfile>[];
      final seenProfiles = <String>{};
      for (final raw in group['profiles'] as List) {
        if (raw is! Map<String, dynamic>) continue;
        final inbound = XrayInboundProfile.tryParse(raw, nodeId);
        if (inbound != null && seenProfiles.add(inbound.id)) {
          inbounds.add(inbound);
        }
      }
      // A partly provisioned node may supply fewer than three real profiles.
      // Never manufacture a missing inbound from the first stored URI.
      result.add(XrayServerProfiles(
        serverId: nodeId,
        inbounds: List.unmodifiable(inbounds),
      ));
    }
    return List.unmodifiable(result);
  }
}
