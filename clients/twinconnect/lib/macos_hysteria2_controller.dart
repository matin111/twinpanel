import 'dart:io';

import 'package:flutter/services.dart';

import 'singbox_macos_config.dart';

/// Hysteria2 macOS host control. The native extension must be provisioned,
/// signed, and enabled before this controller sends any sensitive profile.
class MacHysteria2Controller {
  const MacHysteria2Controller();

  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  Future<Map<String, dynamic>> installation() async {
    if (!Platform.isMacOS) {
      return const <String, dynamic>{
        'contractVersion': 1,
        'engineReady': false,
        'reason': 'MACOS_REQUIRED',
      };
    }
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'macOSHysteria2EngineStatus',
    ).timeout(const Duration(seconds: 8));
    if (result == null ||
        result['contractVersion'] != 1 ||
        result['protocol'] != 'hysteria2' ||
        result['engineReady'] is! bool) {
      throw const FormatException('MACOS_HYSTERIA2_STATUS_INVALID');
    }
    return Map.unmodifiable(result);
  }

  /// Apple OS status only. Even when the OS says connected, this is NOT
  /// evidence of a Hysteria2 handshake, traffic egress or DNS protection.
  Future<Map<String, dynamic>> status() async {
    if (!Platform.isMacOS) {
      return const <String, dynamic>{
        'contractVersion': 1,
        'protocol': 'hysteria2',
        'state': 'unavailable',
        'osConnected': false,
        'verified': false,
        'peerHandshakeVerified': false,
      };
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'getHysteria2TunnelStatus',
    ).timeout(const Duration(seconds: 8));
    const states = <String>{
      'not_configured', 'status_unavailable', 'connecting',
      'os_connected_unverified', 'reasserting', 'disconnecting',
      'disconnected', 'invalid', 'unknown',
    };
    if (raw == null ||
        raw['contractVersion'] != 1 ||
        raw['protocol'] != 'hysteria2' ||
        !states.contains(raw['state']) ||
        raw['osConnected'] is! bool ||
        raw['verified'] != false ||
        raw['peerHandshakeVerified'] != false ||
        (raw['osConnected'] == true &&
            raw['state'] != 'os_connected_unverified')) {
      throw const FormatException('MACOS_HYSTERIA2_OS_STATUS_INVALID');
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
      throw const FormatException('MACOS_HYSTERIA2_TENANT_INVALID');
    }
    final status = await installation();
    if (status['engineReady'] != true ||
        status['packetFlowBridgeReady'] != true ||
        status['inProcessLibboxBundled'] != true) {
      throw const FormatException(
          'MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING');
    }
    final config = SingBoxMacConfig.encodeForEphemeralTunnel(item: profile);
    final output = await _channel.invokeMapMethod<String, dynamic>(
      'startHysteria2',
      <String, dynamic>{
        'protocol': 'hysteria2',
        'config': config,
        'namespace': namespace,
        'account': account,
      },
    ).timeout(const Duration(seconds: 35));
    if (output == null ||
        output['contractVersion'] != 1 ||
        output['protocol'] != 'hysteria2' ||
        output['state'] != 'connecting' ||
        output['peerHandshakeVerified'] != false) {
      throw const FormatException('MACOS_HYSTERIA2_START_INVALID');
    }
    return Map.unmodifiable(output);
  }
}
