import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'sudoku_client_profile.dart';
import 'xray_endpoint_route.dart';

/// Official SUDOKU-ASCII core, running as a guarded loopback mixed
/// SOCKS5/HTTP proxy. A live local proxy is NOT yet a system-wide VPN:
/// the separately verified sing-box TUN must carry its traffic.
class WindowsSudokuProxy {
  WindowsSudokuProxy({this.onUnexpectedExit});
  static const _native = MethodChannel('com.twinpanel.twinconnect/vpn');
  final void Function()? onUnexpectedExit;

  Process? _child;
  int? _port;
  String? _verifiedExit;
  String? _endpointIpv4;
  bool _changing = false;
  // Never retain engine stderr: it can contain customer credentials.
  // Store only a coarse, known-safe error category and numeric exit code.
  String? _lastFailureCategory;
  int? _lastUnexpectedExitCode;
  String? get lastUnexpectedExitReason {
    final failure = _lastFailureCategory;
    if (failure != null) return failure;
    if (_lastUnexpectedExitCode == 0) return 'SUDOKU_CORE_EXITED_CLEANLY';
    final code = _lastUnexpectedExitCode;
    if (code != null) {
      // Windows NTSTATUS and ordinary process return codes are numeric,
      // not raw native logs. Show only these safe, bounded diagnostics.
      return 'SUDOKU_CORE_EXIT_CODE_${code.toUnsigned(32).toRadixString(16).padLeft(8, '0')}';
    }
    return 'SUDOKU_CORE_EXITED';
  }

  static String? _classifyNativeFailure(String line) {
    // The official SUDOKU-ASCII logx implementation emits fatal errors to
    // stdout, not stderr. Keep no raw output or credential-bearing message.
    final value = line.toLowerCase();
    if (value.contains('address already in use') ||
        (value.contains('listen') && value.contains('bind'))) {
      return 'SUDOKU_LOCAL_PORT_CONFLICT';
    }
    if (value.contains('access is denied') ||
        value.contains('permission denied')) {
      return 'SUDOKU_CORE_ACCESS_DENIED';
    }
    if (value.contains('failed to load config') ||
        (value.contains('config') &&
         (value.contains('invalid') || value.contains('open') ||
          value.contains('parse') || value.contains('decode')))) {
      return 'SUDOKU_CONFIG_LOAD_FAILED';
    }
    if (value.contains('failed to build client table') ||
        value.contains('failed to build table')) {
      return 'SUDOKU_TABLE_INIT_FAILED';
    }
    if (value.contains('failed to initialize client nodes')) {
      return 'SUDOKU_CLIENT_INIT_FAILED';
    }
    if (value.contains('key') &&
        (value.contains('invalid') || value.contains('decode') ||
         value.contains('recover'))) {
      return 'SUDOKU_KEY_REJECTED';
    }
    return null;
  }

  void _consumeNativeDiagnostic(Process owned, Stream<List<int>> output) {
    unawaited(utf8.decoder.bind(output)
        .transform(const LineSplitter()).forEach((line) {
      final category = _classifyNativeFailure(line);
      if (category != null && identical(_child, owned)) {
        _lastFailureCategory = category;
      }
    }).catchError((Object _) {}));
  }

  bool get isRunning => _child != null && _port != null;
  int? get socksPort => isRunning ? _port : null;
  String? get verifiedExitIp => isRunning ? _verifiedExit : null;
  String? get endpointIpv4 => isRunning ? _endpointIpv4 : null;

  static String binaryPath() {
    return '${File(Platform.resolvedExecutable).parent.path}'
        '\\engines\\sudoku\\sudoku.exe';
  }

  static Future<bool> enginePresent() async {
    if (!Platform.isWindows) return false;
    try {
      return await File(binaryPath()).exists();
    } catch (_) {
      return false;
    }
  }

