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
