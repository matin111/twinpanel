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

  static const supported = <String>{
    'hysteria2', 'tuic', 'anytls', 'socks5',
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
    final outbound = SingBoxProfileValidator.validateOutbound(
      protocolCode: protocol,
      item: profile,
    );
    await initialize();
    // The plugin builds the local TUN/DNS/routing config; never accept
    // untrusted subscription-provided inbounds, routes or app settings.
    // Do not persist profiles in TwinConnect's own preferences.
    var verifiedLatency = 0;
    try {
      await SingBox.instance.connect(jsonEncode(outbound));
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
    } catch (_) {
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
    await SingBox.instance.disconnect();
    _lastVerifiedLatencyMs = null;
  }
}
