import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'singbox_profile_validator.dart';
import 'windows_singbox_preflight.dart';

/// Transport-only proof using a loopback HTTP CONNECT proxy.
/// This does NOT create a Windows VPN/TUN interface or alter routes.
/// It never claims system-wide connectivity. Credentials remain in memory.
class ModernTransportProbe {
  const ModernTransportProbe();

  static Map<String, dynamic> proxyConfig({
    required String protocol,
    required Map<String, dynamic> profile,
    required int port,
    String? resolvedServer,
  }) {
    if (port < 1024 || port > 65535) {
      throw const FormatException('INVALID_LOCAL_PROXY_PORT');
    }
    final outbound = SingBoxProfileValidator.validateOutbound(
      protocolCode: protocol, item: profile);
    final dialOutbound = <String, dynamic>{...outbound, 'tag': 'proxy'};
    if (resolvedServer != null) {
      final address = InternetAddress.tryParse(resolvedServer);
      if (address == null || address.type != InternetAddressType.IPv4) {
        throw const FormatException('SINGBOX_BOOTSTRAP_IP_INVALID');
      }
      final originalServer = outbound['server'] as String;
      if (InternetAddress.tryParse(originalServer) == null &&
          dialOutbound['tls'] is Map) {
        final tls = Map<String, dynamic>.from(dialOutbound['tls'] as Map);
        if (tls['server_name'] == null || tls['server_name'] == '') {
          tls['server_name'] = originalServer;
        }
        dialOutbound['tls'] = tls;
      }
      dialOutbound['server'] = resolvedServer;
    }
    return {
      'log': {'level': 'error'},
      'inbounds': [{
        'type': 'mixed',
        'tag': 'twinconnect-probe',
        'listen': '127.0.0.1',
        'listen_port': port,
      }],
      'outbounds': [dialOutbound],
      'route': {'final': 'proxy'},
    };
  }

  static Future<ModernProbeResult> verify({
    required String protocol,
    required Map<String, dynamic> profile,
    String? resolvedServer,
  }) async {
    if (!Platform.isWindows || !await WindowsSingBoxPreflight.enginePresent()) {
      throw const FormatException('SINGBOX_ENGINE_UNAVAILABLE');
    }
    // Bind and release a local ephemeral port, then let sing-box acquire it.
    // Never allow remote clients onto this diagnostic proxy.
    final reservation = await ServerSocket.bind(
      InternetAddress.loopbackIPv4, 0);
    final port = reservation.port;
    await reservation.close();
    final config = proxyConfig(
      protocol: protocol, profile: profile, port: port,
      resolvedServer: resolvedServer);
    if (!await WindowsSingBoxPreflight.checkInMemory(config)) {
      throw const FormatException('SINGBOX_PROXY_CONFIG_REJECTED');
    }
    final executable = WindowsSingBoxPreflight.enginePath(
      Platform.resolvedExecutable);
    Process? engine;
    HttpClient? client;
    try {
      engine = await Process.start(executable, ['run', '-c', 'stdin'],
        runInShell: false).timeout(const Duration(seconds: 8));
      // Never collect or log potentially sensitive engine diagnostic streams.
      unawaited(engine.stdout.drain<void>());
      unawaited(engine.stderr.drain<void>());
      engine.stdin.add(utf8.encode(jsonEncode(config)));
      await engine.stdin.close();
      // A valid HTTP proxy response proves that this outbound was reachable.
      // An HTTP CONNECT from the local probe must go through the proxy.
      client = HttpClient()
        ..connectionTimeout = const Duration(seconds: 3)
        ..findProxy = (uri) => 'PROXY 127.0.0.1:$port';
      final clock = Stopwatch()..start();
      Object? lastError;
      for (var attempt = 0; attempt < 3; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 500));
        try {
          final request = await client.getUrl(
            Uri.https('api.ipify.org', '/', {'format': 'json'}),
          ).timeout(const Duration(seconds: 3));
          request.followRedirects = false;
          final response = await request.close()
              .timeout(const Duration(seconds: 5));
          if (response.statusCode != HttpStatus.ok) {
            throw const FormatException('PROXY_HTTP_RESPONSE_INVALID');
          }
          final body = await utf8.decoder.bind(response)
              .join().timeout(const Duration(seconds: 5));
          if (body.length > 512) {
            throw const FormatException('PROXY_RESPONSE_TOO_LARGE');
          }
          final decoded = jsonDecode(body);
          if (decoded is! Map || decoded['ip'] is! String ||
              InternetAddress.tryParse(decoded['ip'] as String) == null) {
            throw const FormatException('PROXY_PUBLIC_IP_INVALID');
          }
          clock.stop();
          return ModernProbeResult(
            publicIp: decoded['ip'] as String,
            latencyMs: clock.elapsedMilliseconds,
          );
        } catch (error) {
          lastError = error;
        }
      }
      // Do not return raw network or engine failures containing credentials.
      if (lastError is FormatException) {
        throw const FormatException('SINGBOX_TRANSPORT_NOT_VERIFIED');
      }
      throw const FormatException('SINGBOX_TRANSPORT_TIMEOUT');
    } finally {
      client?.close(force: true);
      if (engine != null) {
        engine.kill();
        try {
          await engine.exitCode.timeout(const Duration(seconds: 5));
        } catch (_) {
          // Process termination cannot be assumed successful if it times out.
        }
      }
    }
  }
}

class ModernProbeResult {
  const ModernProbeResult({required this.publicIp, required this.latencyMs});
  final String publicIp;
  final int latencyMs;
}
