import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/windows_openvpn_tunnel.dart';

void main() {
  test('OpenVPN Windows startup avoids unreliable DCO adapter by default', () {
    final args = WindowsOpenVpnTunnel.startupArguments(
      configPath: r'C:\private\account.ovpn',
      managementPort: 41921,
      managementPasswordPath: r'C:\private\management.pwd',
    );
    expect(args, contains('--disable-dco'));
    expect(args.indexOf('--disable-dco'), greaterThan(0));
    expect(args, containsAllInOrder([
      '--config', r'C:\private\account.ovpn',
      '--management', '127.0.0.1', '41921',
      r'C:\private\management.pwd',
      '--disable-dco', '--auth-nocache', '--verb', '3',
    ]));
    expect(args, isNot(contains('--windows-driver')));
    expect(args, isNot(contains('--script-security')));
  });
}
