import 'dart:io';

import 'package:flutter/services.dart';

import 'android_mieru_profile.dart';
import 'mieru_client_profile.dart';

/// Dedicated Android Mieru transport contract.
///
/// Mieru cannot run through WireGuard or sing-box. The Android native
/// service must expose this channel only after its Mieru core and TUN
/// bridge are installed. No credentials are fetched until it proves ready.
class AndroidMieruTunnel {
  AndroidMieruTunnel._();
  static final AndroidMieruTunnel instance = AndroidMieruTunnel._();
  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/mieru');

  Future<bool> get engineReady async {
    if (!Platform.isAndroid) return false;
    try {
      final state = await _channel.invokeMapMethod<String, dynamic>(
        'getCapabilities',
      );
      return state?['engineReady'] == true &&
          state?['vpnServiceReady'] == true &&
          state?['contractVersion'] == 1;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  Future<void> connect(Map<String, dynamic> item) async {
    if (!await engineReady) {
      throw const FormatException('MIERU_NATIVE_ENGINE_UNAVAILABLE');
    }
    final MieruClientProfile profile = AndroidMieruProfile.validate(item);
    final endpoint = await profile.resolveEndpointIpv4();
    final runtime = profile.runtimeConfig(
      socks5Port: 34101,
      rpcPort: 34102,
      httpProxyPort: 34103,
      resolvedEndpointIpv4: endpoint,
    );
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'connect',
      {'config': runtime, 'endpointIpv4': endpoint},
    );
    if (result?['tunnelVerified'] != true) {
      throw const FormatException('MIERU_TUNNEL_NOT_VERIFIED');
    }
  }

  Future<void> disconnect() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<void>('disconnect');
  }
}
