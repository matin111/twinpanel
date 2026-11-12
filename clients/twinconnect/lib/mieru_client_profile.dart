import 'dart:convert';
import 'dart:io';

/// Validates the official mieru JSON delivered per subscription.
/// Do not persist plaintext user passwords or use this as a sing-box
/// outbound. The independent mieru CLI exposes a SOCKS5 loopback proxy.
class MieruClientProfile {
  const MieruClientProfile(this._config);
  final Map<String, dynamic> _config;

  static MieruClientProfile fromItem(Map<String, dynamic> item) {
    if (item['config_format'] != 'mieru-json') {
      throw const FormatException('MIERU_PROFILE_FORMAT_INVALID');
    }
    final raw = item['config'];
    if (raw is! String || raw.isEmpty || raw.length > 65536) {
      throw const FormatException('MIERU_PROFILE_MISSING');
    }
    dynamic decoded;
    try { decoded = jsonDecode(raw); } catch (_) {
      throw const FormatException('MIERU_PROFILE_INVALID');
    }
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('MIERU_PROFILE_INVALID');
    }
    final profiles = decoded['profiles'];
    if (profiles is! List || profiles.length != 1 ||
        profiles.single is! Map<String, dynamic>) {
      throw const FormatException('MIERU_PROFILE_AMBIGUOUS');
    }
    final profile = Map<String, dynamic>.from(profiles.single as Map);
    final name = profile['profileName'];
    final user = profile['user'];
    final servers = profile['servers'];
    if (name is! String || name.isEmpty ||
        decoded['activeProfile'] != name || user is! Map ||
        user['name'] != name || user['password'] is! String ||
        (user['password'] as String).isEmpty ||
        servers is! List || servers.length != 1 || servers.single is! Map) {
      throw const FormatException('MIERU_IDENTITY_INVALID');
    }
    final server = Map<String, dynamic>.from(servers.single as Map);
    final bindings = server['portBindings'];
    final host = server['ipAddress'];
    if (host is! String || InternetAddress.tryParse(host)?.type !=
        InternetAddressType.IPv4 ||
        bindings is! List || bindings.isEmpty || bindings.length > 2) {
      throw const FormatException('MIERU_SERVER_INVALID');
    }
    final seen = <String>{};
    for (final dynamic row in bindings) {
      if (row is! Map || row['port'] is! int ||
          (row['port'] as int) < 1 || (row['port'] as int) > 65535 ||
          (row['protocol'] != 'TCP' && row['protocol'] != 'UDP') ||
          !seen.add(row['protocol'] as String)) {
        throw const FormatException('MIERU_BINDING_INVALID');
      }
    }
    if (decoded['socks5ListenLAN'] == true ||
        decoded['httpProxyListenLAN'] == true ||
        decoded.containsKey('dialer') || profile.containsKey('dialer')) {
      throw const FormatException('MIERU_UNTRUSTED_PROXY_SETTINGS');
    }
    return MieruClientProfile(decoded);
  }

  /// Only override local ephemeral ports; never change the delivered
  /// subscription username, password, server identity or protocol ports.
  Map<String, dynamic> runtimeConfig({
    required int socks5Port,
    required int rpcPort,
  }) {
    if (socks5Port < 1025 || socks5Port > 65535 ||
        rpcPort < 1025 || rpcPort > 65535 || socks5Port == rpcPort) {
      throw const FormatException('MIERU_LOCAL_PORT_INVALID');
    }
    return <String, dynamic>{
      'profiles': _config['profiles'],
      'activeProfile': _config['activeProfile'],
      'socks5Port': socks5Port,
      'rpcPort': rpcPort,
      'socks5ListenLAN': false,
      'loggingLevel': 'ERROR',
    };
  }
}
