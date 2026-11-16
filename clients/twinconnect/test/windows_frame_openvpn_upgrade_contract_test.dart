import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Windows surface eliminates nonclient dark stripe and retains resize', () {
    final install = File('tools/install_windows_native.py').readAsStringSync();
    expect(install, contains('SetWindowSubclass(shell,'));
    expect(install, contains('message == WM_NCCALCSIZE && wp'));
    expect(install, contains('message == WM_NCHITTEST'));
    expect(install, contains('return HTTOPLEFT'));
    expect(install, contains('return HTBOTTOMRIGHT'));
    expect(install, contains('DefSubclassProc'));
    expect(install, contains('PRIVATE comctl32'));
    expect(install, contains('WS_CAPTION'));
    expect(install, isNot(contains('static_cast<LONG_PTR>(WS_THICKFRAME)')));
  });

  test('installed OpenVPN engine is upgraded, not silently skipped', () {
    final installer = File('installer.iss').readAsStringSync();
    final bundler = File('tools/bundle_openvpn_windows.ps1').readAsStringSync();
    expect(installer, contains('OpenVPN-2.7.9-I002-amd64.msi'));
    expect(bundler, contains('OpenVPN-2.7.9-I002-amd64.msi'));
    expect(installer, contains('OpenVpnStamp'));
    expect(installer, contains('not FileExists(OpenVpnStamp)'));
    expect(installer, contains('ExitCode = 3010'));
    expect(installer, contains('SaveStringToFile(OpenVpnStamp'));
  });
}
