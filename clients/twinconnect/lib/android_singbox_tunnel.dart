import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:sing_box/sing_box.dart';
import 'package:flutter/services.dart';

import 'singbox_profile_validator.dart';

/// Independent Android VpnService engine for the supported sing-box family.
/// This is never routed through WireGuard's native MethodChannel.
/// Only authenticated panel-issued native outbound JSON is accepted.
class AndroidSingBoxTunnel {
  AndroidSingBoxTunnel._();

  static final AndroidSingBoxTunnel instance = AndroidSingBoxTunnel._();
  bool _initialized = false;
  static const MethodChannel _native =
      MethodChannel('com.twinpanel.twinconnect/vpn');
  int? _lastVerifiedLatencyMs;
  int? get verifiedLatencyMs => _lastVerifiedLatencyMs;
  StreamSubscription<SingBoxConnectionStats>? _statsSubscription;
  SingBoxConnectionStats? _latestStats;
  double? get downloadBps => _latestStats?.downloadSpeed.toDouble();
  double? get uploadBps => _latestStats?.uploadSpeed.toDouble();
  int? get receivedBytes => _latestStats?.downloadTotal;
  int? get sentBytes => _latestStats?.uploadTotal;

  static const supported = <String>{
    'hysteria2', 'tuic', 'anytls', 'socks5', 'shadowtls',
  };

  Future<void> initialize() async {
    if (!Platform.isAndroid) {
      throw const FormatException('SINGBOX_ANDROID_ONLY');
    }
    if (_initialized) return;
    await SingBox.instance.initialize(const SingBoxOptions(
      android: SingBoxAndroidOptions(notificationTitle: 'TwinConnect'),
    ));
    _initialized = true;
  }

  Future<void> connect({
    required String protocol,
    required Map<String, dynamic> profile,
  }) async {
    if (!supported.contains(protocol)) {
      throw const FormatException('SINGBOX_PROTOCOL_UNSUPPORTED');
    }
    if (protocol == 'shadowtls') {
      final chain = SingBoxProfileValidator.validateShadowTlsChain(profile);
      await _connectNative(jsonEncode(chain));
      return;
    }
    final outbound = SingBoxProfileValidator.validateOutbound(
      protocolCode: protocol,
      item: profile,
    );
    await _connectNative(jsonEncode(outbound));
  }

  /// The bundled libbox supports VLESS over TCP TLS and WebSocket TLS.
  /// The panel-signed VLESS URI is used exactly as supplied; never transform
  /// XHTTP Reality into a different transport or weaken TLS verification.
  Future<void> connectVlessUri(Uri uri) async {
    if (!Platform.isAndroid || uri.scheme != 'vless' ||
        uri.userInfo.isEmpty || uri.host.isEmpty || !uri.hasPort ||
        uri.port <= 0 || uri.port > 65535) {
      throw const FormatException('XRAY_URI_INVALID');
    }
    final transport = uri.queryParameters['type'];
    final security = uri.queryParameters['security'];
    if (security != 'tls' || (transport != 'tcp' && transport != 'ws')) {
      throw const FormatException('XRAY_ANDROID_TRANSPORT_UNSUPPORTED');
    }
    await _connectNative(uri.toString());
  }

  Future<void> _connectNative(String config) async {
    await initialize();
    // The plugin builds the local TUN/DNS/routing config; never accept
    // untrusted subscription-provided inbounds, routes or app settings.
    // Do not persist profiles in TwinConnect's own preferences.
    var verifiedLatency = 0;
    await _statsSubscription?.cancel();
    _statsSubscription = null;
    _latestStats = null;
    try {
      await SingBox.instance.connect(config);
      if (SingBox.instance.status != SingBoxConnectionStatus.connected) {
        throw const FormatException('SINGBOX_TUNNEL_NOT_VERIFIED');
      }
      // URL test is performed through the selected encrypted outbound.
      final result = await SingBox.instance.pingCurrentServer(
        timeout: const Duration(seconds: 12),
      );
      if (!result.success) {
        throw const FormatException('SINGBOX_OUTBOUND_UNREACHABLE');
      }
      verifiedLatency = result.ping;
      _statsSubscription = SingBox.instance.watchConnectionStats().listen(
        (stats) => _latestStats = stats,
        onError: (Object _) { _latestStats = null; },
      );
    } catch (_) {
      await _statsSubscription?.cancel();
      _statsSubscription = null;
      _latestStats = null;
      try { await SingBox.instance.disconnect(); } catch (_) {}
      rethrow;
    } finally {
      // The plugin writes the last outbound in app-private plaintext files.
      // Purge it even after a failure, not just after a successful handshake.
      bool purged = false;
      try {
        final response = await _native.invokeMapMethod<String, dynamic>(
          'forgetSingBoxEphemeralConfig',
        );
        purged = response?['purged'] == true;
      } catch (_) {}
      if (!purged) {
        try { await SingBox.instance.disconnect(); } catch (_) {}
        throw const FormatException('PROFILE_PURGE_FAILED');
      }
    }
    _lastVerifiedLatencyMs = verifiedLatency;
  }

  bool get isConnected => _initialized &&
      SingBox.instance.status == SingBoxConnectionStatus.connected;

  Future<void> disconnect() async {
    if (!_initialized) return;
    await _statsSubscription?.cancel();
    _statsSubscription = null;
    _latestStats = null;
    await SingBox.instance.disconnect();
    _lastVerifiedLatencyMs = null;
  }
}
