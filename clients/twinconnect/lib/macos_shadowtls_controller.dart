import 'dart:io';

import 'package:flutter/services.dart';

import 'macos_shadowtls_config.dart';

/// Signed macOS ShadowTLS v3 + Shadowsocks profile handoff.
class MacShadowTlsController {
  const MacShadowTlsController();

  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  Future<Map<String, dynamic>> installation() async {
    if (!Platform.isMacOS) {
      return const {'contractVersion': 1, 'engineReady': false,
        'reason': 'MACOS_REQUIRED'};
    }
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'macOSShadowTlsEngineStatus',
    ).timeout(const Duration(seconds: 8));
    if (result == null || result['contractVersion'] != 1 ||
        result['protocol'] != 'shadowtls' || result['engineReady'] is! bool) {
      throw const FormatException('MACOS_SHADOWTLS_STATUS_INVALID');
    }
    return Map.unmodifiable(result);
  }

  Future<Map<String, dynamic>> status() async {
    if (!Platform.isMacOS) {
      return const {'contractVersion': 1, 'protocol': 'shadowtls',
        'state': 'unavailable', 'osConnected': false,
        'verified': false, 'peerHandshakeVerified': false};
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'getShadowTlsTunnelStatus',
    ).timeout(const Duration(seconds: 8));
    const states = <String>{
      'not_configured', 'status_unavailable', 'connecting',
      'os_connected_unverified', 'reasserting', 'disconnecting',
      'disconnected', 'invalid', 'unknown',
    };
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['protocol'] != 'shadowtls' ||
        !states.contains(raw['state']) ||
        raw['osConnected'] is! bool ||
        raw['verified'] != false ||
        raw['peerHandshakeVerified'] != false ||
        (raw['osConnected'] == true &&
          raw['state'] != 'os_connected_unverified')) {
      throw const FormatException('MACOS_SHADOWTLS_OS_STATUS_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<Map<String, dynamic>> start({
    required Map<String, dynamic> profile,
    required String namespace,
    required String account,
  }) async {
    if (!Platform.isMacOS) {
      throw const FormatException('MACOS_REQUIRED');
    }
    if (namespace.length < 3 || namespace.length > 128 ||
        account.isEmpty || account.length > 255) {
      throw const FormatException('MACOS_SHADOWTLS_TENANT_INVALID');
    }
    final capability = await installation();
    if (capability['engineReady'] != true ||
        capability['packetFlowBridgeReady'] != true ||
        capability['inProcessLibboxBundled'] != true) {
      throw const FormatException(
        'MACOS_SHADOWTLS_PACKET_FLOW_BRIDGE_MISSING');
    }
    final config = MacShadowTlsConfig.encode(item: profile);
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'startShadowTls',
      {'protocol': 'shadowtls', 'config': config,
        'namespace': namespace, 'account': account},
    ).timeout(const Duration(seconds: 35));
    if (result == null || result['contractVersion'] != 1 ||
        result['protocol'] != 'shadowtls' ||
        result['state'] != 'connecting' ||
        result['peerHandshakeVerified'] != false) {
      throw const FormatException('MACOS_SHADOWTLS_START_INVALID');
    }
    return Map.unmodifiable(result);
  }
}
