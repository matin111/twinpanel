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

  /// TUIC requires a UUID plus TLS. Generate one allowlisted outbound; never
  /// enable 0-RTT or accept certificate verification bypass from the panel.
  static Map<String, dynamic> composeTuic({required Map<String, dynamic> item}) {
    final candidate = SingBoxProfileValidator.validateOutbound(
      protocolCode: 'tuic', item: item,
    );
    final uuid = candidate['uuid'];
    final secret = candidate['password'];
    final uuidPattern = RegExp(
      r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12} <String, dynamic>{'level': 'error'},
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
}
,
    );
    if (uuid is! String || !uuidPattern.hasMatch(uuid) ||
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
}
