import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'singbox_windows_config.dart';
import 'modern_transport_probe.dart';
import 'windows_singbox_preflight.dart';

/// Owns a single sing-box Windows TUN child process.
/// The process is launched only after the user's authorized native profile
/// passes engine syntax validation. No credentials are written to disk or logs.
///
/// Important: this is an application-lifetime TUN controller, not a Windows
/// service or a guaranteed kill switch. A separate native Job Object/recovery
/// helper is needed before advertising crash-safe always-on protection.
class WindowsSingBoxTunnel {
  static const MethodChannel _native =
      MethodChannel('com.twinpanel.twinconnect/vpn');
  WindowsSingBoxTunnel({this.onUnexpectedExit});
  final void Function()? onUnexpectedExit;
  Process? _child;
  String? _activeProtocol;
  String? _activeServerId;
  String? _exitIp;
  bool _changing = false;

  bool get isRunning => _child != null && _exitIp != null;
  String? get protocol => isRunning ? _activeProtocol : null;
  String? get serverId => isRunning ? _activeServerId : null;
  String? get publicIp => isRunning ? _exitIp : null;

  Future<String> start({
    required String protocol,
    required String serverId,
    required Map<String, dynamic> profile,
  }) async {
    if (_changing || _child != null) {
      throw const FormatException('SINGBOX_TUNNEL_ALREADY_RUNNING');
    }
    if (!Platform.isWindows) {
      throw const FormatException('SINGBOX_WINDOWS_ONLY');
    }
    _changing = true;
    Process? started;
    try {
      if (!await WindowsSingBoxPreflight.enginePresent()) {
        throw const FormatException('SINGBOX_ENGINE_NOT_INSTALLED');
      }
      final config = SingBoxWindowsConfig.compose(
        protocol: protocol, item: profile);
      if (!await WindowsSingBoxPreflight.checkInMemory(config)) {
        throw const FormatException('SINGBOX_TUN_CONFIG_INVALID');
      }
      // Independently verify that the selected Hysteria2/TUIC/etc outbound
      // can reach the internet before changing any Windows routes.
      // A failure here points to profile/transport rather than TUN routing.
      String verifiedProxyIp;
      try {
        verifiedProxyIp = (await ModernTransportProbe.verify(
          protocol: protocol, profile: profile)).publicIp;
      } catch (_) {
        throw const FormatException('SINGBOX_SERVER_TRANSPORT_UNREACHABLE');
      }
      final before = await _requestPublicIp().timeout(
        const Duration(seconds: 10),
        onTimeout: () => throw const FormatException('BASELINE_IP_UNAVAILABLE'),
      );

      started = await Process.start(
        WindowsSingBoxPreflight.enginePath(Platform.resolvedExecutable),
        const ['run', '-c', 'stdin'], runInShell: false,
      ).timeout(const Duration(seconds: 8));
      _child = started;
      final current = started;
      // Attach to JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE before supplying the
      // credential-bearing config or allowing any Windows route changes.
      // If the guard isn't available this connection MUST fail closed.
      final guarded = await _native.invokeMethod<bool>(
        'guardSingBoxProcess', {'pid': current.pid},
      ).timeout(const Duration(seconds: 6));
      if (guarded != true) {
        throw const FormatException('SINGBOX_PROCESS_GUARD_UNAVAILABLE');
      }
      // Ensure pipes can never block the child. They are not logged because
      // native client diagnostics might contain account secrets.
      unawaited(current.stdout.drain<void>());
      unawaited(current.stderr.drain<void>());
      current.stdin.add(utf8.encode(jsonEncode(config)));
      await current.stdin.close();
      var exited = false;
      unawaited(current.exitCode.then((_) {
        exited = true;
        if (identical(_child, current) && !_changing) {
          _child = null;
          _activeServerId = null;
          _activeProtocol = null;
          _exitIp = null;
          onUnexpectedExit?.call();
        }
      }));
      // Verify Windows actually created the TUN adapter and a default
      // route; an alive sing-box process does not imply a working TUN.
      String? routeIssue;
      for (var attempt = 0; attempt < 5; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 450));
        if (exited) throw const FormatException('SINGBOX_PROCESS_EXITED');
        routeIssue = await _windowsTunRouteIssue();
        if (routeIssue == null) break;
      }
      if (routeIssue != null) throw FormatException(routeIssue);
      String? verified;
      var postTunnelHttpSucceeded = false;
      for (var attempt = 0; attempt < 8; attempt++) {
        await Future<void>.delayed(const Duration(seconds: 2));
        if (exited) {
          throw const FormatException('SINGBOX_PROCESS_EXITED');
        }
        try {
          // Do not use the same HTTPS service for every probe: a single
          // blocked IP-echo domain must not be confused with TUN failure.
          // Always use the SAME IPv4 echo endpoint used for the baseline
          // and for the independent sing-box proxy probe.
          final ip = await _requestPublicIp()
              .timeout(const Duration(seconds: 6));
          final observed = InternetAddress.tryParse(ip);
          final baseline = InternetAddress.tryParse(before);
          if (observed == null || baseline == null ||
              observed.type != baseline.type) {
            // IPv4/IPv6 differences are not proof of a VPN route change.
            continue;
          }
          postTunnelHttpSucceeded = true;
          if (ip != before && ip == verifiedProxyIp) {
            // Require the actual Windows route to agree with the SAME
            // outbound's separately verified exit, not just any IP change.
            verified = ip;
            break;
          }
        } catch (_) {
          // No successful HTTP response is not evidence of a working TUN.
        }
      }
      if (verified == null) {
        throw FormatException(postTunnelHttpSucceeded
          ? 'SINGBOX_TUN_ROUTE_NOT_VERIFIED'
          : 'SINGBOX_TUN_INTERNET_UNREACHABLE');
      }
      if (exited || !identical(_child, current)) {
        throw const FormatException('SINGBOX_PROCESS_EXITED');
      }
      _activeServerId = serverId;
      _activeProtocol = protocol;
      _exitIp = verified;
      return verified;
    } catch (_) {
      await _killChild();
      rethrow;
    } finally {
      _changing = false;
    }
  }

  Future<void> stop() async {
    if (_changing) throw const FormatException('SINGBOX_TUNNEL_BUSY');
    _changing = true;
    try {
      await _killChild();
    } finally {
      _changing = false;
    }
  }

  Future<void> _killChild() async {
    final child = _child;
    if (child == null) {
      _activeServerId = null;
      _activeProtocol = null;
      _exitIp = null;
      return;
    }
    // Do not claim stopped before Windows confirms child termination.
    child.kill();
    try {
      await child.exitCode.timeout(const Duration(seconds: 8));
    } on TimeoutException {
      throw const FormatException('SINGBOX_PROCESS_DID_NOT_STOP');
    }
    if (identical(child, _child)) {
      _child = null;
      _activeServerId = null;
      _activeProtocol = null;
      _exitIp = null;
    }
  }

  /// Read-only Windows inspection. Never modifies routes or adapters.
  /// Route presence alone is not a proof of an operating VPN.
  static Future<String?> _windowsTunRouteIssue() async {
    const command = r'''$a=Get-NetAdapter -Name 'TwinConnectSB' -ErrorAction SilentlyContinue; $r=@(Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.InterfaceAlias -eq 'TwinConnectSB' -and $_.DestinationPrefix -in @('0.0.0.0/0','0.0.0.0/1','128.0.0.0/1') }); [pscustomobject]@{adapter=[bool]$a; routes=$r.Count} | ConvertTo-Json -Compress''';
    try {
      final result = await Process.run('powershell.exe',
        ['-NoProfile', '-NonInteractive', '-Command', command],
        runInShell: false).timeout(const Duration(seconds: 6));
      if (result.exitCode != 0) return 'SINGBOX_TUN_ROUTE_INSPECTION_FAILED';
      final data = jsonDecode(result.stdout.toString());
      if (data is! Map) return 'SINGBOX_TUN_ROUTE_INSPECTION_FAILED';
      if (data['adapter'] != true) return 'SINGBOX_TUN_ADAPTER_MISSING';
      if (data['routes'] is! num || (data['routes'] as num) < 1) {
        return 'SINGBOX_TUN_DEFAULT_ROUTE_MISSING';
      }
      return null;
    } catch (_) {
      return 'SINGBOX_TUN_ROUTE_INSPECTION_FAILED';
    }
  }

  /// Direct HTTPS request using the current Windows network routes.
  /// A different IP than the pre-TUN baseline is necessary (not sufficient)
  /// to prove that traffic left through the selected outbound.
  static Future<String> _requestPublicIp() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 3)
      ..findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(
        Uri.https('api.ipify.org', '/', {'format': 'json'}));
      request.followRedirects = false;
      final response = await request.close().timeout(
        const Duration(seconds: 5));
      if (response.statusCode != HttpStatus.ok) {
        throw const FormatException('PUBLIC_IP_CHECK_FAILED');
      }
      final body = await utf8.decoder.bind(response).join()
          .timeout(const Duration(seconds: 5));
      if (body.length > 512) {
        throw const FormatException('PUBLIC_IP_RESPONSE_TOO_LARGE');
      }
      final data = jsonDecode(body);
      if (data is! Map || data['ip'] is! String) {
        throw const FormatException('PUBLIC_IP_RESPONSE_INVALID');
      }
      final ip = data['ip'] as String;
      if (InternetAddress.tryParse(ip) == null) {
        throw const FormatException('PUBLIC_IP_RESPONSE_INVALID');
      }
      return ip;
    } finally {
      client.close(force: true);
    }
  }

  /// Best-effort cleanup on view disposal. Not a crash recovery guarantee.
  void dispose() {
    final child = _child;
    child?.kill();
  }
}
