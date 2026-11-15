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
  String? _lastHealthError;

  bool get isRunning => _nativeActive;
  String? get exitIp => _exitIp;
  String? get lastHealthError => _lastHealthError;

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

  /// Returns real OS interface byte totals for the verified Cisco route.
  /// No whole-system fallback; null means the VPN interface was not identified.
  Future<({int received, int sent})?> readTrafficTotals() async {
    if (!_nativeActive || _exitIp == null) return null;
    try {
      final raw = await _channel.invokeMapMethod<String, dynamic>(
          'openConnectTraffic').timeout(const Duration(seconds: 5));
      if (raw == null) return null;
      final rx = raw['rxBytes'];
      final tx = raw['txBytes'];
      if (rx is! int || tx is! int || rx < 0 || tx < 0) return null;
      return (received: rx, sent: tx);
    } catch (_) {
      return null;
    }
  }

  Future<bool> checkHealth() async {
    if (!_nativeActive || _exitIp == null) return false;
    // Check whether the owned OpenConnect process is still alive first.
    // A failed third-party HTTPS IP probe cannot establish that a native
    // tunnel has exited; do not mark Cisco disconnected on that basis.
    try {
      final up = await _channel.invokeMethod<bool>('openConnectStatus')
          .timeout(const Duration(seconds: 6));
      if (up != true) {
        _nativeActive = false;
        _exitIp = null;
        _lastHealthError = 'CISCO_PROCESS_EXITED';
        return false;
      }
    } catch (_) {
      _lastHealthError = 'CISCO_NATIVE_STATUS_UNAVAILABLE';
      return false;
    }

    try {
      final ip = await _publicIp().timeout(const Duration(seconds: 8));
      if (ip == _baselineIp) {
        // An independently observed return to the pre-VPN egress is not a
        // verified tunnel. Keep the child owned so Disconnect can clean it.
        _lastHealthError = 'CISCO_ROUTE_BYPASS_DETECTED';
        return false;
      }
      // An exit server can rotate its public IP. It must still differ from
      // the pre-tunnel baseline before the new address can be accepted.
      _exitIp = ip;
      _lastHealthError = null;
      return true;
    } catch (_) {
      // The process was just verified alive. This is indeterminate egress,
      // NOT a native disconnect. Retain the last verified IP and surface a
      // warning without a false stop/reconnect cycle.
      _lastHealthError = 'CISCO_EGRESS_RECHECK_UNAVAILABLE';
      return true;
    }
  }

  static Future<String> directPublicIp() => _publicIp();

  Future<String> start(CiscoOpenConnectProfile profile, {String? baselinePublicIp}) async {
    if (!Platform.isWindows) {
      throw const FormatException('CISCO_WINDOWS_ONLY');
    }
    if (_pending || _nativeActive) {
      throw const FormatException('CISCO_TUNNEL_BUSY');
    }
    if (baselinePublicIp != null &&
        InternetAddress.tryParse(baselinePublicIp)?.type !=
            InternetAddressType.IPv4) {
      throw const FormatException('BASELINE_IP_UNAVAILABLE');
    }
    _pending = true;
    _lastHealthError = null;
    try {
      // Engine file inspection and the direct baseline HTTPS request are
      // both read-only. Run them together, but never start the OS tunnel
      // until BOTH succeeded. Baseline remains measured before route changes.
      final prerequisites = await Future.wait<Object?>([
        _engine(),
        baselinePublicIp == null
            ? _publicIp().timeout(const Duration(seconds: 10))
            : Future<String>.value(baselinePublicIp),
      ]);
      final engine = prerequisites[0] as ({String executable, String script})?;
      if (engine == null) {
        throw const FormatException('CISCO_ENGINE_UNAVAILABLE');
      }
      _baselineIp = prerequisites[1] as String;
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
              'CISCO_ENGINE_DEPENDENCY_FAILED',
              'CISCO_POST_AUTH_TUNNEL_FAILED',
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
        // No fixed ~1s penalty after every RAS/route check; the real
        // HTTPS exit probe and native status remain mandatory.
        await Future<void>.delayed(const Duration(milliseconds: 300));
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
      _lastHealthError = null;
      final now = await _publicIp().timeout(const Duration(seconds: 10));
      if (_baselineIp != null && now != _baselineIp) {
        throw const FormatException('CISCO_ROUTE_RESTORE_UNVERIFIED');
      }
    } finally {
      _pending = false;
    }
  }
}
