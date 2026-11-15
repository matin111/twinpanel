import 'dart:convert';


/// The sing-box family uses one engine process. Profiles may be native
/// outbound JSON or a full native config; opaque links are deliberately not
/// converted without a protocol-specific, verified parser.
///
/// Validating a candidate NEVER implies that a native Windows TUN engine is
/// installed, started or connected.
class SingBoxProfileValidator {
  static const Set<String> familyCodes = {
    'hysteria2', 'tuic', 'anytls', 'naive',
    'shadowtls', 'snell', 'socks5',
  };

  static const Map<String, String> outboundTypes = {
    'hysteria2': 'hysteria2',
    'tuic': 'tuic',
    'anytls': 'anytls',
    'naive': 'naive',
    'shadowtls': 'shadowtls',
    'snell': 'snell',
    'socks5': 'socks',
  };

  static bool supportsFamily(String protocolCode) =>
      familyCodes.contains(protocolCode);

  /// Only JSON-native outbounds are accepted. No credentials or entire
  /// serialized payloads appear in thrown exceptions.
  /// A ShadowTLS client needs an authenticated inner Shadowsocks outbound
  /// detoured through one ShadowTLS wrapper. Do not execute panel-provided
  /// inbound, DNS, routes, selectors, experimental settings, or extra outbounds.
  /// Return only the two validated outbounds in deterministic order, so the
  /// sing_box plugin selects the real Shadowsocks proxy as its first server.
  /// Keep the authenticated inner Shadowsocks stream paired with exactly
  /// one ShadowTLS detour. Other app-level routes/DNS/inbounds are discarded.
  static List<Map<String, dynamic>> validateShadowTlsChain(
      Map<String, dynamic> item) {
    dynamic candidate = item['config'] ?? item['singbox_outbound'] ??
        item['outbound'];
    if (candidate == null && item['outbounds'] is List) {
      candidate = {'outbounds': item['outbounds']};
    }
    if (candidate is String) {
      if (candidate.length > 131072) {
        throw const FormatException('SHADOWTLS_CONFIG_TOO_LARGE');
      }
      try {
        candidate = jsonDecode(candidate);
      } catch (_) {
        throw const FormatException('SHADOWTLS_CONFIG_INVALID');
      }
    }
    if (candidate is! Map || candidate['outbounds'] is! List) {
      throw const FormatException('SHADOWTLS_CHAIN_REQUIRED');
    }
    final all = candidate['outbounds'] as List;
    if (all.length > 16) {
      throw const FormatException('SHADOWTLS_CHAIN_AMBIGUOUS');
    }
    final wrappers = all.whereType<Map>()
        .where((out) => out['type'] == 'shadowtls').toList();
    final shadowsocks = all.whereType<Map>()
        .where((out) => out['type'] == 'shadowsocks').toList();
    if (wrappers.length != 1 || shadowsocks.length != 1) {
      throw const FormatException('SHADOWTLS_CHAIN_AMBIGUOUS');
    }
    final wrapper = Map<String, dynamic>.from(wrappers.single);
    final inner = Map<String, dynamic>.from(shadowsocks.single);
    final wrapperTag = wrapper['tag'];
    if (wrapperTag is! String || wrapperTag.isEmpty ||
        inner['detour'] != wrapperTag || wrapperTag == inner['tag']) {
      throw const FormatException('SHADOWTLS_DETOUR_INVALID');
    }
    final version = wrapper['version'];
    if (version is! int || version < 1 || version > 3) {
      throw const FormatException('SHADOWTLS_VERSION_UNSUPPORTED');
    }
    if (version >= 2 &&
        (wrapper['password'] is! String ||
            (wrapper['password'] as String).isEmpty)) {
      throw const FormatException('SHADOWTLS_PASSWORD_MISSING');
    }
    final host = wrapper['server'];
    final port = wrapper['server_port'];
    if (host is! String || host.isEmpty || host.length > 255 ||
        host.contains(' ') || host.contains('/') ||
        port is! int || port < 1 || port > 65535) {
      throw const FormatException('SHADOWTLS_ENDPOINT_INVALID');
    }

    // A valid sing-box ShadowTLS outbound has a TLS object, but does not
    // require explicit "enabled" or "server_name". Legacy panel payloads
    // can provide SNI alongside the wrapper instead. Keep full certificate
    // verification; never set insecure=true or disable SNI.
    final rawTls = wrapper['tls'];
    if (rawTls != null && rawTls is! Map) {
      throw const FormatException('SHADOWTLS_TLS_INVALID');
    }
    final tls = rawTls == null
        ? <String, dynamic>{}
        : Map<String, dynamic>.from(rawTls);
    if (tls['enabled'] == false || tls['insecure'] == true ||
        tls['disable_sni'] == true) {
      throw const FormatException('SHADOWTLS_TLS_INVALID');
    }
    final explicitSni = tls['server_name'] ?? wrapper['sni'] ?? item['sni'];
    if (explicitSni != null) {
      if (explicitSni is! String || explicitSni.trim().isEmpty ||
          explicitSni.length > 253 || explicitSni.contains(' ') ||
          explicitSni.contains('/')) {
        throw const FormatException('SHADOWTLS_TLS_INVALID');
      }
      tls['server_name'] = explicitSni;
    }
    tls['enabled'] = true;
    wrapper['tls'] = tls;
    wrapper.remove('sni');

    if (inner['method'] is! String ||
        (inner['method'] as String).isEmpty ||
        inner['password'] is! String ||
        (inner['password'] as String).isEmpty) {
      throw const FormatException('SHADOWTLS_INNER_INVALID');
    }
    for (final outbound in [wrapper, inner]) {
      if (outbound.keys.any((key) => const {
        'inbounds', 'outbounds', 'dns', 'route', 'experimental',
        'log', 'selector', 'rules', 'default',
      }.contains(key))) {
        throw const FormatException('SHADOWTLS_UNTRUSTED_APP_CONFIG');
      }
    }
    return [inner, wrapper];
  }

