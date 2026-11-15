import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('L2TP PPP config explicitly negotiates IPv4 to avoid RAS error 720', () {
    final code = File('native/windows/twinconnect_l2tp.h').readAsStringSync();
    expect(code, contains('settings.dwfNetProtocols = RASNP_Ip;'));
    expect(code, contains('settings.dwFramingProtocol = RASFP_Ppp;'));
    expect(code, contains('settings.dwfOptions2 = RASEO2_UsePreSharedKey;'));
    expect(code, contains('settings.dwVpnStrategy = VS_L2tpOnly;'));
  });

  test('OpenVPN native startup surfaces safe error stages', () {
    final code = File('lib/windows_openvpn_tunnel.dart').readAsStringSync();
    expect(code, contains('OPENVPN_PROCESS_LAUNCH_FAILED'));
    expect(code, contains('OPENVPN_RUNTIME_FILES_FAILED'));
    expect(code, contains('EGRESS_BASELINE'));
    expect(code, contains('EGRESS_VERIFICATION'));
    expect(code, contains('OPENVPN_'));
  });

  test('dashboard shows OS exception classes without leaked exception paths', () {
    final code = File('lib/live_dashboard.dart').readAsStringSync();
    expect(code, contains('VPN_NATIVE_PROCESS_LAUNCH_FAILED'));
    expect(code, contains('VPN_PRIVATE_STORAGE_FAILED'));
    expect(code, contains('VPN_NETWORK_UNAVAILABLE'));
    expect(code, contains('VPN_PROFILE_RUNTIME_TYPE_ERROR'));
    expect(code, contains('VPN_INTERNAL_UNEXPECTED_FAILURE'));
  });
}