  static Future<String> _resolveIpv4(String host) async {
    final literal = InternetAddress.tryParse(host);
    if (literal != null) {
      return XrayEndpointRoute.requirePublicIPv4(literal.address);
    }
    try {
      final rows = await InternetAddress.lookup(
        host, type: InternetAddressType.IPv4,
      ).timeout(const Duration(seconds: 5));
      for (final address in rows) {
        try {
          return XrayEndpointRoute.requirePublicIPv4(address.address);
        } on FormatException {
          // Do not pin poisoned / internal DNS answers.
        }
      }
    } catch (_) {}
    throw const FormatException('SUDOKU_ENDPOINT_DNS_UNAVAILABLE');
  }

  Future<int> start(SudokuClientProfile profile) async {
    if (!Platform.isWindows) {
      throw const FormatException('SUDOKU_WINDOWS_ONLY');
    }
    if (_child != null || _changing) {
      throw const FormatException('SUDOKU_PROXY_BUSY');
    }
    _changing = true;
    _lastFailureCategory = null;
    _lastUnexpectedExitCode = null;
    try {
      if (!await enginePresent()) {
        throw const FormatException('SUDOKU_ENGINE_NOT_BUNDLED');
      }
      final hostIp = await _resolveIpv4(profile.host);
      final listener = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final localPort = listener.port;
      await listener.close();
      final config = profile.runtimeConfig(
          serverIpv4: hostIp, localPort: localPort);
      // The official Sudoku core requires -c <filename>. The native
      // runner stages the config in a user-SID-only, delete-on-close
      // temporary Windows file, never as a CLI argument or public JSON.
      final path = await _native.invokeMethod<String>(
        'stageSudokuConfig', {'config': jsonEncode(config)},
      ).timeout(const Duration(seconds: 5), onTimeout: () =>
          throw const FormatException('SUDOKU_CONFIG_STAGE_TIMEOUT'));
      if (path == null || path.isEmpty) {
        throw const FormatException('SUDOKU_PRIVATE_CONFIG_STAGE_FAILED');
      }
      final owned = await Process.start(
        binaryPath(), ['-c', path], runInShell: false,
      ).timeout(const Duration(seconds: 7), onTimeout: () =>
          throw const FormatException('SUDOKU_PROCESS_START_TIMEOUT'));
      _child = owned;
      final guarded = await _native.invokeMethod<bool>(
        'guardSudokuProcess', {'pid': owned.pid},
      ).timeout(const Duration(seconds: 5), onTimeout: () =>
          throw const FormatException('SUDOKU_PROCESS_GUARD_TIMEOUT'));
      if (guarded != true) {
        throw const FormatException('SUDOKU_PROCESS_GUARD_UNAVAILABLE');
      }
      // The config handle remains open until the core has opened SOCKS.
      // Never log the native core's output: it may contain private keys.
      // Official Sudoku Fatalf -> logx.Errorf -> stdout, so both streams
      // must be consumed. Never persist or print either stream.
      _consumeNativeDiagnostic(owned, owned.stdout);
      _consumeNativeDiagnostic(owned, owned.stderr);
      unawaited(owned.exitCode.then((code) {
        if (identical(_child, owned)) {
          _lastUnexpectedExitCode = code;
          _child = null;
          _port = null;
          _verifiedExit = null;
          _endpointIpv4 = null;
          if (!_changing) onUnexpectedExit?.call();
        }
      }));
      var ready = false;
      for (var attempt = 0; attempt < 30; attempt++) {
        if (!identical(_child, owned)) {
          throw FormatException(lastUnexpectedExitReason ?? 'SUDOKU_CORE_EXITED');
        }
        if (await _socksReady(localPort)) {
          ready = true;
          break;
        }
        await Future<void>.delayed(const Duration(milliseconds: 150));
      }
      if (!ready || !identical(_child, owned)) {
        throw const FormatException('SUDOKU_LOOPBACK_PROXY_UNAVAILABLE');
      }
      // The core already read its config: close the delete-on-close handle
      // before attempting remote HTTPS. No private key file remains.
      await _finishConfigStage();
      final exit = await _verifyRemoteExit(localPort);
      if (!identical(_child, owned)) {
        throw FormatException(lastUnexpectedExitReason ?? 'SUDOKU_CORE_EXITED');
      }
      _port = localPort;
      _verifiedExit = exit;
      _endpointIpv4 = hostIp;
      return localPort;
    } catch (_) {
      await _terminate();
      rethrow;
    } finally {
      // Cleanup also runs when Process.start, guarding, or SOCKS fails.
      await _finishConfigStage();
      _changing = false;
    }
  }