  static Map<String, dynamic> validateOutbound({
    required String protocolCode,
    required Map<String, dynamic> item,
  }) {
    final expected = outboundTypes[protocolCode];
    if (expected == null) {
      throw const FormatException('NOT_SINGBOX_PROTOCOL');
    }
    dynamic candidate = item['outbound'];
    candidate ??= item['singbox_outbound'];
    candidate ??= item['config'];
    if (candidate is String) {
      if (candidate.length > 131072) {
        throw const FormatException('SINGBOX_CONFIG_TOO_LARGE');
      }
      try {
        candidate = jsonDecode(candidate);
      } on FormatException {
        throw const FormatException('SINGBOX_CONFIG_INVALID');
      }
    }
    if (candidate is! Map) {
      throw const FormatException('SINGBOX_JSON_PROFILE_REQUIRED');
    }
    var object = Map<String, dynamic>.from(candidate);
    // TwinPanel may deliver a full generated sing-box config rather than
    // an isolated outbound. Never execute its routing, DNS, TUN, logging,
    // or experimental sections: extract only one matching native outbound.
    // Multiple matching outbounds are ambiguous and must fail closed.
    if (object['outbounds'] is List) {
      final matches = (object['outbounds'] as List<dynamic>)
          .whereType<Map>()
          .where((row) => row['type'] == expected).toList(growable: false);
      if (matches.length != 1) {
        throw const FormatException('SINGBOX_OUTBOUND_AMBIGUOUS');
      }
      object = Map<String, dynamic>.from(matches.single);
    }
    if (object.containsKey('outbounds') || object.containsKey('inbounds') ||
        object.containsKey('dns') || object.containsKey('route') ||
        object.containsKey('experimental') || object.containsKey('log')) {
      // Never let a subscription profile override local routing/security.
      throw const FormatException('SINGBOX_UNTRUSTED_APP_CONFIG');
    }
    if (object['type'] != expected) {
      throw const FormatException('SINGBOX_PROTOCOL_MISMATCH');
    }
    final server = object['server'];
    final port = object['server_port'];
    if (server is! String || server.isEmpty || server.length > 255 ||
        server.contains('/') || server.contains(' ') ||
        port is! int || port < 1 || port > 65535) {
      throw const FormatException('SINGBOX_ENDPOINT_INVALID');
    }
    if (protocolCode == 'snell') {
      // sing-box 1.14 implements Snell v4 TCP and v6, but not the
      // Snell v5 QUIC proxy. Never silently choose a different version.
      final version = object['version'];
      if (version != 4 && version != 6) {
        throw const FormatException('SNELL_VERSION_UNSUPPORTED');
      }
      final psk = object['psk'];
      if (psk is! String || psk.isEmpty ||
          (version == 6 &&
              (utf8.encode(psk).length < 12 ||
               utf8.encode(psk).length > 255))) {
        throw const FormatException('SNELL_PSK_REQUIRED');
      }
      if (object['password'] != null) {
        throw const FormatException('SNELL_WRONG_CREDENTIAL_FIELD');
      }
      final network = object['network'];
      if (network != null && network != 'tcp' && network != 'udp') {
        throw const FormatException('SNELL_NETWORK_UNSUPPORTED');
      }
    }
    if (protocolCode == 'socks5') {
      // Do not quietly downgrade the entitled SOCKS5 account to SOCKS4
      // or attempt an unauthenticated session with incomplete credentials.
      if (object['version'] != '5') {
        throw const FormatException('SOCKS5_VERSION_INVALID');
      }
      final user = object['username'];
      final password = object['password'];
      if (user is! String || password is! String ||
          user.isEmpty || password.isEmpty ||
          user.length > 255 || password.length > 255) {
        throw const FormatException('SOCKS5_ACCOUNT_AUTH_INVALID');
      }
      final transport = object['network'];
      if (transport != null && transport != 'tcp') {
        // This VPN uses TCP CONNECT and HTTPS-over-TCP for protected DNS.
        // A UDP-only SOCKS5 account cannot carry that traffic.
        throw const FormatException('SOCKS5_TCP_TRANSPORT_REQUIRED');
      }
    }
    if (protocolCode == 'hysteria2' || protocolCode == 'tuic' ||
        protocolCode == 'anytls' || protocolCode == 'naive') {
      final rawTls = object['tls'];
      if (rawTls is! Map) {
        throw const FormatException('SINGBOX_TLS_REQUIRED');
      }
      final tls = Map<String, dynamic>.from(rawTls);
      if (tls['enabled'] == false || tls['insecure'] == true ||
          tls['disable_sni'] == true) {
        throw const FormatException('SINGBOX_TLS_UNSAFE');
      }
      // Some panel profiles omit "enabled" but provide a valid TLS block.
      // Make TLS explicit rather than accidentally dialing without TLS.
      tls['enabled'] = true;
      object['tls'] = tls;
    }
    // ShadowTLS detours cannot safely be flattened into one outbound.
    if (protocolCode == 'shadowtls') {
      throw const FormatException('SINGBOX_SHADOWTLS_CHAIN_REQUIRED');
    }
    // A copy keeps caller-owned profile data untouched.
    return object;
  }
}
