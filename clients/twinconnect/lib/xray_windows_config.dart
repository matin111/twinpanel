import 'xray_inbound_profiles.dart';

/// Creates an Xray-core VLESS outbound and an isolated local SOCKS listener.
/// This is only a configuration builder. It does NOT start a process, install
/// Windows routes or claim a functioning system-wide VPN.
class XrayWindowsConfig {
  const XrayWindowsConfig._();

  static Map<String, dynamic> compose({
    required XrayInboundProfile inbound,
    required int localSocksPort,
    int? localHttpPort,
  }) {
    if (localHttpPort != null &&
        (localHttpPort < 1024 || localHttpPort > 65535 ||
         localHttpPort == localSocksPort)) {
      throw const FormatException('XRAY_HTTP_PORT_INVALID');
    }
    if (localSocksPort < 1024 || localSocksPort > 65535) {
      throw const FormatException('XRAY_SOCKS_PORT_INVALID');
    }
    final uri = inbound.uri;
    final query = uri.queryParameters;
    final uuid = uri.userInfo;
    if (!RegExp(
      r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[1-8][a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}$',
    ).hasMatch(uuid)) {
      throw const FormatException('XRAY_UUID_INVALID');
    }

    final security = query['security']!;
    final transport = query['type']!;
    final sni = query['sni']!;
    final fingerprint = query['fp'] ?? 'chrome';
    final tls = <String, dynamic>{
      'serverName': sni,
      'fingerprint': fingerprint,
      if (query['alpn'] case final String alpn when alpn.isNotEmpty)
        'alpn': alpn.split(','),
    };
    final stream = <String, dynamic>{
      'network': transport,
      'security': security,
      if (security == 'tls') 'tlsSettings': tls,
      if (security == 'reality')
        'realitySettings': {
          'serverName': sni,
          'fingerprint': fingerprint,
          'publicKey': query['pbk']!,
          'shortId': query['sid'] ?? '',
          if ((query['spx'] ?? '').isNotEmpty) 'spiderX': query['spx'],
        },
      if (transport == 'ws')
        'wsSettings': {
          'path': query['path']!,
          if ((query['host'] ?? '').isNotEmpty)
            'headers': {'Host': query['host']},
        },
      if (transport == 'xhttp')
        'xhttpSettings': {
          'path': query['path']!,
          'mode': query['mode'] ?? 'stream-one',
          if ((query['host'] ?? '').isNotEmpty) 'host': query['host'],
        },
    };
    return {
      'log': {'loglevel': 'warning'},
      'inbounds': [{
        'tag': 'twinconnect-loopback',
        'listen': '127.0.0.1',
        'port': localSocksPort,
        'protocol': 'socks',
        'settings': {'auth': 'noauth', 'udp': false},
      },
      if (localHttpPort != null) {
        'tag': 'twinconnect-loopback-probe',
        'listen': '127.0.0.1',
        'port': localHttpPort,
        'protocol': 'http',
        'settings': {'allowTransparent': false},
      }],
      'outbounds': [
        {
          'tag': 'proxy',
          'protocol': 'vless',
          'settings': {
            'vnext': [{
              'address': uri.host,
              'port': uri.port,
              'users': [{'id': uuid, 'encryption': 'none'}],
            }],
          },
          'streamSettings': stream,
        },
        {'tag': 'block', 'protocol': 'blackhole'},
      ],
      'routing': {'domainStrategy': 'AsIs', 'rules': []},
    };
  }
}