  static Future<bool> _socksReady(int port) async {
    Socket? socket;
    try {
      socket = await Socket.connect(
        InternetAddress.loopbackIPv4, port,
        timeout: const Duration(milliseconds: 400),
      );
      socket.add(const [5, 1, 0]);
      await socket.flush();
      final response = await socket.first
          .timeout(const Duration(milliseconds: 600));
      return response.length >= 2 &&
          response[0] == 5 && response[1] == 0;
    } catch (_) {
      return false;
    } finally {
      socket?.destroy();
    }
  }

  static Future<String> _verifyRemoteExit(int port) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 3)
      ..findProxy = (_) => 'PROXY 127.0.0.1:$port';
    try {
      final deadline = Stopwatch()..start();
      for (var attempt = 0; attempt < 3 &&
          deadline.elapsed < const Duration(seconds: 10); attempt++) {
        try {
          final req = await client.getUrl(
            Uri.https('api.ipify.org', '/', {'format': 'json'}),
          ).timeout(const Duration(seconds: 4));
          req.followRedirects = false;
          final res = await req.close()
              .timeout(const Duration(seconds: 5));
          if (res.statusCode != HttpStatus.ok) {
            throw const FormatException('SUDOKU_REMOTE_EGRESS_UNVERIFIED');
          }
          final body = await utf8.decoder.bind(res).join()
              .timeout(const Duration(seconds: 5));
          if (body.length > 512) {
            throw const FormatException('SUDOKU_REMOTE_EGRESS_UNVERIFIED');
          }
          final parsed = jsonDecode(body);
          final raw = parsed is Map ? parsed['ip'] : null;
          if (raw is! String) {
            throw const FormatException('SUDOKU_REMOTE_EGRESS_UNVERIFIED');
          }
          return XrayEndpointRoute.requirePublicIPv4(raw);
        } catch (_) {
          if (attempt < 2) {
            await Future<void>.delayed(
                const Duration(milliseconds: 200));
          }
        }
      }
      throw const FormatException('SUDOKU_REMOTE_EGRESS_UNVERIFIED');
    } finally {
      client.close(force: true);
    }
  }

  Future<void> _finishConfigStage() async {
    try {
      await _native.invokeMethod<bool>('finishSudokuConfig')
          .timeout(const Duration(seconds: 4));
    } catch (_) {
      // The native config handle will still be deleted by the OS if the
      // parent process exits. Never display config path in error text.
    }
  }

  void dispose() {
    _child?.kill();
    _child = null;
    _port = null;
    _verifiedExit = null;
    _endpointIpv4 = null;
    unawaited(_finishConfigStage());
  }

  Future<void> stop() async {
    if (_changing) throw const FormatException('SUDOKU_PROXY_BUSY');
    _changing = true;
    try {
      await _terminate();
    } finally {
      _changing = false;
    }
  }

  Future<void> _terminate() async {
    final child = _child;
    if (child == null) {
      _port = null;
      _verifiedExit = null;
      _endpointIpv4 = null;
      return;
    }
    child.kill();
    try {
      await child.exitCode.timeout(const Duration(seconds: 7));
    } on TimeoutException {
      throw const FormatException('SUDOKU_CORE_DID_NOT_STOP');
    }
    if (identical(_child, child)) _child = null;
    _port = null;
    _verifiedExit = null;
    _endpointIpv4 = null;
  }
}
