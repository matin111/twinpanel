import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/windows_wireguard.dart';

ClientProtocolProfiles _profiles(List<Map<String, dynamic>> items) =>
    ClientProtocolProfiles(
      namespace: 'TPABCDEF',
      protocol: VpnProtocols.byCode('wireguard')!,
      items: items,
    );

void main() {
  test('only an authorized selected node config is returned', () {
    final profiles = _profiles([
      {'node_id': 12, 'node': 'Germany', 'config': 'secret Germany'},
      {'node_id': 18, 'node': 'Turkey', 'config': 'secret Turkey'},
    ]);
    final result = WindowsWireGuardController.configForSingleNode(
        profiles, '18');
    expect(result.name, 'Turkey');
    expect(result.config, 'secret Turkey');
  });

  test('missing selected node fails closed', () {
    final profiles = _profiles([
      {'node_id': 12, 'config': 'private config'},
    ]);
    expect(
      () => WindowsWireGuardController.configForSingleNode(profiles, '18'),
      throwsFormatException,
    );
  });

  test('ambiguous selected node cannot select random config', () {
    final profiles = _profiles([
      {'node_id': 12, 'config': 'private config A'},
      {'node_id': 12, 'config': 'private config B'},
    ]);
    expect(
      () => WindowsWireGuardController.configForSingleNode(profiles, '12'),
      throwsFormatException,
    );
  });

  test('empty configuration is refused', () {
    final profiles = _profiles([{'node_id': '12', 'config': ''}]);
    expect(
      () => WindowsWireGuardController.configForSingleNode(profiles, '12'),
      throwsFormatException,
    );
  });

  test('native Windows service is not assumed on other operating systems',
      () async {
    final status = await const WindowsWireGuardController().status();
    // Flutter CI Linux does not have the Windows tunnel service.
    expect(status['state'], 'unavailable');
  });
}
