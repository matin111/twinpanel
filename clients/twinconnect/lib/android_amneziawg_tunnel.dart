import 'dart:io';
import 'package:flutter/services.dart';
import 'amneziawg_profile.dart';

/// Native AmneziaWG transport contract. Do not substitute WireGuard GoBackend:
/// AmneziaWG's obfuscation parameters require its own implementation.
class AndroidAmneziaWgTunnel {
  AndroidAmneziaWgTunnel._();
  static final instance = AndroidAmneziaWgTunnel._();
  static const _channel = MethodChannel('com.twinpanel.twinconnect/amneziawg');

  Future<bool> get engineReady async {
    if (!Platform.isAndroid) return false;
    try {
      final state = await _channel.invokeMapMethod<String, dynamic>('getCapabilities');
      return state?['contractVersion'] == 1 &&
          state?['engineReady'] == true &&
          state?['vpnServiceReady'] == true;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  Future<void> connect(Map<String, dynamic> item) async {
    if (!await engineReady) {
      throw const FormatException('AWG_NATIVE_ENGINE_UNAVAILABLE');
    }
    final profile = AmneziaWgProfile.fromItem(item);
    final response = await _channel.invokeMapMethod<String, dynamic>(
      'connect', {'config': profile.config},
    );
    if (response?['tunnelVerified'] != true) {
      throw const FormatException('AWG_TUNNEL_NOT_VERIFIED');
    }
  }

  Future<Map<String, dynamic>> status() async {
    if (!Platform.isAndroid) return const {'connected': false};
    final result = await _channel.invokeMapMethod<String, dynamic>('status');
    return result ?? const {'connected': false};
  }

  Future<void> disconnect() async {
    if (Platform.isAndroid) await _channel.invokeMethod<void>('disconnect');
  }
}
