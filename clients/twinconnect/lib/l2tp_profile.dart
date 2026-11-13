/// Immutable, validated Windows L2TP/IPsec account profile.
class L2tpProfile {
  const L2tpProfile({
    required this.nodeId,
    required this.server,
    required this.username,
    required this.password,
    required this.psk,
  });

  final int nodeId;
  final String server;
  final String username;
  final String password;
  final String psk;

  factory L2tpProfile.fromItem(Map<String, dynamic> item) {
    final id = int.tryParse((item['node_id'] ?? '').toString());
    final host = (item['server'] ?? item['server_ip'])?.toString().trim();
    final username = item['username'];
    final password = item['password'];
    final psk = item['psk'];
    if (id == null || id <= 0 || host == null ||
        !RegExp(r'^[A-Za-z0-9.-]{1,253}$').hasMatch(host) ||
        host.startsWith('-') || host.endsWith('.') ||
        host.contains('..')) {
      throw const FormatException('L2TP_ENDPOINT_INVALID');
    }
    bool secretOK(Object? value, int max) =>
        value is String && value.isNotEmpty && value.length <= max &&
        !value.contains(RegExp(r'[\x00-\x1f\x7f]'));
    if (!secretOK(username, 256) || !secretOK(password, 256) ||
        !secretOK(psk, 256)) {
      throw const FormatException('L2TP_CREDENTIALS_INVALID');
    }
    return L2tpProfile(
      nodeId: id, server: host, username: username as String,
      password: password as String, psk: psk as String,
    );
  }
}
