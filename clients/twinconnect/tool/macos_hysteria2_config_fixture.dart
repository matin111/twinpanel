// Offline synthetic profile for validating the Dart macOS Libbox config
// against the official sing-box parser. NEVER use production credentials.
import 'dart:convert';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  final config = SingBoxMacConfig.composeHysteria2(item: {
    'node_id': 1,
    'outbound': {
      'type': 'hysteria2',
      'server': 'example.org',
      'server_port': 443,
      'password': 'TEST_ONLY_NOT_A_REAL_CREDENTIAL',
      'tls': {'enabled': true, 'server_name': 'example.org'},
    },
  });
  print(jsonEncode(config));
}
