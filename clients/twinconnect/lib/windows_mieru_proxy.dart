import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'mieru_client_profile.dart';
import 'xray_endpoint_route.dart';

/// Owns the independently bundled Mieru Windows core in foreground mode.
/// Its SOCKS5 endpoint is consumed by the existing verified sing-box TUN.
/// No profile password or full native log is printed or persisted.
class WindowsMieruProxy {
  WindowsMieruProxy({this.onUnexpectedExit});

  static const MethodChannel _native =
      MethodChannel('com.twinpanel.twinconnect/vpn');
  final void Function()? onUnexpectedExit;

  Process? _child;
  int? _port;
  String? _verifiedExitIp;
  String? _endpointIpv4;
  bool _changing = false;
  int? _exitCode;

  String get exitReason => _exitCode == null
      ? 'MIERU_CORE_EXITED'
      : 'MIERU_CORE_EXIT_CODE_${_exitCode!.toUnsigned(32).toRadixString(16).padLeft(8, '0')}';

  bool get isRunning => _child != null && _port != null;
  int? get socksPort => isRunning ? _port : null;
  String? get verifiedExitIp => isRunning ? _verifiedExitIp : null;
  String? get endpointIpv4 => isRunning ? _endpointIpv4 : null;

  static String binaryPath() =>
      '${File(Platform.resolvedExecutable).parent.path}'
      '\\engines\\mieru\\mieru.exe';

  static Future<bool> enginePresent() async {
    if (!Platform.isWindows) return false;
    return File(binaryPath()).exists();
  }

  Future<int> start(MieruClientProfile profile) async {
    if (!Platform.isWindows) {
      throw const FormatException('MIERU_WINDOWS_ONLY');
    }
    if (_child != null || _changing) {
      throw const FormatException('MIERU_PROXY_BUSY');
    }
    _changing = true;
    _exitCode = null;
    try {
      if (!await enginePresent()) {
        throw const FormatException('MIERU_ENGINE_NOT_BUNDLED');
      }
      Future<int> localPort() async {
        final reserved = await ServerSocket.bind(
            InternetAddress.loopbackIPv4, 0);
        final p = reserved.port;
        await reserved.close();
        return p;
      }

      final ports = <int>{};
      for (var attempt = 0; ports.length < 3 && attempt < 15; attempt++) {
        ports.add(await localPort());
      }
      if (ports.length != 3) {
        throw const FormatException('MIERU_PORT_ALLOCATION_FAILED');
      }
      final socksPort = ports.elementAt(0);
      final rpcPort = ports.elementAt(1);
      final httpPort = ports.elementAt(2);
      final config = profile.runtimeConfig(
        socks5Port: socksPort, rpcPort: rpcPort, httpProxyPort: httpPort);
      final path = await _native.invokeMethod<String>(
        'stageMieruConfig', {'config': jsonEncode(config)},
      ).timeout(const Duration(seconds: 5));
      if (path == null || path.isEmpty) {
        throw const FormatException('MIERU_PRIVATE_CONFIG_STAGE_FAILED');
      }
      // The native user-only temporary JSON is the only credential source.
      // The process arguments contain only an unprivileged 'run' subcommand.
      final owned = await Process.start(
        binaryPath(), ['run'], runInShell: false,
        environment: {'MIERU_CONFIG_JSON_FILE': path},
        includeParentEnvironment: true,
      ).timeout(const Duration(seconds: 7));
      _child = owned;
      unawaited(owned.stdout.drain<void>());
      unawaited(owned.stderr.drain<void>());
      unawaited(owned.exitCode.then((code) {
        if (identical(_child, owned)) {
          _exitCode = code;
          _child = null;
          _port = null;
          _verifiedExitIp = null;
          _endpointIpv4 = null;
          if (!_changing) onUnexpectedExit?.call();
        }
      }));
      final guarded = await _native.invokeMethod<bool>(
        'guardMieruProcess', {'pid': owned.pid},
      ).timeout(const Duration(seconds: 5));
      if (guarded != true) {
        throw const FormatException('MIERU_PROCESS_GUARD_UNAVAILABLE');
      }
      var ready = false;
      for (var i = 0; i < 40; i++) {
        if (!identical(_child, owned)) throw FormatException(exitReason);
        if (await _socksReady(socksPort)) { ready = true; break; }
        await Future<void>.delayed(const Duration(milliseconds: 150));
      }
      if (!ready || !identical(_child, owned)) {
        throw const FormatException('MIERU_SOCKS_PROXY_UNAVAILABLE');
      }
      // Remove credential-bearing file immediately after the engine loaded it.
      await _finishConfigStage();
      final exitIp = await _verifyRemoteExit(httpPort);
      if (!identical(_child, owned)) throw FormatException(exitReason);
      _port = socksPort;
      _verifiedExitIp = exitIp;
      _endpointIpv4 = profile.endpointIpv4;
      return socksPort;
    } catch (_) {
      await _terminate();
      rethrow;
    } finally {
      await _finishConfigStage();
      _changing = false;
    }
  }

