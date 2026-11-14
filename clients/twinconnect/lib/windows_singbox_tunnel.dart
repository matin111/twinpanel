import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/services.dart';

import 'singbox_windows_config.dart';
import 'windows_app_route_engine.dart';
import 'xray_endpoint_route.dart';
import 'singbox_profile_validator.dart';
import 'shadowtls_chain.dart';
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
  int? _telemetryPort;
  String? _telemetrySecret;
  bool _changing = false;

  bool get isRunning => _child != null && _exitIp != null;
  String? get protocol => isRunning ? _activeProtocol : null;
  String? get serverId => isRunning ? _activeServerId : null;
  String? get publicIp => isRunning ? _exitIp : null;

  /// Read actual sing-box byte totals without exposing the local API on LAN.
  /// The authenticated loopback API is active only for the owned TUN process.
  Future<({int received, int sent})?> readTrafficTotals() async {
    final port = _telemetryPort;
    final secret = _telemetrySecret;
    if (!isRunning || port == null || secret == null) return null;
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 2)
      ..findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(
        Uri.parse('http://127.0.0.1:$port/connections'),
      ).timeout(const Duration(seconds: 3));
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $secret');
      final response = await request.close().timeout(const Duration(seconds: 3));
      if (response.statusCode != HttpStatus.ok) return null;
      final bytes = <int>[];
      await for (final chunk in response.timeout(const Duration(seconds: 3))) {
        if (bytes.length + chunk.length > 262144) return null;
        bytes.addAll(chunk);
      }
      final parsed = jsonDecode(utf8.decode(bytes));
      if (parsed is! Map) return null;
      final rx = parsed['downloadTotal'];
      final tx = parsed['uploadTotal'];
      if (rx is! int || tx is! int || rx < 0 || tx < 0) return null;
      if (!isRunning || _telemetryPort != port || _telemetrySecret != secret) {
        return null;
      }
      return (received: rx, sent: tx);
    } catch (_) {
      return null;
    } finally {
      client.close(force: true);
    }
  }

  /// Read-only route health check. Never starts, stops or reroutes a tunnel.
  /// A transient failure returns false; the caller decides whether to warn.
  Future<bool> checkHealth() async {
    final expected = _exitIp;
    if (!isRunning || expected == null) return false;
    try {
      final actual = await _requestPublicIp()
          .timeout(const Duration(seconds: 7));
      // An explicit different exit is never accepted as healthy.
      return isRunning && actual == expected;
    } catch (_) {
      // A single IPv4 echo domain can fail while the TUN remains healthy.
      // Confirm the SAME verified exit through an independent endpoint,
      // never silently treat network errors as successful VPN traffic.
      try {
        final alternate = await _requestAlternativePublicIp()
            .timeout(const Duration(seconds: 6));
        return isRunning && alternate == expected;
      } catch (_) {
        return false;
      }
    }
  }

  static Future<String> _requestAlternativePublicIp() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 3)
      ..findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(
        Uri.https('ipv4.icanhazip.com', '/'))
        .timeout(const Duration(seconds: 4));
      request.followRedirects = false;
      final response = await request.close()
          .timeout(const Duration(seconds: 4));
      if (response.statusCode != HttpStatus.ok) {
        throw const FormatException('PUBLIC_IP_CHECK_FAILED');
      }
      final body = await utf8.decoder.bind(response).join()
          .timeout(const Duration(seconds: 4));
      if (body.length > 64) {
        throw const FormatException('PUBLIC_IP_RESPONSE_TOO_LARGE');
      }
      final ip = body.trim();
      final address = InternetAddress.tryParse(ip);
      if (address == null || address.type != InternetAddressType.IPv4 ||
          address.isLoopback || address.isLinkLocal ||
          address.isMulticast) {
        throw const FormatException('PUBLIC_IP_RESPONSE_INVALID');
      }
      return ip;
    } finally {
      client.close(force: true);
    }
  }

  // Optional pre-TUN baseline is measured by this same helper while
  // Xray independently verifies its upstream. It is never cached across
  // connections or reused after the system's routes change.
  static Future<String> measureBaselineIp() => _requestPublicIp();

  Future<String> start({
    required String protocol,
    required String serverId,
    required Map<String, dynamic> profile,
    int? xraySocksPort,
    String? xrayVerifiedExitIp,
    String? xrayEndpointIPv4,
    int? sudokuSocksPort,
    String? sudokuVerifiedExitIp,
    String? sudokuEndpointIPv4,
    int? mieruSocksPort,
    String? mieruVerifiedExitIp,
    String? mieruEndpointIPv4,
    int? trusttunnelSocksPort,
    String? trusttunnelVerifiedExitIp,
    String? trusttunnelEndpointIPv4,
    String? baselinePublicIp,
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
      // An independently verified native core (Xray or Sudoku) must keep
      // its upstream TCP dial on the physical network after TUN auto_route.
      if ([xraySocksPort, sudokuSocksPort, mieruSocksPort, trusttunnelSocksPort]
          .where((port) => port != null).length > 1) {
        throw const FormatException('MULTIPLE_LOCAL_PROXY_UPSTREAMS');
      }
      if ((sudokuSocksPort == null) != (sudokuEndpointIPv4 == null) ||
          (sudokuSocksPort == null) != (sudokuVerifiedExitIp == null)) {
        throw const FormatException('SUDOKU_BRIDGE_NOT_VERIFIED');
      }
      if (sudokuSocksPort != null &&
          (protocol != 'sudoku' || sudokuSocksPort < 1024 ||
           sudokuSocksPort > 65535 ||
           InternetAddress.tryParse(sudokuVerifiedExitIp!)?.type !=
               InternetAddressType.IPv4)) {
        throw const FormatException('SUDOKU_BRIDGE_NOT_VERIFIED');
      }
      if (sudokuEndpointIPv4 != null) {
        XrayEndpointRoute.requirePublicIPv4(sudokuEndpointIPv4);
      }
      if ((mieruSocksPort == null) != (mieruEndpointIPv4 == null) ||
          (mieruSocksPort == null) != (mieruVerifiedExitIp == null) ||
          (mieruSocksPort != null &&
            (protocol != 'mieru' || mieruSocksPort < 1024 ||
             mieruSocksPort > 65535 ||
             InternetAddress.tryParse(mieruVerifiedExitIp!)?.type !=
                 InternetAddressType.IPv4))) {
        throw const FormatException('MIERU_BRIDGE_NOT_VERIFIED');
      }
      if (mieruEndpointIPv4 != null) {
        XrayEndpointRoute.requirePublicIPv4(mieruEndpointIPv4);
      }
      if ((trusttunnelSocksPort == null) != (trusttunnelEndpointIPv4 == null) ||
          (trusttunnelSocksPort == null) != (trusttunnelVerifiedExitIp == null) ||
          (trusttunnelSocksPort != null &&
            (protocol != 'trusttunnel' || trusttunnelSocksPort < 1025 ||
             trusttunnelSocksPort > 65535 ||
             InternetAddress.tryParse(trusttunnelVerifiedExitIp!)?.type !=
                 InternetAddressType.IPv4))) {
        throw const FormatException('TRUSTTUNNEL_BRIDGE_NOT_VERIFIED');
      }
      if (trusttunnelEndpointIPv4 != null) {
        XrayEndpointRoute.requirePublicIPv4(trusttunnelEndpointIPv4);
      }
      final activeSocksPort = xraySocksPort ?? sudokuSocksPort ??
          mieruSocksPort ?? trusttunnelSocksPort;
      final activeVerifiedExit =
          xrayVerifiedExitIp ?? sudokuVerifiedExitIp ??
          mieruVerifiedExitIp ?? trusttunnelVerifiedExitIp;
      // Only that server IP can be exempted from TUN routes, preventing loopback.
      if ((xraySocksPort == null) != (xrayEndpointIPv4 == null)) {
        throw const FormatException('XRAY_ENDPOINT_ROUTE_MISSING');
      }
      if (xrayEndpointIPv4 != null) {
        XrayEndpointRoute.requirePublicIPv4(xrayEndpointIPv4);
      }
      if ((xraySocksPort == null) != (xrayVerifiedExitIp == null) ||
          (xraySocksPort != null &&
           (protocol != 'v2ray' || xraySocksPort < 1024 ||
            xraySocksPort > 65535 ||
            InternetAddress.tryParse(xrayVerifiedExitIp!) == null))) {
        throw const FormatException('XRAY_PROXY_NOT_VERIFIED');
      }
      final shadowChain = activeSocksPort == null && protocol == 'shadowtls'
          ? ShadowTlsChain.fromItem(profile) : null;
      final outbound = activeSocksPort == null
          ? shadowChain == null
              ? SingBoxProfileValidator.validateOutbound(
                  protocolCode: protocol, item: profile)
              : shadowChain.transport
          : <String, dynamic>{'server': '127.0.0.1'};
      final endpoint = outbound['server'] as String;
      String? resolvedServer;
      if (InternetAddress.tryParse(endpoint) == null) {
        try {
          final addresses = await InternetAddress.lookup(
            endpoint, type: InternetAddressType.IPv4,
          ).timeout(const Duration(seconds: 8));
          if (addresses.isEmpty) {
            throw const FormatException('SINGBOX_ENDPOINT_DNS_UNAVAILABLE');
          }
          // A poisoned local DNS answer (for example 10.x.x.x for a
          // public VPN hostname) must never be treated as the VPN server.
          final candidate = addresses.first;
          final bytes = candidate.rawAddress;
          final privateAddress = bytes.length == 4 &&
              (bytes[0] == 10 ||
               (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31) ||
               (bytes[0] == 192 && bytes[1] == 168) ||
               bytes[0] == 127 || bytes[0] == 0 ||
               (bytes[0] == 169 && bytes[1] == 254));
          if (privateAddress) {
            throw const FormatException('SINGBOX_ENDPOINT_DNS_POISONED');
          }
          resolvedServer = candidate.address;
        } on FormatException catch (error) {
          if (error.message == 'SINGBOX_ENDPOINT_DNS_POISONED') rethrow;
          throw const FormatException('SINGBOX_ENDPOINT_DNS_UNAVAILABLE');
        } catch (_) {
          throw const FormatException('SINGBOX_ENDPOINT_DNS_UNAVAILABLE');
        }
      }
      // Reserve a free localhost-only port and a non-guessable API secret.
      final reservation = await ServerSocket.bind(
        InternetAddress.loopbackIPv4, 0);
      final telemetryPort = reservation.port;
      await reservation.close();
      final random = Random.secure();
      final telemetrySecret = List<int>.generate(32, (_) => random.nextInt(256))
          .map((value) => value.toRadixString(16).padLeft(2, '0')).join();
      final config = SingBoxWindowsConfig.compose(
        protocol: protocol, item: profile, resolvedServer: resolvedServer,
        telemetryPort: telemetryPort, telemetrySecret: telemetrySecret,
        xraySocksPort: xraySocksPort,
        xrayEndpointIPv4: xrayEndpointIPv4,
        sudokuSocksPort: sudokuSocksPort,
        sudokuEndpointIPv4: sudokuEndpointIPv4,
        mieruSocksPort: mieruSocksPort,
        mieruEndpointIPv4: mieruEndpointIPv4,
        trusttunnelSocksPort: trusttunnelSocksPort,
        trusttunnelEndpointIPv4: trusttunnelEndpointIPv4);
      // Separate app-routing engine. Apply the selected policy to the actual
      // in-memory native sing-box configuration for this VPN session.
      final routingPolicy = await WindowsAppRoutePolicy.load();
      routingPolicy.applyTo(config);
      // Independently verify that the selected Hysteria2/TUIC/etc outbound
      // can reach the internet before changing any Windows routes.
      // A failure here points to profile/transport rather than TUN routing.
      // Both checks are read-only and independent. Run concurrently so
      // connection setup does not wait for their latencies sequentially.
      final Future<String> proxyCheck = activeSocksPort == null
          ? ModernTransportProbe.verify(
              protocol: protocol, profile: profile,
              resolvedServer: resolvedServer,
            ).then((result) => result.publicIp).catchError((Object _) {
              throw const FormatException('SINGBOX_SERVER_TRANSPORT_UNREACHABLE');
            })
          : Future<String>.value(activeVerifiedExit!);
      if (baselinePublicIp != null &&
          (InternetAddress.tryParse(baselinePublicIp)?.type !=
              InternetAddressType.IPv4)) {
        throw const FormatException('BASELINE_IP_UNAVAILABLE');
      }
      final Future<String> baselineCheck = baselinePublicIp != null
          ? Future<String>.value(baselinePublicIp)
          : _requestPublicIp().timeout(
              const Duration(seconds: 10),
              onTimeout: () =>
                  throw const FormatException('BASELINE_IP_UNAVAILABLE'),
            );
      // All three pre-TUN checks are independent. Overlap CPU-only config
      // validation with the two read-only HTTPS checks. The engine MUST
      // pass all of them BEFORE its route-changing process is started.
      final preTunnelChecks = await Future.wait<Object>([
        WindowsSingBoxPreflight.checkInMemory(config),
        proxyCheck,
        baselineCheck,
      ]);
      if (preTunnelChecks[0] != true) {
        throw const FormatException('SINGBOX_TUN_CONFIG_INVALID');
      }
      final verifiedProxyIp = preTunnelChecks[1] as String;
      final before = preTunnelChecks[2] as String;

      started = await Process.start(
        WindowsSingBoxPreflight.enginePath(Platform.resolvedExecutable),
        const ['run', '-c', 'stdin'], runInShell: false,
      ).timeout(const Duration(seconds: 8));
      _child = started;
      _telemetryPort = telemetryPort;
      _telemetrySecret = telemetrySecret;
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
      // Keep only a coarse diagnostic classification in memory, never the
      // potentially credential-bearing text of an engine error.
      String? nativeFailure;
      unawaited(utf8.decoder.bind(current.stderr)
          .transform(const LineSplitter()).forEach((line) {
        final safe = line.toLowerCase();
        if (safe.contains('wintun') || safe.contains('driver')) {
          nativeFailure = 'SINGBOX_TUN_DRIVER_ERROR';
        } else if (safe.contains('access is denied') ||
            safe.contains('permission denied') ||
            safe.contains('administrator')) {
          nativeFailure = 'SINGBOX_TUN_PERMISSION_DENIED';
        } else if (safe.contains('route') && safe.contains('fail')) {
          nativeFailure = 'SINGBOX_TUN_ROUTE_INSTALL_FAILED';
        } else if (safe.contains('create tun') ||
            safe.contains('start tun')) {
          nativeFailure = 'SINGBOX_TUN_ADAPTER_START_FAILED';
        }
      }));
      current.stdin.add(utf8.encode(jsonEncode(config)));
      await current.stdin.close();
      var exited = false;
      unawaited(current.exitCode.then((_) {
        exited = true;
        if (identical(_child, current) && !_changing) {
          _child = null;
          _telemetryPort = null;
          _telemetrySecret = null;
          _activeServerId = null;
          _activeProtocol = null;
          _exitIp = null;
          onUnexpectedExit?.call();
        }
      }));
      // The optional PowerShell inspector is not authoritative and may fail
      // on locked-down Windows hosts. Never block a real traffic probe solely
      // because Get-NetRoute / Get-NetAdapter cannot be invoked.
      //
      // The IP comparison below remains fail-closed. If no traffic actually
      // traverses the selected outbound, connection cannot be confirmed.
      // Native engine failures are still checked while testing traffic.
      // Do not spawn slow PowerShell diagnostics in the connection path;
      // inspectWindowsTunRoutes remains available for explicit diagnostics.

      // Observe the actual Windows interface and default route directly
      // before judging egress. No PowerShell or guessed error-string mapping.
      // Poll briefly because auto_route is installed after TUN startup.
      String? tunState;
      for (var readiness = 0; readiness < 5; readiness++) {
        if (exited) {
          throw FormatException(nativeFailure ?? 'SINGBOX_PROCESS_EXITED');
        }
        tunState = await inspectNativeTunRoutes();
        if (tunState == null ||
            tunState == 'SINGBOX_TUN_NATIVE_INSPECTION_FAILED') {
          break;
        }
        await Future<void>.delayed(const Duration(milliseconds: 500));
      }
      // An unavailable native inspector does not prove a connection failed.
      // Real HTTP traffic verification remains mandatory below.
      if (tunState != null &&
          tunState != 'SINGBOX_TUN_NATIVE_INSPECTION_FAILED') {
        throw FormatException(nativeFailure ?? tunState);
      }
      String? verified;
      var postTunnelHttpSucceeded = false;
      // A bounded total readiness budget prevents 40 independent HTTP
      // timeouts from turning one failed connection into minutes of waiting.
      // A verified HTTPS exit is still required; a timeout never means online.
      final routeDeadline = Stopwatch()..start();
      for (var attempt = 0;
          attempt < 40 &&
          routeDeadline.elapsed < const Duration(seconds: 14);
          attempt++) {
        if (attempt > 0) {
          await Future<void>.delayed(Duration(milliseconds:
              attempt < 5 ? 150 : 400));
        }
        if (exited) {
          throw FormatException(nativeFailure ?? 'SINGBOX_PROCESS_EXITED');
        }
        try {
          // Do not use the same HTTPS service for every probe: a single
          // blocked IP-echo domain must not be confused with TUN failure.
          // Always use the SAME IPv4 echo endpoint used for the baseline
          // and for the independent sing-box proxy probe.
          final ip = await _requestPublicIp()
              .timeout(const Duration(seconds: 3));
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
      _telemetryPort = null;
      _telemetrySecret = null;
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
      _telemetryPort = null;
      _telemetrySecret = null;
      _child = null;
      _activeServerId = null;
      _activeProtocol = null;
      _exitIp = null;
    }
  }

  /// Native Windows IP Helper inspection: no PowerShell startup, no
  /// dependency on shell policy, and no modification of adapter/routes.
  static Future<String?> inspectNativeTunRoutes() async {
    if (!Platform.isWindows) return 'SINGBOX_WINDOWS_ONLY';
    try {
      final state = await _native.invokeMapMethod<String, dynamic>(
        'inspectSingBoxTun',
      ).timeout(const Duration(seconds: 3));
      if (state == null || state['inspectionOk'] != true) {
        return 'SINGBOX_TUN_NATIVE_INSPECTION_FAILED';
      }
      if (state['adapterPresent'] != true) {
        return 'SINGBOX_TUN_ADAPTER_MISSING';
      }
      if (state['adapterUp'] != true) {
        return 'SINGBOX_TUN_ADAPTER_DOWN';
      }
      if (state['defaultRoutePresent'] != true) {
        return 'SINGBOX_TUN_DEFAULT_ROUTE_MISSING';
      }
      if (state['bestRouteKnown'] == true && state['tunPreferred'] != true) {
        return 'SINGBOX_TUN_NOT_PREFERRED';
      }
      return null;
    } catch (_) {
      return 'SINGBOX_TUN_NATIVE_INSPECTION_FAILED';
    }
  }

  /// Read-only Windows inspection. Never modifies routes or adapters.
  /// Route presence alone is not a proof of an operating VPN.
  static Future<String?> inspectWindowsTunRoutes() async {
    // PowerShell's NetTCPIP module can take more than six seconds to load
    // on Windows 10/11 and cold CI runners. Use a bounded 45-second
    // budget; don't interpret command timeout as a missing default route.
    const command = r'''
$ErrorActionPreference = 'Stop'
try {
  $adapter = Get-NetAdapter -Name 'TwinConnectSB' -ErrorAction SilentlyContinue
  if ($null -eq $adapter) {
    [pscustomobject]@{ state='adapter_missing'; routes=0 } |
      ConvertTo-Json -Compress
    exit 0
  }
  $routes = @(Get-NetRoute -AddressFamily IPv4 -InterfaceIndex $adapter.ifIndex -ErrorAction Stop |
    Where-Object {
      $_.DestinationPrefix -eq '0.0.0.0/0' -or
      $_.DestinationPrefix -eq '0.0.0.0/1' -or
      $_.DestinationPrefix -eq '128.0.0.0/1'
    })
  [pscustomobject]@{ state='inspected'; routes=$routes.Count } |
    ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ state='inspection_error'; routes=0 } |
    ConvertTo-Json -Compress
}
''';
    try {
      final result = await Process.run(
        'powershell.exe',
        ['-NoLogo', '-NoProfile', '-NonInteractive', '-Command', command],
        runInShell: false,
      ).timeout(const Duration(seconds: 45));
      if (result.exitCode != 0) {
        return 'SINGBOX_TUN_ROUTE_INSPECTION_FAILED';
      }
      final raw = result.stdout.toString().trim();
      final data = jsonDecode(raw);
      if (data is! Map) return 'SINGBOX_TUN_ROUTE_INSPECTION_FAILED';
      if (data['state'] == 'adapter_missing') {
        return 'SINGBOX_TUN_ADAPTER_MISSING';
      }
      if (data['state'] != 'inspected') {
        return 'SINGBOX_TUN_ROUTE_INSPECTION_FAILED';
      }
      final routeCount = data['routes'];
      if (routeCount is! num || routeCount < 1) {
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
