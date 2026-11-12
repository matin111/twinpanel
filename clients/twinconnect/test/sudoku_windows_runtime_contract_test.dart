import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Sudoku native core is included and guarded, not called via sing-box', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    final native = File('tools/install_windows_native.py').readAsStringSync();
    final proxy = File('lib/windows_sudoku_proxy.dart').readAsStringSync();
    final config = File('lib/singbox_windows_config.dart').readAsStringSync();

    expect(ui, contains('_startSudokuTunnel('));
    expect(ui, contains('WindowsSudokuProxy.enginePresent()'));
    // The profile resolver validates delivered Sudoku identities and may
    // choose a verified same-country node when a legacy node has no profile.
    expect(ui, contains('SudokuClientProfile.resolveDeliveredProfile('));
    expect(ui, contains('requestedNodeId: serverId'));
    expect(ui, contains('inventory: widget.servers'));
    expect(ui, contains('serverId: resolvedServerId'));
    expect(ui, contains('_modernNodeId = resolvedServerId'));
    final resolver = File('lib/sudoku_client_profile.dart').readAsStringSync();
    expect(resolver, contains('fromItem(matches.single, candidate.id)'));
    expect(resolver, contains('server.nodeOnline'));
    expect(resolver, contains('server.countryCode.toUpperCase()'));
    expect(resolver, contains('requested!.countryCode.toUpperCase()'));
    expect(ui, contains("protocol: 'sudoku'"));
    expect(ui, contains('sudokuSocksPort: socksPort'));
    expect(ui, contains('sudokuVerifiedExitIp: verifiedExit'));
    expect(ui, contains('sudokuEndpointIPv4: endpoint'));
    expect(ui, contains('_sudokuProxy.stop()'));
    expect(proxy, contains('stageSudokuConfig'));
    expect(proxy, contains('guardSudokuProcess'));
    expect(proxy, contains('finishSudokuConfig'));
    expect(proxy, contains('await _verifyRemoteExit(localPort)'));
    // Diagnose abrupt core exits without leaking keys, config, or raw stderr.
    expect(proxy, contains('lastUnexpectedExitReason'));
    expect(proxy, contains('_classifyNativeFailure(line)'));
    // Official Sudoku emits Fatalf/ERROR through stdout. Check both streams
    // are read and reduced to safe categories, never logged raw.
    expect(proxy, contains('_consumeNativeDiagnostic(owned, owned.stdout)'));
    expect(proxy, contains('_consumeNativeDiagnostic(owned, owned.stderr)'));
    expect(proxy, contains('SUDOKU_CLIENT_INIT_FAILED'));
    expect(proxy, contains('SUDOKU_TABLE_INIT_FAILED'));
    expect(proxy, contains('owned.exitCode.then((code)'));
    expect(proxy, isNot(contains('print(line)')));
    expect(proxy, isNot(contains('stderr.listen((chunk) => print')));
    expect(ui, contains('_sudokuProxy.lastUnexpectedExitReason'));
    expect(ui, contains('SUDOKU_CONFIG_LOAD_FAILED'));
    expect(ui, contains('SUDOKU_LOCAL_PORT_CONFLICT'));
    // Native startup and pre-TUN probe timeouts remain explicit and safe.
    expect(proxy, contains('SUDOKU_CONFIG_STAGE_TIMEOUT'));
    expect(proxy, contains('SUDOKU_PROCESS_START_TIMEOUT'));
    expect(proxy, contains('SUDOKU_PROCESS_GUARD_TIMEOUT'));
    expect(ui, contains('SUDOKU_BASELINE_IP_TIMEOUT'));
    expect(ui, contains('WindowsSingBoxTunnel.measureBaselineIp().timeout('));
    expect(proxy, contains('SUDOKU_CORE_EXIT_CODE_'));
    expect(proxy, contains('code.toUnsigned(32)'));
    expect(proxy, contains('lastUnexpectedExitReason ??'));
    expect(ui, contains("status.startsWith('SUDOKU_CORE_EXIT_CODE_')"));
    expect(proxy, contains("['-c', path]"));
    expect(native, contains('twinconnect_sudoku_guard.h'));
    expect(native, contains('stageSudokuConfig'));
    expect(native, contains('guardSudokuProcess'));
    expect(config, contains("'route_exclude_address': ['\$endpointRoute/32']"));
  });

  test('native ownership uses delete-on-close private files and limited child', () {
    final native = File('native/windows/twinconnect_sudoku_guard.h')
        .readAsStringSync();
    expect(native, contains('JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE'));
    expect(native, contains('IsBundledEngine(child)'));
    expect(native, contains('FILE_FLAG_DELETE_ON_CLOSE'));
    expect(native, contains('ConvertSidToStringSidW'));
    expect(native, contains('FILE_SHARE_READ | FILE_SHARE_DELETE'));
    expect(native, contains('ReleaseConfig()'));
  });

  test('official release is pinned and smoke tested in Windows CI', () {
    final script = File('tools/bundle_sudoku_windows.ps1')
        .readAsStringSync();
    final flow = File('../../.github/workflows/twinconnect-windows-preview.yml')
        .readAsStringSync();
    expect(script, contains('sudoku-windows-amd64.zip'));
    expect(script, contains('52051b7b30d6af66ee151d6a978fa20434edeb5eaaecc4c9bb27063bed33efe1'));
    expect(script, contains('LICENSE.txt'));
    expect(flow, contains('bundle_sudoku_windows.ps1'));
    expect(flow, contains('check_sudoku_windows.ps1'));
  });
}
