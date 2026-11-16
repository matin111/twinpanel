import 'dart:convert';
import '../lib/singbox_macos_config.dart';

void main() {
  print(jsonEncode(SingBoxMacConfig.composeSocks5(item: {
    'outbound': {
      'type': 'socks',
      'server': 'example.org',
      'server_port': 1080,
      'version': '5',
      'username': 'synthetic-user',
      'password': 'synthetic-password',
      'network': 'tcp',
    },
  })));
}
