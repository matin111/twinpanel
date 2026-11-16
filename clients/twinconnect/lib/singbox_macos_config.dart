import 'dart:convert';

import 'singbox_profile_validator.dart';

/// Builds the in-process Libbox configuration for a signed macOS PacketTunnel.
///
/// This is *only* profile preparation. Calling compose() never configures
/// NEPacketTunnelFlow, starts Libbox, or verifies an internet connection.
/// The resulting structure contains secrets: do not persist or log it.
class SingBoxMacConfig {
  const SingBoxMacConfig._();

  static Map<String, dynamic> composeHysteria2({
    required Map<String, dynamic> item,
  }) {
    final candidate = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'hysteria2',
      item: item,
    );
    final password = candidate['password'];
    final server = candidate['server'] as String;
    final rawTls = candidate['tls'];
    if (password is! String || password.isEmpty ||
        password.length > 4096 || rawTls is! Map) {
      throw const FormatException('MAC_HYSTERIA2_CREDENTIALS_INVALID');
    }
    final tls = Map<String, dynamic>.from(rawTls);
    // Never let an untrusted panel record disable TLS certificate checks.
    if (tls['enabled'] != true || tls['insecure'] == true ||
        tls['disable_sni'] == true || tls['utls'] != null) {
      throw const FormatException('MAC_HYSTERIA2_TLS_UNSAFE');
    }
    final sni = tls['server_name'];
    if (sni != null && (sni is! String || sni.trim().isEmpty ||
        sni.contains('/') || sni.contains(' '))) {
      throw const FormatException('MAC_HYSTERIA2_SNI_INVALID');
    }
    final obfs = candidate['obfs'];
    if (obfs != null &&
        (obfs is! Map || obfs['type'] != 'salamander' ||
         obfs['password'] is! String ||
         (obfs['password'] as String).isEmpty)) {
      throw const FormatException('MAC_HYSTERIA2_OBFS_INVALID');
    }
    final up = candidate['up_mbps'];
    final down = candidate['down_mbps'];
    if ((up != null && (up is! int || up < 1 || up > 100000)) ||
        (down != null && (down is! int || down < 1 || down > 100000))) {
      throw const FormatException('MAC_HYSTERIA2_RATE_INVALID');
    }

    // Build from an allowlist, discarding any injected routing, detour,
    // certificate-bypass or local inbound configuration from the panel.
    final outbound = <String, dynamic>{
      'type': 'hysteria2',
      'tag': 'proxy',
      'server': server,
      'server_port': candidate['server_port'],
      'password': password,
      if (obfs != null) 'obfs': Map<String, dynamic>.from(obfs),
      if (up != null) 'up_mbps': up,
      if (down != null) 'down_mbps': down,
      'tls': <String, dynamic>{
        'enabled': true,
        'server_name': sni ?? server,
      },
    };

