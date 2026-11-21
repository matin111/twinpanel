import 'dart:convert';

import '../lib/macos_shadowtls_config.dart';

void main() {
  final profile = {
    'config': jsonEncode({
      'outbounds': [
        {'type': 'shadowsocks', 'tag': 'user-shadowsocks',
         'detour': 'shadowtls-chain',
         'method': 'aes-128-gcm', 'password': 'synthetic-ss-password'},
        {'type': 'shadowtls', 'tag': 'shadowtls-chain',
         'version': 3, 'server': 'example.org', 'server_port': 443,
         'password': 'synthetic-shadowtls-password',
         'tls': {'enabled': true, 'server_name': 'example.org'}},
      ],
      'route': {'final': 'user-shadowsocks'},
    }),
  };
  print(MacShadowTlsConfig.encode(item: profile));
}
