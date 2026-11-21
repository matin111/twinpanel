import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS Kill Switch is native configured, never fake verified', () {
    final host = File('macos_native/TwinConnectMacOSVPNControl.swift')
        .readAsStringSync();
    final libbox = File('macos_native/TwinConnectMacOSLibboxControl.swift')
        .readAsStringSync();
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift')
        .readAsStringSync();
    final settings = File('lib/vpn_settings.dart').readAsStringSync();

    expect(host, contains('enum TwinConnectMacOSKillSwitch'));
    expect(host, contains('tunnel.includeAllNetworks = requested'));
    expect(host, contains('manager.onDemandRules = requested ? [NEOnDemandRuleConnect()] : []'));
    expect(host, contains('manager.isOnDemandEnabled = requested'));
    expect(host, contains('MACOS_KILLSWITCH_DISCONNECT_FIRST'));
    expect(host, contains('"configured": false, "verified": false'));
    expect(host, contains('"configured": true, "verified": false'));
    expect(host, contains('TwinConnectMacOSKillSwitch.applySavedPolicy(settings, manager: selected)'));
    expect(libbox, contains('TwinConnectMacOSKillSwitch.applySavedPolicy(tunnel, manager: manager)'));
    expect(bridge, contains('case "getMacKillSwitchStatus":'));
    expect(bridge, contains('case "setMacKillSwitch":'));
    expect(settings, contains("const Key('macKillSwitch')"));
    expect(settings, contains("'setMacKillSwitch'"));
    expect(settings, contains("'getMacKillSwitchStatus'"));
    expect(settings, contains('leak testing still required'));
  });
}
