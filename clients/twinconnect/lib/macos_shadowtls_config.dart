import 'dart:convert';

import 'shadowtls_chain.dart';

/// Strict macOS ShadowTLS v3 + Shadowsocks configuration preparation.
///
/// This is an offline profile composer only. The macOS native PacketTunnel
/// bridge must explicitly support and validate the two-hop chain before
/// this configuration may be used to start a VPN.
class MacShadowTlsConfig {
  const MacShadowTlsConfig._();

  static Map<String, dynamic> compose({required Map<String, dynamic> item}) {
    final chain = ShadowTlsChain.fromItem(item);
    final ss = chain.shadowsocks;
    final transport = chain.transport;
    final tls = transport['tls'];
    if (tls is! Map ||
        tls['enabled'] != true ||
        tls['insecure'] == true ||
        tls.containsKey('reality') ||
        tls.containsKey('disable_sni') ||
        tls.containsKey('utls')) {
      throw const FormatException('MAC_SHADOWTLS_TLS_UNSAFE');
    }
    final sni = tls['server_name'];
    if (sni is! String || sni.isEmpty || sni.length > 255 ||
        sni.contains('/') || sni.contains(' ') || sni.contains('@')) {
      throw const FormatException('MAC_SHADOWTLS_SNI_INVALID');
    }
    // Do not carry unreviewed settings into the extension.
    if (ss.keys.any((k) => !const {'type', 'tag', 'detour',
          'method', 'password'}.contains(k)) ||
        transport.keys.any((k) => !const {'type', 'tag', 'version',
          'server', 'server_port', 'password', 'tls'}.contains(k)) ||
        tls.keys.any((k) => !const {'enabled', 'server_name'}.contains(k))) {
      throw const FormatException('MAC_SHADOWTLS_UNREVIEWED_FIELD');
    }
    if (!const {'aes-128-gcm', 'aes-256-gcm',
      'chacha20-ietf-poly1305', '2022-blake3-aes-128-gcm',
      '2022-blake3-aes-256-gcm', '2022-blake3-chacha20-poly1305'}
        .contains(ss['method']) ||
        (ss['password'] as String).length > 4096 ||
        (transport['password'] as String).length > 4096) {
      throw const FormatException('MAC_SHADOWTLS_CIPHER_INVALID');
    }
    final inner = <String, dynamic>{
      'type': 'shadowsocks',
      'tag': 'proxy',
      'method': ss['method'],
      'password': ss['password'],
      'detour': 'shadowtls-transport',
    };
    final outer = <String, dynamic>{
      'type': 'shadowtls',
      'tag': 'shadowtls-transport',
      'version': 3,
      'server': transport['server'],
      'server_port': transport['server_port'],
      'password': transport['password'],
      'tls': {'enabled': true, 'server_name': sni},
    };
    return {
      'log': {'level': 'error'},
      'dns': {
        'servers': [
          {'type': 'local', 'tag': 'dns-bootstrap'},
          {'type': 'https', 'tag': 'dns-remote',
            'server': '1.1.1.1', 'server_port': 443,
            'path': '/dns-query',
            'tls': {'enabled': true, 'server_name': 'one.one.one.one'},
            'detour': 'proxy'},
        ],
        'final': 'dns-remote', 'strategy': 'ipv4_only',
      },
      'inbounds': [
        {'type': 'tun', 'tag': 'twinconnect-macos-tun',
          'address': ['172.19.0.1/30', 'fdfe:dcba:9876::1/126'],
          'mtu': 1400, 'auto_route': true, 'strict_route': true,
          'dns_mode': 'hijack'},
      ],
      'outbounds': [inner, outer],
      'route': {
        'auto_detect_interface': true,
        'default_domain_resolver': 'dns-bootstrap',
        'final': 'proxy',
        'rules': [
          {'port': 53, 'action': 'hijack-dns'},
          {'ip_version': 6, 'action': 'reject'},
        ],
      },
    };
  }

  static String encode({required Map<String, dynamic> item}) =>
      jsonEncode(compose(item: item));
}