    return _envelope(outbound);
  }

  /// TUIC uses the native sing-box QUIC outbound in the same guarded TUN.
  static Map<String, dynamic> composeTuic({required Map<String, dynamic> item}) {
    final candidate = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'tuic', item: item,
    );
    final uuid = candidate['uuid'];
    final secret = candidate['password'];
    final uuidPattern = RegExp(
      r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
    );
    if (uuid is! String || uuid.length != 36 || !uuidPattern.hasMatch(uuid) ||
        secret is! String || secret.isEmpty || secret.length > 4096) {
      throw const FormatException('MAC_TUIC_CREDENTIALS_INVALID');
    }
    final tls = Map<String, dynamic>.from(candidate['tls'] as Map);
    if (tls['enabled'] != true || tls['insecure'] == true ||
        tls['disable_sni'] == true || tls['utls'] != null ||
        candidate['zero_rtt_handshake'] == true ||
        candidate['udp_over_stream'] == true) {
      throw const FormatException('MAC_TUIC_TLS_OR_REPLAY_UNSAFE');
    }
    final server = candidate['server'] as String;
    final sni = tls['server_name'] ?? server;
    if (sni is! String || sni.isEmpty || sni.length > 255 ||
        sni.contains('/') || sni.contains(' ')) {
      throw const FormatException('MAC_TUIC_SNI_INVALID');
    }
    final congestion = candidate['congestion_control'];
    if (congestion != null &&
        !const ['cubic', 'new_reno', 'bbr'].contains(congestion)) {
      throw const FormatException('MAC_TUIC_CONGESTION_INVALID');
    }
    final udpMode = candidate['udp_relay_mode'];
    if (udpMode != null && !const ['native', 'quic'].contains(udpMode)) {
      throw const FormatException('MAC_TUIC_UDP_MODE_INVALID');
    }
    final outbound = <String, dynamic>{
      'type': 'tuic',
      'tag': 'proxy',
      'server': server,
      'server_port': candidate['server_port'],
      'uuid': uuid,
      'password': secret,
      if (congestion != null) 'congestion_control': congestion,
      if (udpMode != null) 'udp_relay_mode': udpMode,
      'zero_rtt_handshake': false,
      'tls': <String, dynamic>{'enabled': true, 'server_name': sni},
    };
    return _envelope(outbound);
  }

  /// AnyTLS 1.12+ uses the shared Libbox TUN with remote DNS.
  static Map<String, dynamic> composeAnyTls({
    required Map<String, dynamic> item,
  }) {
    final candidate = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'anytls',
      item: item,
    );
    final password = candidate['password'];
    final server = candidate['server'] as String;
    if (password is! String || password.isEmpty ||
        password.length > 4096) {
      throw const FormatException('MAC_ANYTLS_CREDENTIALS_INVALID');
    }
    final rawTls = candidate['tls'];
    if (rawTls is! Map) {
      throw const FormatException('MAC_ANYTLS_TLS_REQUIRED');
    }
    final tls = Map<String, dynamic>.from(rawTls);
    if (tls['enabled'] != true || tls['insecure'] == true ||
        tls['disable_sni'] == true || tls['utls'] != null) {
      throw const FormatException('MAC_ANYTLS_TLS_UNSAFE');
    }
    final sni = tls['server_name'] ?? server;
    if (sni is! String || sni.isEmpty || sni.length > 255 ||
        sni.contains('/') || sni.contains(' ')) {
      throw const FormatException('MAC_ANYTLS_SNI_INVALID');
    }
    final interval = candidate['idle_session_check_interval'];
    final timeout = candidate['idle_session_timeout'];
    final minIdle = candidate['min_idle_session'];
    final durationPattern = RegExp(r'^[1-9][0-9]{0,3}(s|m)$');
    if ((interval != null &&
            (interval is! String || !durationPattern.hasMatch(interval))) ||
        (timeout != null &&
            (timeout is! String || !durationPattern.hasMatch(timeout))) ||
        (minIdle != null &&
            (minIdle is! int || minIdle < 0 || minIdle > 512))) {
      throw const FormatException('MAC_ANYTLS_IDLE_SETTINGS_INVALID');
    }
    final outbound = <String, dynamic>{
      'type': 'anytls',
      'tag': 'proxy',
      'server': server,
      'server_port': candidate['server_port'],
      'password': password,
      if (interval != null) 'idle_session_check_interval': interval,
      if (timeout != null) 'idle_session_timeout': timeout,
      if (minIdle != null) 'min_idle_session': minIdle,
      'tls': <String, dynamic>{
        'enabled': true,
        'server_name': sni,
      },
    };
    return _envelope(outbound);
  }

  /// NaiveProxy on macOS uses the official sing-box Cronet-enabled Libbox.
  /// Preserve only reviewed fields; never accept TLS bypass or direct routes.
  static Map<String, dynamic> composeNaive({
    required Map<String, dynamic> item,
  }) {
    final candidate = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'naive', item: item,
    );
    final username = candidate['username'];
    final password = candidate['password'];
    if (username is! String || username.isEmpty || username.length > 1024 ||
        password is! String || password.isEmpty || password.length > 4096) {
      throw const FormatException('MAC_NAIVE_CREDENTIALS_INVALID');
    }
    final rawTls = candidate['tls'];
    if (rawTls is! Map) {
      throw const FormatException('MAC_NAIVE_TLS_REQUIRED');
    }
    final tls = Map<String, dynamic>.from(rawTls);
    final server = candidate['server'] as String;
    final sni = tls['server_name'] ?? server;
    if (tls['enabled'] != true || tls['insecure'] == true ||
        tls['disable_sni'] == true || tls['utls'] != null ||
        tls['reality'] != null ||
        sni is! String || sni.isEmpty || sni.length > 255 ||
        sni.contains('/') || sni.contains(' ')) {
      throw const FormatException('MAC_NAIVE_TLS_UNSAFE');
    }
    // Naive concurrency > 0 changes traffic-analysis resistance. Treat
    // server-supplied overrides as unsafe instead of quietly enabling them.
    final concurrent = candidate['insecure_concurrency'];
    if (concurrent != null && concurrent != 0) {
      throw const FormatException('MAC_NAIVE_CONCURRENCY_UNSAFE');
    }
    final quic = candidate['quic'];
    final udpOverTcp = candidate['udp_over_tcp'];
    if ((quic != null && quic is! bool) ||
        (udpOverTcp != null && udpOverTcp is! bool)) {
      throw const FormatException('MAC_NAIVE_TRANSPORT_INVALID');
    }
    // UDP support is available only if the actual server supports UoT and
    // the panel explicitly advertises that setting; never invent it.
    final congestion = candidate['quic_congestion_control'];
    if (congestion != null && (quic != true ||
        !const ['bbr', 'bbr2', 'cubic', 'reno'].contains(congestion))) {
      throw const FormatException('MAC_NAIVE_QUIC_CONGESTION_INVALID');
    }
    final headers = candidate['extra_headers'];
    if (headers != null && headers is Map && headers.isNotEmpty) {
      throw const FormatException('MAC_NAIVE_CUSTOM_HEADERS_NOT_SUPPORTED');
    }
    final outbound = <String, dynamic>{
      'type': 'naive',
      'tag': 'proxy',
      'server': server,
      'server_port': candidate['server_port'],
      'username': username,
      'password': password,
      'insecure_concurrency': 0,
      if (quic == true) 'quic': true,
      if (udpOverTcp == true) 'udp_over_tcp': true,
      if (congestion != null) 'quic_congestion_control': congestion,
      'tls': <String, dynamic>{
        'enabled': true,
        'server_name': sni,
      },
    };
    return _envelope(outbound);
  }

  /// Snell v4/v6 outbound. Never invent a server version or credentials.
  /// This is offline configuration preparation, not a verified connection.
  static Map<String, dynamic> composeSnell({
    required Map<String, dynamic> item,
  }) {
    final candidate = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'snell', item: item,
    );
    final version = candidate['version'];
    final psk = candidate['psk'];
    if (version != 4 && version != 6) {
      throw const FormatException('MAC_SNELL_VERSION_UNSUPPORTED');
    }
    if (psk is! String || psk.isEmpty ||
        psk.length > 4096 ||
        (version == 6 &&
            (utf8.encode(psk).length < 12 || utf8.encode(psk).length > 255))) {
      throw const FormatException('MAC_SNELL_PSK_INVALID');
    }
    const keys = {
      'type', 'tag', 'server', 'server_port', 'version', 'psk',
      'userkey', 'reuse', 'network', 'obfs_mode', 'obfs_host', 'mode',
    };
    if (candidate.keys.any((key) => !keys.contains(key))) {
      throw const FormatException('MAC_SNELL_UNREVIEWED_FIELD');
    }
    final userkey = candidate['userkey'];
    if (userkey != null &&
        (userkey is! String || utf8.encode(userkey).length > 255)) {
      throw const FormatException('MAC_SNELL_USERKEY_INVALID');
    }
    final reuse = candidate['reuse'];
    final network = candidate['network'];
    if ((reuse != null && reuse is! bool) ||
        (network != null && network != 'tcp' && network != 'udp')) {
      throw const FormatException('MAC_SNELL_TRANSPORT_INVALID');
    }
    final obfsMode = candidate['obfs_mode'];
    final obfsHost = candidate['obfs_host'];
    final mode = candidate['mode'];
    if (version == 4) {
      if (mode != null ||
          (obfsMode != null && !const ['none', 'http'].contains(obfsMode)) ||
          (obfsHost != null &&
              (obfsMode != 'http' || obfsHost is! String ||
               obfsHost.isEmpty || obfsHost.length > 255 ||
               obfsHost.contains('/') || obfsHost.contains(' ')))) {
        throw const FormatException('MAC_SNELL_OBFS_INVALID');
      }
    } else {
      if (obfsMode != null || obfsHost != null ||
          (mode != null && !const ['default', 'unshaped'].contains(mode))) {
        throw const FormatException('MAC_SNELL_MODE_INVALID');
      }
    }
    return _envelope(<String, dynamic>{
      'type': 'snell',
      'tag': 'proxy',
      'server': candidate['server'],
      'server_port': candidate['server_port'],
      'version': version,
      'psk': psk,
      if (userkey != null) 'userkey': userkey,
      if (reuse != null) 'reuse': reuse,
      if (network != null) 'network': network,
      if (version == 4 && obfsMode != null) 'obfs_mode': obfsMode,
      if (version == 4 && obfsHost != null) 'obfs_host': obfsHost,
      if (version == 6 && mode != null) 'mode': mode,
    });
  }

  static String encodeSnellForEphemeralTunnel({
    required Map<String, dynamic> item,
  }) => jsonEncode(composeSnell(item: item));

  /// SOCKS5 account profile for the signed macOS packet-tunnel backend.
  /// Credentials and server are never replaced with fallback public proxies.
  static Map<String, dynamic> composeSocks5({
    required Map<String, dynamic> item,
  }) {
    final candidate = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'socks5', item: item,
    );
    if (candidate.keys.any((key) => !const {
          'type', 'tag', 'server', 'server_port', 'version',
          'username', 'password', 'network',
        }.contains(key))) {
      throw const FormatException('MAC_SOCKS5_UNREVIEWED_FIELD');
    }
    // For protected DNS-over-HTTPS, the server must support TCP CONNECT.
    if (candidate['network'] != null && candidate['network'] != 'tcp') {
      throw const FormatException('MAC_SOCKS5_TCP_REQUIRED');
    }
    return _envelope(<String, dynamic>{
      'type': 'socks',
      'tag': 'proxy',
      'server': candidate['server'],
      'server_port': candidate['server_port'],
      'version': '5',
      'username': candidate['username'],
      'password': candidate['password'],
      'network': 'tcp',
    });
  }

  static String encodeSocks5ForEphemeralTunnel({
    required Map<String, dynamic> item,
  }) => jsonEncode(composeSocks5(item: item));

  static Map<String, dynamic> _envelope(Map<String, dynamic> outbound) {
    return <String, dynamic>{
      'log': <String, dynamic>{'level': 'error'},
      'dns': <String, dynamic>{
        'servers': <Map<String, dynamic>>[
          // Only the proxy endpoint gets local bootstrap DNS.
          {'type': 'local', 'tag': 'dns-bootstrap'},
          {
            'type': 'https',
            'tag': 'dns-remote',
            'server': '1.1.1.1',
            'server_port': 443,
            'path': '/dns-query',
            'tls': {'enabled': true, 'server_name': 'one.one.one.one'},
            'detour': 'proxy',
          },
        ],
        'final': 'dns-remote',
        'strategy': 'ipv4_only',
      },
      'inbounds': <Map<String, dynamic>>[
        <String, dynamic>{
          'type': 'tun',
          'tag': 'twinconnect-macos-tun',
          'address': <String>['172.19.0.1/30', 'fdfe:dcba:9876::1/126'],
          'mtu': 1400,
          'auto_route': true,
          // Route enforcement is performed by the signed extension once its
          // platform interface is fully connected to the packet flow.
          'strict_route': true,
          'dns_mode': 'hijack',
        }
      ],
      'outbounds': <Map<String, dynamic>>[outbound],
      'route': <String, dynamic>{
        'auto_detect_interface': true,
        'default_domain_resolver': 'dns-bootstrap',
        'final': 'proxy',
        'rules': <Map<String, dynamic>>[
          {'port': 53, 'action': 'hijack-dns'},
          // Until native IPv6 forwarding and leak checks are verified,
          // reject IPv6 explicitly instead of silently routing it direct.
          {'ip_version': 6, 'action': 'reject'},
        ],
      },
    };
  }

  static String encodeForEphemeralTunnel({
    required Map<String, dynamic> item,
  }) => jsonEncode(composeHysteria2(item: item));

  static String encodeTuicForEphemeralTunnel({
    required Map<String, dynamic> item,
  }) => jsonEncode(composeTuic(item: item));

  static String encodeAnyTlsForEphemeralTunnel({
    required Map<String, dynamic> item,
  }) => jsonEncode(composeAnyTls(item: item));

  static String encodeNaiveForEphemeralTunnel({
    required Map<String, dynamic> item,
  }) => jsonEncode(composeNaive(item: item));
}
