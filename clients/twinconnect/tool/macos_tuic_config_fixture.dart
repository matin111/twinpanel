// Official sing-box v1.14.4 TUIC synthetic parser fixture.
// No production credentials or accounts.
import 'dart:convert';
import 'package:twinconnect/singbox_macos_config.dart';

void main() {
  final json = SingBoxMacConfig.composeTuic(item: {
    'node_id': 1,
    'outbound': {
      'type': 'tuic',
      'server': 'example.org',
      'server_port': 443,
      'uuid': '2dd61d93-75d8-4da4-ac0e-6aece7eac365',
      'password': 'SYNTHETIC_NOT_REAL',
      'congestion_control': 'cubic',
      'udp_relay_mode': 'native',
      'tls': {'enabled': true, 'server_name': 'example.org'},
    },
  });
  print(jsonEncode(json));
}
