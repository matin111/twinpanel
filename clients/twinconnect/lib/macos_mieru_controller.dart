import 'dart:io';

import 'package:flutter/services.dart';

/// Native Mieru diagnostics for macOS. Bundled executables are not enough
/// to claim that the PacketTunnel owns a functioning protocol engine.
class MacMieruController {
  const MacMieruController();

  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  Future<Map<String, dynamic>> installation() async {
    if (!Platform.isMacOS) {
      return const {
        'contractVersion': 1,
        'protocol': 'mieru',
        'binaryInstalled': false,
        'packetFlowBridgeReady': false,
        'engineReady': false,
        'reason': 'MACOS_REQUIRED',
      };
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'macOSMieruEngineStatus',
    ).timeout(const Duration(seconds: 8));
    if (raw == null ||
        raw['contractVersion'] != 1 ||
        raw['protocol'] != 'mieru' ||
        raw['binaryInstalled'] is! bool ||
        raw['packetFlowBridgeReady'] is! bool ||
        raw['engineReady'] is! bool ||
        raw['reason'] is! String) {
      throw const FormatException('MACOS_MIERU_STATUS_INVALID');
    }
    if (raw['engineReady'] == true && raw['packetFlowBridgeReady'] != true) {
      throw const FormatException('MACOS_MIERU_BACKEND_INCONSISTENT');
    }
    return Map.unmodifiable(raw);
  }
}
