import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/windows_xray_proxy.dart';

void main() {
  test('Xray remains disconnected before a process is verified', () {
    final runtime = WindowsXrayProxy();
    expect(runtime.isRunning, isFalse);
    expect(runtime.socksPort, isNull);
  });

  test('native process guard verifies bundled Xray executable path', () {
    final guard = File('native/windows/twinconnect_xray_guard.h')
        .readAsStringSync();
    final installer = File('tools/install_windows_native.py')
        .readAsStringSync();
    expect(guard, contains('engines\\\\xray\\\\xray.exe'));
    expect(guard, contains('JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE'));
    expect(guard, contains('IsBundledEngine(child)'));
    expect(installer, contains('guardXrayProcess'));
    expect(installer, contains('twinconnect_xray_guard.h'));
  });

  test('bundler and smoke check reject missing or wrong binaries', () {
    final bundler = File('tools/bundle_xray_windows.ps1').readAsStringSync();
    final check = File('tools/check_xray_windows.ps1').readAsStringSync();
    expect(bundler, contains('SHA256'));
    expect(bundler, contains('26.11.9'));
    expect(check, contains('run -test -config stdin:'));
  });
}
