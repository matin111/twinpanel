/// Strict selection of a Cisco / OpenConnect endpoint from the existing
/// subscription profile. Never manufacture a credential or trust a host
/// supplied by an unentitled entry.
class CiscoOpenConnectProfile {
  const CiscoOpenConnectProfile({
    required this.host,
    required this.port,
    required this.username,
    required this.password,
    this.serverCertificate,
  });

  final String host;
  final int port;
  final String username;
  final String password;
  final String? serverCertificate;

  String get gateway => host.contains(':') ? '[$host]:$port' : '$host:$port';

  static CiscoOpenConnectProfile fromItem(Map<String, dynamic> item) {
    String? field(List<String> keys) {
      for (final key in keys) {
        final value = item[key];
        if (value is String && value.trim().isNotEmpty) return value.trim();
      }
      return null;
    }

    final rawHost = field(['host', 'server', 'server_ip', 'endpoint']);
    final username = field(['username', 'user']);
    // Preserve password whitespace exactly: it may be part of the secret.
    final password = item['password'];
    final rawPort = item['port'] ?? item['server_port'] ?? 443;
    final port = rawPort is int ? rawPort
        : rawPort is String ? int.tryParse(rawPort) : null;

    if (rawHost == null || username == null || password is! String ||
        password.isEmpty || password.length > 4096 ||
        port == null || port < 1 || port > 65535) {
      throw const FormatException('CISCO_PROFILE_MISSING_FIELDS');
    }
    // Accept literal IPv4, bracketed IPv6, or DNS labels, not arbitrary URLs,
    // shell tokens, redirects, paths, whitespace or embedded credentials.
    final host = rawHost;
    final safeHost = RegExp(r'^[a-zA-Z0-9.-]{1,253}$').hasMatch(host) &&
        !host.startsWith('-') && !host.endsWith('.') &&
        !host.contains('..');
    if (!safeHost ||
        !RegExp(r'^[^\x00-\x1f\x7f]{1,256}$').hasMatch(username) ||
        username.startsWith('-') ||
        password.contains('\n') || password.contains('\r') ||
        password.contains('\x00')) {
      throw const FormatException('CISCO_PROFILE_UNSAFE');
    }
    final pinned = field(['servercert', 'server_certificate']);
    if (pinned != null &&
        !RegExp(r'^(sha256:[0-9a-fA-F]{64}|sha1:[0-9a-fA-F]{40})\$')
            .hasMatch(pinned)) {
      throw const FormatException('CISCO_CERT_PIN_INVALID');
    }
    return CiscoOpenConnectProfile(
        host: host, port: port, username: username, password: password,
        serverCertificate: pinned);
  }
}
