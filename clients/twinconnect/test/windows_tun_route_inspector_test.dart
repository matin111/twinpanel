import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/windows_singbox_tunnel.dart';

void main() {
  test('Windows read-only TUN inspection responds without PowerShell failure',
      () async {
    if (!Platform.isWindows) return;
    final issue = await WindowsSingBoxTunnel.inspectWindowsTunRoutes();
    // CI runners normally have no TwinConnectSB adapter. If it is present,
    // the inspector may instead report missing route or healthy state.
    // A PowerShell invocation/parse failure is the regression.
    expect(issue, isNot('SINGBOX_TUN_ROUTE_INSPECTION_FAILED'));
    expect(issue, anyOf(
      isNull,
      'SINGBOX_TUN_ADAPTER_MISSING',
      'SINGBOX_TUN_DEFAULT_ROUTE_MISSING',
    ));
  }, timeout: const Timeout(Duration(seconds: 65)));
}
