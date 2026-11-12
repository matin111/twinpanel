import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Windows runner removes only title caption and keeps resize', () {
    final installer = File('tools/install_windows_native.py').readAsStringSync();
    expect(installer, contains('frameless Windows shell'));
    expect(installer, contains('WS_CAPTION'));
    expect(installer, contains('WS_SYSMENU'));
    expect(installer, contains('SWP_FRAMECHANGED'));
    expect(installer, contains('windowControl'));
    expect(installer, contains('WM_CLOSE'));
    expect(installer, isNot(contains('ExitProcess(')));
  });

  test('all screens keep safe floating window controls and drag', () {
    final view = File('lib/frameless_window_controls.dart').readAsStringSync();
    final main = File('lib/main.dart').readAsStringSync();
    expect(main, contains('TwinConnectFramelessControls()'));
    expect(view, contains('windowsMinimize'));
    expect(view, contains('windowsMaximize'));
    expect(view, contains('windowsClose'));
    expect(view, contains('windowsFramelessDrag'));
    expect(view, contains("windowControl"));
  });
}
