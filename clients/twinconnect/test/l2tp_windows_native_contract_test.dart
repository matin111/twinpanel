import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('L2TP uses Windows RAS directly and never executes a password shell', () {
    final native = File('native/windows/twinconnect_l2tp.h')
        .readAsStringSync();
    expect(native, contains('RasSetEntryPropertiesW'));
    expect(native, contains('RasSetCredentialsW'));
    expect(native, contains('RASCM_PreSharedKey'));
    expect(native, contains('RasDialW'));
    expect(native, contains('RasHangUpW'));
    expect(native, contains('RasDeleteEntryW'));
    expect(native, isNot(contains('system(')));
    expect(native, isNot(contains('ShellExecute')));
    expect(native, isNot(contains('CreateProcess')));
  });

  test('native channel never returns secret-bearing L2TP request fields', () {
    final bridge = File('tools/install_windows_native.py')
        .readAsStringSync();
    expect(bridge, contains('startL2tp'));
    expect(bridge, contains('l2tpStatus'));
    expect(bridge, contains('l2tpTraffic'));
    expect(bridge, contains('stopL2tp'));
    expect(bridge, contains('twinconnect_l2tp::Stop();'));
  });
}
