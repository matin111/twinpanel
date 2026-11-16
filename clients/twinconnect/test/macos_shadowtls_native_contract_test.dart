import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('ShadowTLS macOS uses a signed-only native Libbox chain', () {
    final bridge = File('macos_native/TwinConnectMacOSVPNBridge.swift').readAsStringSync();
    final control = File('macos_native/TwinConnectMacOSLibboxControl.swift').readAsStringSync();
    final engine = File('macos_native/libbox/TwinConnectMacLibboxEngine.swift').readAsStringSync();
    final provider = File('macos_native/PacketTunnelProvider.swift').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final controller = File('lib/macos_shadowtls_controller.dart').readAsStringSync();
    expect(bridge, contains('case "startShadowTls":'));
    expect(bridge, contains('case "getShadowTlsTunnelStatus":'));
    expect(bridge, contains('case "macOSShadowTlsEngineStatus":'));
    expect(control, contains('allowedShadowTlsConfig'));
    expect(control, contains('inner["detour"] as? String == "shadowtls-transport"'));
    expect(engine, contains('shadowTlsProfileAllowed'));
    expect(provider, contains('"naive", "shadowtls", "snell"'));
    expect(controller, contains('MacShadowTlsConfig.encode'));
    expect(dashboard, contains('_macShadowTls.start('));
    expect(dashboard, contains("protocol == 'shadowtls'"));
    expect(dashboard, contains('_vpnVerified = false'));
  });
}
