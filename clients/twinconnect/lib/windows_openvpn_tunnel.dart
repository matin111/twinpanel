import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/services.dart';
import 'openvpn_profile_validator.dart';

/// Manages OpenVPN Community on Windows separately from Cisco and sing-box.
/// No private profile or daemon output is ever logged or exposed in the UI.
class WindowsOpenVpnTunnel {
  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');
  Process? _process;
  File? _config, _password;
  int? _managementPort;
  String? _exitIp;
  bool _ready = false, _busy = false;

  bool get isRunning => _ready && _process != null;
  String? get exitIp => _exitIp;

  static String? get enginePath {
    if (!Platform.isWindows) return null;
    final root = Platform.environment['ProgramFiles'];
    if (root == null || root.isEmpty) return null;
    return root + r'\OpenVPN\bin\openvpn.exe';
  }
  static Future<bool> enginePresent() async =>
      enginePath != null && await File(enginePath!).exists();

  static String secret() {
    final random = Random.secure();
    return base64UrlEncode(List<int>.generate(48, (_) => random.nextInt(256)))
        .replaceAll('=', '');
  }

  static Future<String> publicIp() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 4)
      ..findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(
          Uri.https('api.ipify.org', '/', {'format': 'json'}))
          .timeout(const Duration(seconds: 6));
      final response = await request.close()
          .timeout(const Duration(seconds: 6));
      if (response.statusCode != 200) {
        throw const FormatException('OPENVPN_PUBLIC_IP_UNAVAILABLE');
      }
      final body = await utf8.decoder.bind(response).join()
          .timeout(const Duration(seconds: 6));
      if (body.length > 512) throw const FormatException('OPENVPN_BAD_PUBLIC_IP');
      final data = jsonDecode(body);
      final ip = data is Map ? data['ip'] : null;
      final parsed = ip is String ? InternetAddress.tryParse(ip) : null;
      if (parsed == null || parsed.type != InternetAddressType.IPv4) {
        throw const FormatException('OPENVPN_BAD_PUBLIC_IP');
      }
      return parsed.address;
    } finally {
      client.close(force: true);
    }
  }

  Future<({int received, int sent})?> readTrafficTotals() async {
    if (!isRunning) return null;
    try {
      final values = await _channel.invokeMapMethod<String, dynamic>(
          'openVpnTraffic').timeout(const Duration(seconds: 5));
      final rx = values?['rxBytes'], tx = values?['txBytes'];
      if (rx is int && tx is int && rx >= 0 && tx >= 0) {
        return (received: rx, sent: tx);
      }
    } catch (_) {}
    return null;
  }

  Future<bool> checkHealth() async {
    if (!isRunning || _exitIp == null) return false;
    try {
      return await publicIp().timeout(const Duration(seconds: 8)) == _exitIp;
    } catch (_) { return false; }
  }

  Future<String> start(Map<String, dynamic> item) async {
    if (!Platform.isWindows) throw const FormatException('OPENVPN_WINDOWS_ONLY');
    if (_busy || _process != null) {
      throw const FormatException('OPENVPN_ALREADY_RUNNING');
    }
    final config = OpenVpnProfileValidator.validate(item);
    final binary = enginePath;
    if (binary == null || !await File(binary).exists()) {
      throw const FormatException('OPENVPN_ENGINE_NOT_INSTALLED');
    }
    _busy = true;
    try {
      final before = await publicIp();
      final local = Platform.environment['LOCALAPPDATA'];
      if (local == null || local.isEmpty) {
        throw const FormatException('OPENVPN_STORAGE_UNAVAILABLE');
      }
      final privateDir = Directory(local + r'\TwinConnect\private');
      await privateDir.create(recursive: true);
      final id = secret();
      _config = File(privateDir.path + '\\' + id + '.ovpn');
      _password = File(privateDir.path + '\\' + id + '.pwd');
      await _config!.writeAsString(config, flush: true);
      await _password!.writeAsString(secret() + '\n', flush: true);

      final reservation = await ServerSocket.bind(
          InternetAddress.loopbackIPv4, 0);
      _managementPort = reservation.port;
      await reservation.close();
      final ready = Completer<void>();
      final child = await Process.start(binary, [
        '--config', _config!.path,
        '--management', '127.0.0.1', _managementPort.toString(),
        _password!.path, '--auth-nocache', '--verb', '3',
      ], runInShell: false);
      _process = child;
      for (final output in [child.stdout, child.stderr]) {
        output.transform(utf8.decoder).transform(const LineSplitter()).listen(
          (line) {
            final lower = line.toLowerCase();
            if (lower.contains('initialization sequence completed') &&
                !ready.isCompleted) ready.complete();
            if ((lower.contains('auth_failed') ||
                 lower.contains('certificate verify failed') ||
                 lower.contains('cannot open tun/tap')) &&
                 !ready.isCompleted) {
              ready.completeError(const FormatException('OPENVPN_ENGINE_START_FAILED'));
            }
            // Raw stdout contains sensitive endpoints. Never log or return it.
          },
          onError: (_) {
            if (!ready.isCompleted) {
              ready.completeError(const FormatException('OPENVPN_ENGINE_IO_FAILED'));
            }
          },
        );
      }
      child.exitCode.then((_) {
        _ready = false;
        _exitIp = null;
        if (!ready.isCompleted) {
          ready.completeError(const FormatException('OPENVPN_PROCESS_EXITED'));
        }
        // Remove secrets when OpenVPN exits on its own, not just on Disconnect.
        unawaited(_cleanupIfExited());
      });
      await ready.future.timeout(const Duration(seconds: 55),
          onTimeout: () => throw const FormatException('OPENVPN_START_TIMEOUT'));
      final ip = await publicIp();
      if (ip == before) {
        throw const FormatException('OPENVPN_EGRESS_NOT_VERIFIED');
      }
      _exitIp = ip;
      _ready = true;
      return ip;
    } catch (_) {
      try { await _signalStop(); } catch (_) {}
      await _cleanupIfExited();
      rethrow;
    } finally { _busy = false; }
  }

  Future<void> _signalStop() async {
    final port = _managementPort;
    if (port == null || _password == null || _process == null) return;
    final password = (await _password!.readAsString()).trim();
    final child = _process!;
    final socket = await Socket.connect(InternetAddress.loopbackIPv4, port,
        timeout: const Duration(seconds: 4));
    final sent = Completer<void>();
    var authenticated = false;
    var passwordSubmitted = false;
    var reply = '';
    socket.cast<List<int>>().transform(utf8.decoder).listen((message) {
      reply = (reply + message);
      if (reply.length > 2048) reply = reply.substring(reply.length - 2048);
      if (!passwordSubmitted && reply.contains('ENTER PASSWORD:')) {
        passwordSubmitted = true;
        reply = '';
        socket.write(password + '\n');
      } else if (passwordSubmitted && !authenticated &&
          (reply.contains('SUCCESS:') || reply.contains('>INFO:'))) {
        authenticated = true;
        reply = '';
        socket.write('signal SIGTERM\n');
        if (!sent.isCompleted) sent.complete();
      } else if (reply.contains('ERROR:') && !sent.isCompleted) {
        sent.completeError(const FormatException('OPENVPN_STOP_REJECTED'));
      }
    }, onError: (_) {
      if (!sent.isCompleted) {
        sent.completeError(const FormatException('OPENVPN_STOP_IO_ERROR'));
      }
    });
    try {
      await sent.future.timeout(const Duration(seconds: 6));
      await child.exitCode.timeout(const Duration(seconds: 15));
    } finally { socket.destroy(); }
  }

  Future<void> _cleanupIfExited() async {
    if (_process != null) {
      try {
        await _process!.exitCode.timeout(const Duration(milliseconds: 250));
      } on TimeoutException { return; }
    }
    _process = null;
    _ready = false;
    _exitIp = null;
    _managementPort = null;
    for (final file in [_config, _password]) {
      if (file == null) continue;
      try { if (await file.exists()) await file.delete(); } catch (_) {}
    }
    _config = null;
    _password = null;
  }

  Future<void> stop() async {
    if (_busy) throw const FormatException('OPENVPN_BUSY');
    _busy = true;
    try {
      if (_process != null) await _signalStop();
      await _cleanupIfExited();
      if (_process != null) {
        throw const FormatException('OPENVPN_DISCONNECT_NOT_CONFIRMED');
      }
    } finally { _busy = false; }
  }
}
