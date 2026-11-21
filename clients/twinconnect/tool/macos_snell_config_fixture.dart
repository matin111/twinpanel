import '../lib/singbox_macos_config.dart';
import 'dart:convert';

void main() {
  final item = {
    'outbound': {
      'type': 'snell',
      'server': 'example.org',
      'server_port': 8388,
      'version': 4,
      'psk': 'synthetic-test-only',
      'reuse': false,
      'network': 'tcp',
    },
  };
  print(jsonEncode(SingBoxMacConfig.composeSnell(item: item)));
}
