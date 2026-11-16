import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('macOS polls Apple tunnel state without faking a peer handshake', () {
    final source = File('lib/live_dashboard.dart').readAsStringSync();
    final macOnly = source.substring(
      source.indexOf('Future<void> _refreshMacOsTunnelStatus()'),
      source.indexOf('Future<void> _toggleIosVpn()'),
    );
    expect(source, contains("Timer.periodic(const Duration(seconds: 7)"));
    expect(source, contains('_macOsStatusTimer?.cancel()'));
    expect(source, contains('_refreshMacOsTunnelStatus()'));
    expect(source, contains("'os_connected_unverified'"));
    expect(source, contains('OS connected; traffic unverified'));
    expect(source, contains('_macOsTunnelPresent'));
    expect(macOnly, contains('_vpnVerified = false'));
    expect(macOnly, contains("if (Platform.isMacOS)"));
  });

  test('macOS safe logout bypasses Windows service and requires OS disconnect', () {
    final source = File('lib/live_dashboard.dart').readAsStringSync();
    final start = source.indexOf('Future<void> _disconnectAndSignOut()');
    final end = source.indexOf('void _stopModernTrafficMonitoring()', start);
    expect(start, greaterThanOrEqualTo(0));
    expect(end, greaterThan(start));
    final signout = source.substring(start, end);
    final appleBranchStart = signout.indexOf('if (Platform.isMacOS) {');
    final windowsBranchStart = signout.indexOf('if (_modernTunnel.isRunning');
    expect(appleBranchStart, greaterThanOrEqualTo(0));
    expect(windowsBranchStart, greaterThan(appleBranchStart));
    final appleBranch = signout.substring(appleBranchStart, windowsBranchStart);
    expect(appleBranch, contains('await _macVpn.status()'));
    expect(appleBranch, contains('await _macVpn.stop()'));
    expect(appleBranch, contains('MACOS_TUNNEL_NOT_STOPPED'));
    expect(appleBranch, contains('MACOS_TUNNEL_STATUS_UNKNOWN'));
    expect(appleBranch, contains('widget.onLogout()'));
    expect(appleBranch, isNot(contains('await _vpn.stop()')));
  });
}
