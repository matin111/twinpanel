// Offline sing-box NaiveProxy parser fixture. No production secrets.
import 'dart:convert';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  final config = SingBoxMacConfig.composeNaive(item: {
    'node_id': 1,
    'outbound': {
      'type': 'naive',
      'server': 'example.org',
      'server_port': 443,
      'username': 'SYNTHETIC_USER',
      'password': 'SYNTHETIC_NOT_REAL',
      'insecure_concurrency': 0,
      'tls': {'enabled': true, 'server_name': 'example.org'},
    },
  });
  print(jsonEncode(config));
}
