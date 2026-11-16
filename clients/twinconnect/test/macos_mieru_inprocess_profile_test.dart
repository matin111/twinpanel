import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/macos_mieru_profile.dart';

Map<String, dynamic> sample() => {
  'config_format': 'mieru-json',
  'config': jsonEncode({
    'profiles': [{
      'profileName': 'test-user',
      'user': {'name': 'test-user', 'password': 'synthetic-secret'},
      'servers': [{
        'ipAddress': '93.184.216.34',
        'domainName': '',
        'portBindings': [
          {'protocol': 'TCP', 'port': 24567},
        ],
      }],
    }],
    'activeProfile': 'test-user',
    'socks5ListenLAN': false,
    'httpProxyListenLAN': false,
  }),
};

void main() {
  test('in-process Mieru keeps account and only local SOCKS listener', () {
    final isolated = MacMieruProfile.composeInProcess(
      item: sample(),
      pinnedEndpointIpv4: '93.184.216.34',
      socks5Port: 34101,
      extensionOwnsCore: true,
      endpointPinnedOutsideTunnel: true,
    );
    expect(isolated['rpcPort'], 0);
    expect(isolated, isNot(contains('httpProxyPort')));
    expect(isolated['socks5Port'], 34101);
    expect(isolated['socks5ListenLAN'], false);
    expect(isolated['httpProxyListenLAN'], false);
    expect(isolated['activeProfile'], 'test-user');
    expect(((isolated['profiles'] as List).single as Map)['user']['password'],
        'synthetic-secret');
    expect(isolated, isNot(contains('outbounds')));
  });

  test('in-process Mieru requires extension ownership and pinned route', () {
    expect(() => MacMieruProfile.composeInProcess(
      item: sample(), pinnedEndpointIpv4: '93.184.216.34',
      socks5Port: 34101,
      extensionOwnsCore: false, endpointPinnedOutsideTunnel: true,
    ), throwsFormatException);
    expect(() => MacMieruProfile.composeInProcess(
      item: sample(), pinnedEndpointIpv4: '93.184.216.34',
      socks5Port: 34101,
      extensionOwnsCore: true, endpointPinnedOutsideTunnel: false,
    ), throwsFormatException);
  });
}
