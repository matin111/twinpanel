import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/android_mieru_profile.dart';

void main() {
  final valid = <String, dynamic>{
    'config_format': 'mieru-json',
    'config': jsonEncode({
      'profiles': [{
        'profileName': 'test',
        'user': {'name': 'test', 'password': 'synthetic'},
        'servers': [{
          'ipAddress': '93.184.216.34',
          'domainName': '',
          'portBindings': [{'port': 12345, 'protocol': 'TCP'}],
        }],
        'mtu': 1400,
        'multiplexing': {'level': 'MULTIPLEXING_LOW'},
        'handshakeMode': 'HANDSHAKE_STANDARD',
      }],
      'activeProfile': 'test',
      'rpcPort': 8964,
      'socks5Port': 1080,
      'socks5ListenLAN': false,
      'httpProxyPort': 8080,
      'httpProxyListenLAN': false,
    }),
  };

  test('accepts a valid panel Mieru profile', () {
    expect(() => AndroidMieruProfile.validate(valid), returnsNormally);
  });

  test('rejects unsafe LAN listening', () {
    final config = jsonDecode(valid['config'] as String) as Map<String, dynamic>;
    config['socks5ListenLAN'] = true;
    expect(
      () => AndroidMieruProfile.validate({...valid, 'config': jsonEncode(config)}),
      throwsFormatException,
    );
  });

  test('rejects missing or oversized profiles', () {
    expect(() => AndroidMieruProfile.validate({}), throwsFormatException);
    expect(
      () => AndroidMieruProfile.validate({'config': 'x' * 262145}),
      throwsFormatException,
    );
  });
}
