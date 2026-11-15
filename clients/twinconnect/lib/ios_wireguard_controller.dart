import 'dart:io';

import 'package:flutter/services.dart';

import 'native_vpn_bridge.dart';
import 'vpn_policy.dart';
import 'protocols.dart';

/// iOS host-app bridge to a signed NEPacketTunnelProvider.
/// A native "connecting" response only means iOS accepted the start request;
/// it NEVER means a WireGuard handshake or working Internet path.
class IosWireGuardController {
  const IosWireGuardController();

  static const _channel = MethodChannel('com.twinpanel.twinconnect/vpn');

  Future<Map<String, dynamic>> installation() async {
    if (!Platform.isIOS) {
      return const {'contractVersion': 1, 'engineReady': false,
        'reason': 'IOS_REQUIRED'};
    }
    final response = await _channel
        .invokeMapMethod<String, dynamic>('getEngineInstallation')
        .timeout(const Duration(seconds: 8));
    if (response == null || response['contractVersion'] != 1) {
      throw const FormatException('IOS_ENGINE_INSTALLATION_INVALID');
    }
    return Map.unmodifiable(response);
  }

  Future<Map<String, dynamic>> start({
    required String profile,
    required String namespace,
    required String account,
    required VpnPolicy policy,
  }) async {
    if (!Platform.isIOS) throw const FormatException('IOS_REQUIRED');
    if (profile.length < 65 || profile.length > 65536 ||
        !profile.contains('[Interface]') || !profile.contains('[Peer]')) {
      throw const FormatException('IOS_WIREGUARD_PROFILE_INVALID');
    }
    if (namespace.isEmpty || account.isEmpty) {
      throw const FormatException('IOS_TENANT_SCOPE_INVALID');
    }

    // Capability and protocol gates run before a profile is ever forwarded.
    final capabilities = await NativeVpnBridge.probe();
    final native = await NativeVpnBridge.protocolReadiness(
        validatedCapabilities: capabilities);
    final wireguard = VpnProtocols.byCode('wireguard')!;
    NativeVpnBridge.requireProtocolSafeToConnect(
        policy, capabilities, wireguard, native);
    final raw = await _channel.invokeMapMethod<String, dynamic>(
        'startTunnel', <String, dynamic>{
      'protocol': 'wireguard',
      'config': profile,
      'namespace': namespace,
      'account': account,
    }).timeout(const Duration(seconds: 30));
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['protocol'] != 'wireguard' ||
        raw['state'] != 'connecting' ||
        raw['peerHandshakeVerified'] != false) {
      throw const FormatException('IOS_NATIVE_START_RESPONSE_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<Map<String, dynamic>> status() async {
    if (!Platform.isIOS) return const {'state': 'unavailable'};
    final raw = await _channel.invokeMapMethod<String, dynamic>(
        'getTunnelStatus').timeout(const Duration(seconds: 8));
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['state'] is! String || raw['verified'] is! bool) {
      throw const FormatException('IOS_NATIVE_STATUS_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<void> stop() async {
    if (!Platform.isIOS) throw const FormatException('IOS_REQUIRED');
    final raw = await _channel.invokeMapMethod<String, dynamic>(
        'stopTunnel').timeout(const Duration(seconds: 12));
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['state'] is! String) {
      throw const FormatException('IOS_NATIVE_STOP_RESPONSE_INVALID');
    }
  }
}
