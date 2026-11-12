import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'windows_xray_preflight.dart';
import 'xray_inbound_profiles.dart';
import 'xray_windows_config.dart';

/// Owns a single bundled Xray-core LOCAL SOCKS5 proxy subprocess.
/// This is NOT a full-tunnel VPN: only readiness of its loopback SOCKS
/// listener is checked here. Do not drive the UI's VPN 'connected' state
/// until an independently verified system TUN routes through this process.
class WindowsXrayProxy {
  WindowsXrayProxy({this.onUnexpectedExit});

  static const MethodChannel _native =
      MethodChannel('com.twinpanel.twinconnect/vpn');
  final void Function()? onUnexpectedExit;

  Process? _child;
  int? _port;
  bool _changing = false;

  bool get isRunning => _child != null && _port != null;
  int? get socksPort => isRunning ? _port : null;

  Future<int> start(XrayInboundProfile inbound) async {
    if (!Platform.isWindows) {
      throw const FormatException('XRAY_WINDOWS_ONLY');
    }
    if (_child != null || _changing) {
      throw const FormatException('XRAY_PROXY_ALREADY_RUNNING');
    }
    _changing = true;
    Process? process;
    try {
      if (!await WindowsXrayPreflight.enginePresent()) {
        throw const FormatException('XRAY_ENGINE_UNAVAILABLE');
      }
      final reservation = await ServerSocket.bind(
          InternetAddress.loopbackIPv4, 0);
      final port = reservation.port;
      await reservation.close();
      final config = XrayWindowsConfig.compose(
          inbound: inbound, localSocksPort: port);
      if (!await WindowsXrayPreflight.checkInMemory(config)) {
        throw const FormatException('XRAY_CONFIG_INVALID');
      }
      process = await Process.start(
        WindowsXrayPreflight.enginePath(Platform.resolvedExecutable),
        const ['run', '-config', 'stdin:'],
        runInShell: false,
      ).timeout(const Duration(seconds: 8));
      _child = process;
      final guarded = await _native.invokeMethod<bool>(
        'guardXrayProcess', {'pid': process.pid},
      ).timeout(const Duration(seconds: 6));
      if (guarded != true) {
        throw const FormatException('XRAY_PROCESS_GUARD_UNAVAILABLE');
      }
      // Never log or persist native stdout/stderr: engine errors can
      // include private VLESS identifiers or REALITY transport parameters.
      unawaited(process.stdout.drain<void>());
      unawaited(process.stderr.drain<void>());
      process.stdin.add(utf8.encode(jsonEncode(config)));
      await process.stdin.close();
      final ownedProcess = process;
      unawaited(process.exitCode.then((_) {
        if (identical(_child, ownedProcess)) {
          _child = null;
          _port = null;
          if (!_changing) onUnexpectedExit?.call();
        }
      }));
      var ready = false;
      for (var attempt = 0; attempt < 25; attempt++) {
        if (!identical(_child, ownedProcess)) {
          throw const FormatException('XRAY_PROCESS_EXITED');
        }
        if (await _checkLocalSocks(port)) {
          ready = true;
          break;
        }
        await Future<void>.delayed(const Duration(milliseconds: 200));
      }
      if (!ready || !identical(_child, ownedProcess)) {
        throw const FormatException('XRAY_SOCKS_LISTENER_UNAVAILABLE');
      }
      _port = port;
      return port;
    } catch (_) {
      await _terminate();
      rethrow;
    } finally {
      _changing = false;
    }
  }

  static Future<bool> _checkLocalSocks(int port) async {
    Socket? socket;
    try {
      socket = await Socket.connect(
        InternetAddress.loopbackIPv4, port,
        timeout: const Duration(milliseconds: 500),
      );
      // SOCKS5 greeting: version 5, one method, no authentication.
      socket.add(const [5, 1, 0]);
      await socket.flush();
      final response = await socket.first.timeout(
        const Duration(milliseconds: 600),
      );
      return response.length >= 2 && response[0] == 5 && response[1] == 0;
    } catch (_) {
      return false;
    } finally {
      socket?.destroy();
    }
  }

  Future<void> stop() async {
    if (_changing) throw const FormatException('XRAY_PROXY_BUSY');
    _changing = true;
    try {
      await _terminate();
    } finally {
      _changing = false;
    }
  }

  Future<void> _terminate() async {
    final process = _child;
    if (process == null) {
      _port = null;
      return;
    }
    process.kill();
    try {
      await process.exitCode.timeout(const Duration(seconds: 8));
    } on TimeoutException {
      throw const FormatException('XRAY_PROCESS_DID_NOT_STOP');
    }
    if (identical(_child, process)) {
      _child = null;
      _port = null;
    }
  }
}
