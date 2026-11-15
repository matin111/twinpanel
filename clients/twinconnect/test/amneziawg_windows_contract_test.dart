import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/amneziawg_profile.dart';
import 'package:twinconnect/windows_amneziawg.dart';
import 'package:twinconnect/protocols.dart';

String synthetic() => '''
[Interface]
Address = 10.254.0.5/32
PrivateKey = ${base64.encode(List<int>.filled(32, 1))}
DNS = 1.1.1.1
Jc = 6
Jmin = 8
Jmax = 80
S1 = 64
S2 = 96
H1 = 101
H2 = 202
H3 = 303
H4 = 404

[Peer]
PublicKey = ${base64.encode(List<int>.filled(32, 2))}
Endpoint = 93.184.216.34:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
''';

Map<String, dynamic> delivered({String? config}) => {
  'protocol': 'amneziawg',
  'node_id': 25,
  'config_format': 'amneziawg',
  'config': config ?? synthetic(),
};

void main() {
  test('authoritative AWG v1 config keeps all obfuscation values intact', () {
    final parsed = AmneziaWgProfile.fromItem(delivered());
    expect(parsed.config, synthetic());
    for (final param in [
      'Jc = 6', 'Jmin = 8', 'Jmax = 80', 'S1 = 64',
      'S2 = 96', 'H1 = 101', 'H2 = 202', 'H3 = 303', 'H4 = 404',
    ]) {
      expect(parsed.config, contains(param));
    }
  });

  test('AmneziaWG cannot be downgraded to WireGuard or inject hooks', () {
    expect(() => AmneziaWgProfile.fromItem({
      ...delivered(), 'config_format': 'wg_conf',
    }), throwsFormatException);
    expect(() => AmneziaWgProfile.fromItem(delivered(
        config: synthetic().replaceFirst('S1 = 64', ''))),
        throwsFormatException);
    expect(() => AmneziaWgProfile.fromItem(delivered(
        config: synthetic() + '\nPostUp = powershell.exe\n')),
        throwsFormatException);
    expect(() => AmneziaWgProfile.fromItem(delivered(
        config: synthetic().replaceFirst('H4 = 404','H4 = 303'))),
        throwsFormatException);
    expect(() => AmneziaWgProfile.fromItem(delivered(
        config: synthetic().replaceFirst('Jmin = 8','Jmin = 81'))),
        throwsFormatException);
    expect(() => AmneziaWgProfile.fromItem(delivered(
        config: synthetic().replaceFirst('AllowedIPs = 0.0.0.0/0, ::/0',
            'AllowedIPs = 0.0.0.0/0'))),
        throwsFormatException);
  });

  test('independent AWG profile is selected only for exact entitled node', () {
    final profiles = ClientProtocolProfiles(
      namespace: 'TEST',
      protocol: VpnProtocols.byCode('amneziawg')!,
      items: [delivered()],
    );
    expect(WindowsAmneziaWgController.configForSingleNode(
        profiles, '25').config, synthetic());
    expect(() => WindowsAmneziaWgController.configForSingleNode(
        profiles, '6'), throwsFormatException);
    expect(() => WindowsAmneziaWgController.configForSingleNode(
      ClientProtocolProfiles(namespace: 'TEST',
          protocol: VpnProtocols.byCode('wireguard')!, items: [delivered()]),
      '25',
    ), throwsFormatException);
  });

  test('native Windows bridge owns only the TwinConnect AWG service', () {
    final native = File('native/windows/twinconnect_amneziawg.h')
        .readAsStringSync();
    final installer = File('tools/install_windows_native.py')
        .readAsStringSync();
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    expect(native, contains('AmneziaWGTunnel\$TwinConnectAWG'));
    expect(native, contains('TwinConnectAWG.conf.dpapi'));
    expect(native, contains('AmneziaWG\\\\amneziawg.exe'));
    expect(native, contains('AmneziaWG\\\\awg.exe'));
    expect(native, contains('CryptProtectData'));
    expect(native, contains('ValidConfig'));
    expect(native, contains('std::all_of(obfs.begin(), obfs.end()'));
    expect(native, contains('unmanaged_service'));
    expect(native, isNot(contains('WireGuardTunnel\$TwinConnect')));
    expect(installer, contains('startAmneziaWg'));
    expect(installer, contains('stopAmneziaWg'));
    expect(installer, contains('getAmneziaWgStatus'));
    expect(ui, contains('_startAmneziaWgTunnel'));
    expect(ui, contains('await _awg.stop()'));
    expect(ui, contains('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION'));
  });
}