  static Future<bool> _socksReady(int port) async {
    Socket? socket;
    try {
      socket = await Socket.connect(InternetAddress.loopbackIPv4, port,
          timeout: const Duration(milliseconds: 450));
      socket.add([5, 1, 0]);
      await socket.flush();
      final bytes = await socket.first.timeout(const Duration(seconds: 1));
      return bytes.length >= 2 && bytes[0] == 5 && bytes[1] == 0;
    } catch (_) { return false; } finally { socket?.destroy(); }
  }

  static Future<String> _verifyRemoteExit(int port) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 4)
      ..findProxy = (_) => 'PROXY 127.0.0.1:$port';
    try {
      for (var i = 0; i < 3; i++) {
        try {
          final request = await client.getUrl(
            Uri.https('api.ipify.org', '/', {'format': 'json'}),
          ).timeout(const Duration(seconds: 5));
          request.followRedirects = false;
          final response = await request.close()
              .timeout(const Duration(seconds: 6));
          if (response.statusCode != HttpStatus.ok) continue;
          final body = await utf8.decoder.bind(response).join()
              .timeout(const Duration(seconds: 6));
          if (body.length > 512) continue;
          final data = jsonDecode(body);
          if (data is Map && data['ip'] is String) {
            return XrayEndpointRoute.requirePublicIPv4(data['ip'] as String);
          }
        } catch (_) {
          // Retry without exposing secret-bearing engine diagnostics.
        }
      }
      throw const FormatException('MIERU_REMOTE_EGRESS_UNVERIFIED');
    } finally { client.close(force: true); }
  }

  Future<void> _finishConfigStage() async {
    try {
      await _native.invokeMethod<bool>('finishMieruConfig')
          .timeout(const Duration(seconds: 4));
    } catch (_) {
      // Native shutdown and stale-file cleanup retain fail-closed behavior.
    }
  }

  Future<void> _terminate() async {
    final child = _child;
    if (child != null) {
      child.kill();
      try {
        await child.exitCode.timeout(const Duration(seconds: 7));
      } catch (_) {
        throw const FormatException('MIERU_CORE_DID_NOT_STOP');
      }
    }
    _child = null;
    _port = null;
    _verifiedExitIp = null;
    _endpointIpv4 = null;
  }

  Future<void> stop() async {
    if (_changing) throw const FormatException('MIERU_PROXY_BUSY');
    _changing = true;
    try { await _terminate(); } finally {
      await _finishConfigStage();
      _changing = false;
    }
  }

  void dispose() {
    _child?.kill();
    _child = null;
    _port = null;
    _verifiedExitIp = null;
    _endpointIpv4 = null;
    unawaited(_finishConfigStage());
  }
}
