import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'cisco_openconnect_profile.dart';

/// Owner of a single OpenConnect Windows CLI child. Requires an independently
/// installed trusted OpenConnect-GUI package including vpnc-script-win.js and
/// its Windows TUN driver. This is not a persistent VPN service or kill switch.
/// Never log credentials, pass the password on the command line, or bypass TLS.
class WindowsOpenConnectTunnel {
  WindowsOpenConnectTunnel({this.onUnexpectedExit});
  final void Function()? onUnexpectedExit;

  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  Process? _child;
  bool _changing = false;
  String? _verifiedIp;

  bool get isRunning => _child != null && _verifiedIp != null;
  String? get publicIp => isRunning ? _verifiedIp : null;

  static Future<String?> findInstalledEngine() async {
    if (!Platform.isWindows) return null;
    final directories = <String>{
      if (Platform.environment['ProgramFiles'] case final String p) p,
      if (Platform.environment['ProgramFiles(x86)'] case final String p) p,
    };
    for (final root in directories) {
      for (final folder in ['OpenConnect-GUI', 'OpenConnect']) {
        final directory = '$root\\$folder';
        final exe = File('$directory\\openconnect.exe');
        final script = File('$directory\\vpnc-script-win.js');
        if (await exe.exists() && await script.exists()) return exe.path;
      }
    }
    return null;
  }

  static Future<String> _publicIPv4() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 3)
      ..findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(
          Uri.https('api.ipify.org', '/', {'format': 'json'}))
          .timeout(const Duration(seconds: 5));
      final response = await request.close().timeout(
          const Duration(seconds: 5));
      if (response.statusCode != HttpStatus.ok) {
        throw const FormatException('CISCO_PUBLIC_IP_UNAVAILABLE');
      }
      final body = await utf8.decoder.bind(response).join()
          .timeout(const Duration(seconds: 5));
      if (body.length > 512) {
        throw const FormatException('CISCO_PUBLIC_IP_INVALID');
      }
      final decoded = jsonDecode(body);
      if (decoded is! Map || decoded['ip'] is! String) {
        throw const FormatException('CISCO_PUBLIC_IP_INVALID');
      }
      final ip = InternetAddress.tryParse(decoded['ip'] as String);
      if (ip == null || ip.type != InternetAddressType.IPv4) {
        throw const FormatException('CISCO_PUBLIC_IP_INVALID');
      }
      return ip.address;
    } finally {
      client.close(force: true);
    }
  }

  Future<bool> checkHealth() async {
    if (!isRunning) return false;
    try {
      final ip = await _publicIPv4().timeout(const Duration(seconds: 7));
      return isRunning && ip == _verifiedIp;
    } catch (_) {
      return false;
    }
  }

  Future<String> start(CiscoOpenConnectProfile profile) async {
    if (!Platform.isWindows) throw const FormatException('CISCO_WINDOWS_ONLY');
    if (_child != null || _changing) {
      throw const FormatException('CISCO_TUNNEL_BUSY');
    }
    _changing = true;
    Process? process;
    try {
      final engine = await findInstalledEngine();
      if (engine == null) {
        throw const FormatException('CISCO_OPENCONNECT_NOT_INSTALLED');
      }
      // The connection is not considered online until the Windows system
      // HTTPS egress IP has actually changed.
      final before = await _publicIPv4().timeout(
          const Duration(seconds: 10));
      final arguments = <String>[
        '--protocol=anyconnect',
        '--non-inter',
        '--passwd-on-stdin',
        '--user=${profile.username}',
        if (profile.serverCertificate != null)
          '--servercert=${profile.serverCertificate}',
        // The script is shipped next to the official CLI by its installer.
        '--script=vpnc-script-win.js',
        profile.gateway,
      ];
      process = await Process.start(engine, arguments,
          workingDirectory: File(engine).parent.path, runInShell: false)
          .timeout(const Duration(seconds: 8));
      final child = process;
      // Credential delivery and route installation are forbidden until the
      // native Job Object verifies the exact installed executable path.
      final guarded = await _channel.invokeMethod<bool>(
          'guardOpenConnectProcess', {'pid': child.pid})
          .timeout(const Duration(seconds: 6));
      if (guarded != true) {
        throw const FormatException('CISCO_PROCESS_GUARD_UNAVAILABLE');
      }
      _child = child;
      // OpenConnect output may contain sensitive connection parameters.
      unawaited(child.stdout.drain<void>());
      unawaited(child.stderr.drain<void>());
      var exited = false;
      unawaited(child.exitCode.then((_) {
        exited = true;
        if (identical(_child, child) && !_changing) {
          _child = null;
          _verifiedIp = null;
          onUnexpectedExit?.call();
        }
      }));
      child.stdin.add(utf8.encode('${profile.password}\n'));
      await child.stdin.close();
      final clock = Stopwatch()..start();
      while (clock.elapsed < const Duration(seconds: 32)) {
        if (exited) throw const FormatException('CISCO_PROCESS_EXITED');
        await Future<void>.delayed(const Duration(milliseconds: 650));
        if (exited) throw const FormatException('CISCO_PROCESS_EXITED');
        try {
          final after = await _publicIPv4().timeout(
              const Duration(seconds: 5));
          if (after != before) {
            _verifiedIp = after;
            return after;
          }
        } catch (_) {
          // A temporary failed HTTPS check never establishes connectivity.
        }
      }
      throw const FormatException('CISCO_TUNNEL_ROUTE_NOT_VERIFIED');
    } catch (_) {
      process?.kill(ProcessSignal.sigint);
      if (process != null) {
        try {
          await process.exitCode.timeout(const Duration(seconds: 6));
        } catch (_) {
          process.kill();
        }
      }
      _child = null;
      _verifiedIp = null;
      rethrow;
    } finally {
      _changing = false;
    }
  }

  Future<void> stop() async {
    if (_changing) throw const FormatException('CISCO_TUNNEL_BUSY');
    final child = _child;
    if (child == null) return;
    _changing = true;
    try {
      // Prefer SIGINT to allow OpenConnect/vpnc-script teardown. Do not
      // assert routes are restored merely because the child exited.
      child.kill(ProcessSignal.sigint);
      await child.exitCode.timeout(const Duration(seconds: 9));
      _child = null;
      _verifiedIp = null;
    } on TimeoutException {
      throw const FormatException('CISCO_TUNNEL_STOP_UNVERIFIED');
    } finally {
      _changing = false;
    }
  }

  void dispose() {
    _child?.kill(ProcessSignal.sigint);
  }
}
