import 'dart:io';
import 'package:flutter/services.dart';
import 'trusttunnel_client_profile.dart';

/// TrustTunnel requires a native Rust SOCKS engine AND a TUN-to-SOCKS bridge.
/// The native layer must prove both before credentials are requested.
class AndroidTrustTunnel {
  AndroidTrustTunnel._();
  static final instance = AndroidTrustTunnel._();
  static const _channel = MethodChannel('com.twinpanel.twinconnect/trusttunnel');

  Future<bool> get engineReady async {
    if (!Platform.isAndroid) return false;
    try {
      final state = await _channel.invokeMapMethod<String, dynamic>('getCapabilities');
      return state?['contractVersion'] == 1 &&
          state?['engineReady'] == true &&
          state?['vpnServiceReady'] == true;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  Future<void> connect(Map<String, dynamic> item) async {
    if (!await engineReady) {
      throw const FormatException('TRUSTTUNNEL_NATIVE_ENGINE_UNAVAILABLE');
    }
    final profile = TrustTunnelClientProfile.fromItem(item);
    final endpointIp = await profile.resolveEndpointIPv4();
    final config = profile.privateSocksToml(endpointIp, 34111);
    final result = await _channel.invokeMapMethod<String, dynamic>(
      'connect', {'config': config, 'endpointIpv4': endpointIp},
    );
    if (result?['tunnelVerified'] != true) {
      throw const FormatException('TRUSTTUNNEL_TUNNEL_NOT_VERIFIED');
    }
  }

  Future<void> disconnect() async {
    if (Platform.isAndroid) await _channel.invokeMethod<void>('disconnect');
  }
}
