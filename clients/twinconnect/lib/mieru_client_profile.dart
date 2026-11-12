import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'xray_endpoint_route.dart';

/// Validates the official mieru JSON delivered per subscription.
/// Do not persist plaintext user passwords or use this as a sing-box
/// outbound. The independent mieru CLI exposes a SOCKS5 loopback proxy.
class MieruClientProfile {
  const MieruClientProfile(this._config);
  final Map<String, dynamic> _config;

  Map<String, dynamic> get _server {
    final profile = (_config['profiles'] as List).single as Map;
    return Map<String, dynamic>.from((profile['servers'] as List).single as Map);
  }

  static bool _validDomain(String domain) {
    if (domain.length > 253 || domain.endsWith('.') ||
        !domain.contains('.')) return false;
    final label = RegExp(r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?

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
    final host = server['ipAddress'];
    final domain = server['domainName'];
    final hasDomain = domain is String && domain.isNotEmpty;
    final parsed = host is String ? InternetAddress.tryParse(host) : null;
    final hasIpv4 = parsed?.type == InternetAddressType.IPv4;
    if (!hasDomain && !hasIpv4) {
      throw const FormatException('MIERU_SERVER_ADDRESS_INVALID');
    }
    if (hasDomain && !_validDomain(domain)) {
      throw const FormatException('MIERU_SERVER_DOMAIN_INVALID');
    }
    if (hasIpv4) {
      XrayEndpointRoute.requirePublicIPv4(parsed!.address);
    } else if (host is String && host.isNotEmpty) {
      throw const FormatException('MIERU_SERVER_ADDRESS_INVALID');
    }
    // Official Mieru supports multiple bindings and portRange as well.
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
        final match = RegExp(r'^([0-9]{1,5})-([0-9]{1,5})
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
    // Freeze the exact effective dial IP from the pre-TUN DNS lookup.
    // Keep the source config and user authentication unchanged.
    final pinned = XrayEndpointRoute.requirePublicIPv4(resolvedEndpointIpv4);
    final cloned = jsonDecode(jsonEncode(_config)) as Map<String, dynamic>;
    final account = (cloned['profiles'] as List).single as Map;
    final activeServer = (account['servers'] as List).single as Map;
    activeServer['ipAddress'] = pinned;
    activeServer['domainName'] = '';
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
);
    return domain.split('.').every(label.hasMatch);
  }

  /// Official Mieru uses domainName in preference to ipAddress, when set.
  /// Resolve the effective dial endpoint before installing TUN routes.
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
          : InternetAddress.lookup(domain, type: InternetAddressType.IPv4)
      ).timeout(const Duration(seconds: 6));
      for (final address in addresses) {
        try {
          return XrayEndpointRoute.requirePublicIPv4(address.address);
        } on FormatException {
          // Reject private/loopback DNS answers; never bypass VPN for them.
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
    XrayEndpointRoute.requirePublicIPv4(host);
    return MieruClientProfile(decoded);
  }

  /// Only override local ephemeral ports; never change the delivered
  /// subscription username, password, server identity or protocol ports.
  Map<String, dynamic> runtimeConfig({
    required int socks5Port,
    required int rpcPort,
    required int httpProxyPort,
  }) {
    if (socks5Port < 1025 || socks5Port > 65535 ||
        rpcPort < 1025 || rpcPort > 65535 ||
        httpProxyPort < 1025 || httpProxyPort > 65535 ||
        socks5Port == rpcPort || socks5Port == httpProxyPort ||
        rpcPort == httpProxyPort) {
      throw const FormatException('MIERU_LOCAL_PORT_INVALID');
    }
    return <String, dynamic>{
      'profiles': _config['profiles'],
      'activeProfile': _config['activeProfile'],
      'socks5Port': socks5Port,
      'rpcPort': rpcPort,
      'httpProxyPort': httpProxyPort,
      'socks5ListenLAN': false,
      'httpProxyListenLAN': false,
      'loggingLevel': 'ERROR',
    };
  }
}
)
            .firstMatch(range);
        if (match != null) {
          final low = int.parse(match.group(1)!);
          final high = int.parse(match.group(2)!);
          hasRange = low >= 1 && high <= 65535 && low <= high;
        }
      }
      if (hasPort == hasRange ||
          !seen.add("${row['protocol']}:${hasPort ? port : range}")) {
        throw const FormatException('MIERU_BINDING_INVALID');
      }
    }
    if (decoded['socks5ListenLAN'] == true ||
        decoded['httpProxyListenLAN'] == true ||
        decoded.containsKey('dialer') || profile.containsKey('dialer')) {
      throw const FormatException('MIERU_UNTRUSTED_PROXY_SETTINGS');
    }
    XrayEndpointRoute.requirePublicIPv4(host);
    return MieruClientProfile(decoded);
  }

  /// Only override local ephemeral ports; never change the delivered
  /// subscription username, password, server identity or protocol ports.
  Map<String, dynamic> runtimeConfig({
    required int socks5Port,
    required int rpcPort,
    required int httpProxyPort,
  }) {
    if (socks5Port < 1025 || socks5Port > 65535 ||
        rpcPort < 1025 || rpcPort > 65535 ||
        httpProxyPort < 1025 || httpProxyPort > 65535 ||
        socks5Port == rpcPort || socks5Port == httpProxyPort ||
        rpcPort == httpProxyPort) {
      throw const FormatException('MIERU_LOCAL_PORT_INVALID');
    }
    return <String, dynamic>{
      'profiles': _config['profiles'],
      'activeProfile': _config['activeProfile'],
      'socks5Port': socks5Port,
      'rpcPort': rpcPort,
      'httpProxyPort': httpProxyPort,
      'socks5ListenLAN': false,
      'httpProxyListenLAN': false,
      'loggingLevel': 'ERROR',
    };
  }
}
);
    return domain.split('.').every(label.hasMatch);
  }

  /// Official Mieru uses domainName in preference to ipAddress, when set.
  /// Resolve the effective dial endpoint before installing TUN routes.
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
          : InternetAddress.lookup(domain, type: InternetAddressType.IPv4)
      ).timeout(const Duration(seconds: 6));
      for (final address in addresses) {
        try {
          return XrayEndpointRoute.requirePublicIPv4(address.address);
        } on FormatException {
          // Reject private/loopback DNS answers; never bypass VPN for them.
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
    XrayEndpointRoute.requirePublicIPv4(host);
    return MieruClientProfile(decoded);
  }

  /// Only override local ephemeral ports; never change the delivered
  /// subscription username, password, server identity or protocol ports.
  Map<String, dynamic> runtimeConfig({
    required int socks5Port,
    required int rpcPort,
    required int httpProxyPort,
  }) {
    if (socks5Port < 1025 || socks5Port > 65535 ||
        rpcPort < 1025 || rpcPort > 65535 ||
        httpProxyPort < 1025 || httpProxyPort > 65535 ||
        socks5Port == rpcPort || socks5Port == httpProxyPort ||
        rpcPort == httpProxyPort) {
      throw const FormatException('MIERU_LOCAL_PORT_INVALID');
    }
    return <String, dynamic>{
      'profiles': _config['profiles'],
      'activeProfile': _config['activeProfile'],
      'socks5Port': socks5Port,
      'rpcPort': rpcPort,
      'httpProxyPort': httpProxyPort,
      'socks5ListenLAN': false,
      'httpProxyListenLAN': false,
      'loggingLevel': 'ERROR',
    };
  }
}
