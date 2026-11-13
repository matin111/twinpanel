import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'xray_endpoint_route.dart';

/// Validates official Mieru JSON without altering the user's credentials.
/// The independent native Mieru core owns its own authenticated protocol.
class MieruClientProfile {
  const MieruClientProfile(this._config);
  final Map<String, dynamic> _config;

  Map<String, dynamic> get _server {
    final profile = (_config['profiles'] as List).single as Map;
    return Map<String, dynamic>.from((profile['servers'] as List).single as Map);
  }

  static bool _validDomain(String domain) {
    if (domain.length > 253 || domain.endsWith('.') ||
        !domain.contains('.')) {
      return false;
    }
    final label =
        RegExp(r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$');
    return domain.split('.').every(label.hasMatch);
  }

  /// Mieru prefers domainName over ipAddress when both are populated.
  /// Resolve and pin the true dial endpoint before installing TUN routes.
  Future<String> resolveEndpointIpv4({
    Future<List<InternetAddress>> Function(String)? lookup,
  }) async {
    final server = _server;
    final domain = (server['domainName'] as String?) ?? '';
    if (domain.isEmpty) {
      return XrayEndpointRoute.requirePublicIPv4(server['ipAddress'] as String);
    }
    if (!_validDomain(domain)) {
      throw const FormatException('MIERU_SERVER_DOMAIN_INVALID');
    }
    try {
      final addresses = await (lookup != null
              ? lookup(domain)
              : InternetAddress.lookup(domain, type: InternetAddressType.IPv4))
          .timeout(const Duration(seconds: 6));
      for (final address in addresses) {
        try {
          return XrayEndpointRoute.requirePublicIPv4(address.address);
        } on FormatException {
          // A private or reserved DNS answer must not bypass TUN.
        }
      }
    } catch (_) {
      throw const FormatException('MIERU_SERVER_DNS_UNAVAILABLE');
    }
    throw const FormatException('MIERU_SERVER_DNS_UNAVAILABLE');
  }

  static MieruClientProfile fromItem(Map<String, dynamic> item) {
    if (item['config_format'] != 'mieru-json') {
      throw const FormatException('MIERU_PROFILE_FORMAT_INVALID');
    }
    final raw = item['config'];
    if (raw is! String || raw.isEmpty || raw.length > 65536) {
      throw const FormatException('MIERU_PROFILE_MISSING');
    }
    dynamic decoded;
    try {
      decoded = jsonDecode(raw);
    } catch (_) {
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
        servers is! List || servers.length != 1 ||
        servers.single is! Map) {
      throw const FormatException('MIERU_IDENTITY_INVALID');
    }
    final server = Map<String, dynamic>.from(servers.single as Map);
    final rawIp = server['ipAddress'];
    final rawDomain = server['domainName'];
    if (rawDomain != null && rawDomain is! String) {
      throw const FormatException('MIERU_SERVER_DOMAIN_INVALID');
    }
    final domain = rawDomain is String ? rawDomain : '';
    final ip = rawIp is String ? InternetAddress.tryParse(rawIp) : null;
    final hasIpv4 = ip?.type == InternetAddressType.IPv4;
    if (!hasIpv4 && domain.isEmpty) {
      throw const FormatException('MIERU_SERVER_ADDRESS_INVALID');
    }
    if (domain.isNotEmpty && !_validDomain(domain)) {
      throw const FormatException('MIERU_SERVER_DOMAIN_INVALID');
    }
    if (hasIpv4) {
      XrayEndpointRoute.requirePublicIPv4(ip!.address);
    } else if (rawIp is String && rawIp.isNotEmpty) {
      throw const FormatException('MIERU_SERVER_ADDRESS_INVALID');
    }

    // Official Mieru supports portRange and multiple bindings, not only
    // a fixed pair of TCP/UDP ports. Reject duplicates and unsafe ranges.
    final bindings = server['portBindings'];
    if (bindings is! List || bindings.isEmpty || bindings.length > 32) {
      throw const FormatException('MIERU_SERVER_BINDINGS_INVALID');
    }
    final seen = <String>{};
    for (final dynamic row in bindings) {
      if (row is! Map ||
          (row['protocol'] != 'TCP' && row['protocol'] != 'UDP')) {
        throw const FormatException('MIERU_BINDING_INVALID');
      }
      final port = row['port'];
      final range = row['portRange'];
      final hasPort = port is int && port >= 1 && port <= 65535;
      var hasRange = false;
      if (range is String) {
        final match =
            RegExp(r'^([0-9]{1,5})-([0-9]{1,5})$').firstMatch(range);
        if (match != null) {
          final low = int.parse(match.group(1)!);
          final high = int.parse(match.group(2)!);
          hasRange = low >= 1 && high <= 65535 && low <= high;
        }
      }
      final identity = row['protocol'].toString() + ':' +
          (hasPort ? port : range).toString();
      if (hasPort == hasRange || !seen.add(identity)) {
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

  /// Pin the pre-TUN verified destination to both the core and the /32
  /// route exception. This makes Mieru's DNS preference deterministic.
  /// The source profile and account identity remain unchanged.
  Map<String, dynamic> runtimeConfig({
    required int socks5Port,
    required int rpcPort,
    required int httpProxyPort,
    required String resolvedEndpointIpv4,
  }) {
    if (socks5Port < 1025 || socks5Port > 65535 ||
        rpcPort < 1025 || rpcPort > 65535 ||
        httpProxyPort < 1025 || httpProxyPort > 65535 ||
        socks5Port == rpcPort || socks5Port == httpProxyPort ||
        rpcPort == httpProxyPort) {
      throw const FormatException('MIERU_LOCAL_PORT_INVALID');
    }
    final pinned = XrayEndpointRoute.requirePublicIPv4(resolvedEndpointIpv4);
    final cloned = jsonDecode(jsonEncode(_config)) as Map<String, dynamic>;
    final account = (cloned['profiles'] as List).single as Map;
    final server = (account['servers'] as List).single as Map;
    server['ipAddress'] = pinned;
    server['domainName'] = '';
    return <String, dynamic>{
      'profiles': cloned['profiles'],
      'activeProfile': cloned['activeProfile'],
      'socks5Port': socks5Port,
      'rpcPort': rpcPort,
      'httpProxyPort': httpProxyPort,
      'socks5ListenLAN': false,
      'httpProxyListenLAN': false,
      'loggingLevel': 'ERROR',
    };
  }
}
