import 'dart:io';

import 'package:flutter/services.dart';

/// Host-side control of an Apple signed macOS PacketTunnel extension.
/// OS acceptance of startTunnel is NOT a verified WireGuard handshake.
class MacWireGuardController {
  const MacWireGuardController();
  static const _channel = MethodChannel('com.twinpanel.twinconnect/vpn');

  Future<Map<String, dynamic>> runtime() async {
    if (!Platform.isMacOS) {
      return const {'contractVersion': 1, 'engineReady': false,
        'reason': 'MACOS_REQUIRED'};
    }
    final response = await _channel.invokeMapMethod<String, dynamic>(
      'macOSRuntimeStatus',
    ).timeout(const Duration(seconds: 8));
    if (response == null || response['contractVersion'] != 1) {
      throw const FormatException('MACOS_RUNTIME_STATUS_INVALID');
    }
    return Map.unmodifiable(response);
  }

  Future<Map<String, dynamic>> start({
    required String profile,
    required String namespace,
    required String account,
  }) async {
    if (!Platform.isMacOS) throw const FormatException('MACOS_REQUIRED');
    if (profile.length < 65 || profile.length > 65536 ||
        !profile.contains('[Interface]') || !profile.contains('[Peer]')) {
      throw const FormatException('MACOS_WIREGUARD_PROFILE_INVALID');
    }
    if (namespace.length < 3 || namespace.length > 128 ||
        account.isEmpty || account.length > 255) {
      throw const FormatException('MACOS_TENANT_SCOPE_INVALID');
    }

    // Native host repeats the backend and profile checks independently.
    final status = await runtime();
    if (status['engineReady'] != true) {
      throw const FormatException('MACOS_WIREGUARD_BACKEND_NOT_LINKED');
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'startTunnel', <String, dynamic>{
        'protocol': 'wireguard',
        'config': profile,
        'namespace': namespace,
        'account': account,
      },
    ).timeout(const Duration(seconds: 30));
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['protocol'] != 'wireguard' || raw['state'] != 'connecting' ||
        raw['peerHandshakeVerified'] != false) {
      throw const FormatException('MACOS_NATIVE_START_RESPONSE_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<Map<String, dynamic>> status() async {
    if (!Platform.isMacOS) return const {'state': 'unavailable'};
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'getTunnelStatus',
    ).timeout(const Duration(seconds: 8));
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['state'] is! String || raw['verified'] is! bool) {
      throw const FormatException('MACOS_NATIVE_STATUS_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<void> stop() async {
    if (!Platform.isMacOS) throw const FormatException('MACOS_REQUIRED');
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'stopTunnel',
    ).timeout(const Duration(seconds: 12));
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['state'] is! String) {
      throw const FormatException('MACOS_NATIVE_STOP_RESPONSE_INVALID');
    }
  }
}
