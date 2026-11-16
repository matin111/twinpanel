import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/macos_mieru_profile.dart';

Map<String, dynamic> item() => {
  'config_format': 'mieru-json',
  'config': jsonEncode({
    'profiles': [{
      'profileName': 'test-user',
      'user': {'name': 'test-user', 'password': 'synthetic-secret'},
      'servers': [{
        'domainName': 'tr.example.org',
        'ipAddress': '93.184.216.35',
        'portBindings': [
          {'protocol': 'TCP', 'port': 24567},
          {'protocol': 'UDP', 'portRange': '24000-24005'},
        ],
      }],
    }],
    'activeProfile': 'test-user',
    'socks5ListenLAN': false,
    'httpProxyListenLAN': false,
  }),
};

void main() {
  test('macOS Mieru retains account and binds only to local proxy', () {
    final before = item();
    final runtime = MacMieruProfile.compose(
      item: before, pinnedEndpointIpv4: '93.184.216.34',
      socks5Port: 34101, rpcPort: 34102, httpProxyPort: 34103,
    );
    expect(runtime['activeProfile'], 'test-user');
    expect(runtime['socks5Port'], 34101);
    expect(runtime['socks5ListenLAN'], false);
    expect(runtime['httpProxyListenLAN'], false);
    expect(runtime['loggingLevel'], 'ERROR');
    final profile = (runtime['profiles'] as List).single as Map;
    expect((profile['user'] as Map)['password'], 'synthetic-secret');
    final server = (profile['servers'] as List).single as Map;
    expect(server['ipAddress'], '93.184.216.34');
    expect(server['domainName'], '');
    expect(server['portBindings'], hasLength(2));
    final original = jsonDecode(before['config'] as String);
    expect(original['profiles'][0]['servers'][0]['ipAddress'],
        '93.184.216.35');
  });

  test('invalid / private endpoint and overlapping local ports fail', () {
    expect(() => MacMieruProfile.compose(
      item: item(), pinnedEndpointIpv4: '192.168.1.2',
      socks5Port: 34101, rpcPort: 34102, httpProxyPort: 34103,
    ), throwsFormatException);
    expect(() => MacMieruProfile.compose(
      item: item(), pinnedEndpointIpv4: '93.184.216.34',
      socks5Port: 34101, rpcPort: 34101, httpProxyPort: 34103,
    ), throwsFormatException);
  });

  test('Mieru is never passed to generic sing-box Libbox outbound', () {
    final encoded = MacMieruProfile.encode(
      item: item(), pinnedEndpointIpv4: '93.184.216.34',
      socks5Port: 34101, rpcPort: 34102, httpProxyPort: 34103,
    );
    final runtime = jsonDecode(encoded) as Map;
    expect(runtime, contains('profiles'));
    expect(runtime, isNot(contains('outbounds')));
  });
}
