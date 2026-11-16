// Offline parser fixture for sing-box v1.14.4. No live accounts.
import 'dart:convert';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  final config = SingBoxMacConfig.composeAnyTls(item: {
    'node_id': 1,
    'outbound': {
      'type': 'anytls',
      'server': 'example.org',
      'server_port': 443,
      'password': 'SYNTHETIC_NOT_A_REAL_SECRET',
      'idle_session_check_interval': '30s',
      'idle_session_timeout': '30s',
      'min_idle_session': 5,
      'tls': {'enabled': true, 'server_name': 'example.org'},
    },
  });
  print(jsonEncode(config));
}
