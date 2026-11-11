import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';

import 'cisco_openconnect_profile.dart';

/// OpenConnect is owned by the native Windows console process group.
/// The app never calls Process.kill, to preserve disconnect route cleanup.
class WindowsOpenConnectTunnel {
  static const _channel = MethodChannel('com.twinpanel.twinconnect/vpn');
  String? _exitIp;
  String? _baselineIp;
  bool _pending = false;
  bool _nativeActive = false;

  bool get isRunning => _nativeActive;
  String? get exitIp => _exitIp;

  static Future<({String executable, String script})?> _engine() async {
    if (!Platform.isWindows) return null;
    final folder = Directory(
        File(Platform.resolvedExecutable).parent.path +
        r'\engines\openconnect');
    final manifest = File(folder.path + r'\OPENCONNECT-ENGINE-MANIFEST.txt');
    if (!await manifest.exists()) return null;
    final data = await manifest.readAsLines();
    String? value(String key) {
      for (final row in data) {
        if (row.startsWith(key + ': ')) return row.substring(key.length + 2);
      }
      return null;
    }
    final cli = value('CLI');
    final script = value('Windows route script');
    if (cli == null || script == null) return null;
    String? verifiedPath(String relative, Set<String> basenames) {
      final normalized = relative.replaceAll('/', String.fromCharCode(92));
      if (normalized.contains('..') || normalized.contains(':') ||
          normalized.startsWith(String.fromCharCode(92)) || normalized.contains('\n') ||
          normalized.contains('\r')) return null;
      final leaf = normalized.split(String.fromCharCode(92)).last.toLowerCase();
      if (!basenames.contains(leaf)) return null;
      return folder.path + String.fromCharCode(92) + normalized;
    }
    final executable = verifiedPath(cli, {'openconnect.exe'});
    final vpnScript = verifiedPath(script, {
      'vpnc-script-win.js', 'vpnc-script.js',
    });
    if (executable == null || vpnScript == null ||
        !await File(executable).exists() || !await File(vpnScript).exists()) {
      return null;
    }
    return (executable: executable, script: vpnScript);
  }

  static Future<bool> enginePresent() async => await _engine() != null;

  static Future<String> _publicIp() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 3)
      ..findProxy = (_) => 'DIRECT';
    try {
      final req = await client.getUrl(Uri.https('api.ipify.org', '/', {
        'format': 'json',
      })).timeout(const Duration(seconds: 5));
      final response = await req.close().timeout(const Duration(seconds: 5));
      if (response.statusCode != HttpStatus.ok) {
        throw const FormatException('CISCO_PUBLIC_IP_UNAVAILABLE');
      }
      final raw = await utf8.decoder.bind(response).join().timeout(
          const Duration(seconds: 5));
      if (raw.length > 512) throw const FormatException('CISCO_BAD_PUBLIC_IP');
      final decoded = jsonDecode(raw);
      if (decoded is! Map || decoded['ip'] is! String) {
        throw const FormatException('CISCO_BAD_PUBLIC_IP');
      }
      final ip = InternetAddress.tryParse(decoded['ip'] as String);
      if (ip == null || ip.type != InternetAddressType.IPv4) {
        throw const FormatException('CISCO_BAD_PUBLIC_IP');
      }
      return ip.address;
    } finally {
      client.close(force: true);
    }
  }

  Future<bool> checkHealth() async {
    if (!_nativeActive || _exitIp == null) return false;
    try {
      final up = await _channel.invokeMethod<bool>('openConnectStatus')
          .timeout(const Duration(seconds: 6));
      if (up != true) {
        _nativeActive = false;
        _exitIp = null;
        return false;
      }
      final ip = await _publicIp().timeout(const Duration(seconds: 8));
      return _nativeActive && ip == _exitIp;
    } catch (_) {
      return false;
    }
  }

  Future<String> start(CiscoOpenConnectProfile profile) async {
    if (!Platform.isWindows) {
      throw const FormatException('CISCO_WINDOWS_ONLY');
    }
    if (_pending || _nativeActive) {
      throw const FormatException('CISCO_TUNNEL_BUSY');
    }
    _pending = true;
    try {
      final engine = await _engine();
      if (engine == null) {
        throw const FormatException('CISCO_ENGINE_UNAVAILABLE');
      }
      _baselineIp = await _publicIp().timeout(const Duration(seconds: 10));
      final started = await _channel.invokeMethod<bool>('startOpenConnect', {
        'executable': engine.executable,
        'script': engine.script,
        'gateway': profile.gateway,
        'username': profile.username,
        'password': profile.password,
        'servercert': profile.serverCertificate ?? '',
      }).timeout(const Duration(seconds: 10));
      if (started != true) {
        throw const FormatException('CISCO_NATIVE_START_FAILED');
      }
      _nativeActive = true;
      final watch = Stopwatch()..start();
      while (watch.elapsed < const Duration(seconds: 43)) {
        final running = await _channel.invokeMethod<bool>('openConnectStatus')
            .timeout(const Duration(seconds: 5));
        if (running != true) {
          _nativeActive = false;
          // Only a coarse native category is exposed. Raw upstream stderr
          // could contain endpoint/user details and must never reach UI.
          String reason = 'CISCO_PROCESS_EXITED';
          try {
            final result = await _channel.invokeMethod<String>(
                'openConnectExitReason').timeout(const Duration(seconds: 4));
            if (result != null && const {
              'CISCO_CERTIFICATE_UNTRUSTED',
              'CISCO_AUTHENTICATION_FAILED',
              'CISCO_ROUTE_SCRIPT_FAILED',
              'CISCO_TAP_ADAPTER_FAILED',
              'CISCO_GATEWAY_UNREACHABLE',
              'CISCO_PROCESS_EXITED',
            }.contains(result)) {
              reason = result;
            }
          } catch (_) {
            // A missing diagnostic never bypasses the fail-closed state.
          }
          throw FormatException(reason);
        }
        try {
          final ip = await _publicIp().timeout(const Duration(seconds: 7));
          if (ip != _baselineIp) {
            _exitIp = ip;
            return ip;
          }
        } catch (_) {
          // No green/connected state before real HTTPS egress.
        }
        await Future<void>.delayed(const Duration(milliseconds: 850));
      }
      throw const FormatException('CISCO_EGRESS_NOT_VERIFIED');
    } catch (_) {
      if (_nativeActive) {
        try {
          final stopped = await _channel.invokeMethod<bool>(
              'stopOpenConnect').timeout(const Duration(seconds: 18));
          if (stopped != true) {
            throw const FormatException('CISCO_GRACEFUL_DISCONNECT_FAILED');
          }
          _nativeActive = false;
        } catch (_) {
          throw const FormatException('CISCO_GRACEFUL_DISCONNECT_FAILED');
        }
      }
      _exitIp = null;
      rethrow;
    } finally {
      _pending = false;
    }
  }

  Future<void> stop() async {
    if (_pending) throw const FormatException('CISCO_TUNNEL_BUSY');
    if (!_nativeActive) return;
    _pending = true;
    try {
      final stopped = await _channel.invokeMethod<bool>('stopOpenConnect')
          .timeout(const Duration(seconds: 18));
      if (stopped != true) {
        throw const FormatException('CISCO_GRACEFUL_DISCONNECT_FAILED');
      }
      _nativeActive = false;
      _exitIp = null;
      final now = await _publicIp().timeout(const Duration(seconds: 10));
      if (_baselineIp != null && now != _baselineIp) {
        throw const FormatException('CISCO_ROUTE_RESTORE_UNVERIFIED');
      }
    } finally {
      _pending = false;
    }
  }
}
