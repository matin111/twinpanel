import 'dart:io';

import 'package:flutter/services.dart';

import 'amneziawg_profile.dart';
import 'native_vpn_bridge.dart';
import 'vpn_policy.dart';
import 'protocols.dart';

/// Native AmneziaWG is its own Windows driver and service, not WireGuard.
/// The official app must be installed on Windows with elevated service rights.
class WindowsAmneziaWgController {
  const WindowsAmneziaWgController();
  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  static AmneziaWgProfile configForSingleNode(
      ClientProtocolProfiles profiles, String selectedId) {
    if (profiles.protocol.code != 'amneziawg') {
      throw const FormatException('AWG_WRONG_PROTOCOL');
    }
    final matches = profiles.items.where(
      (item) => item['node_id']?.toString() == selectedId,
    ).toList(growable: false);
    if (matches.length != 1) {
      throw const FormatException('AWG_NODE_PROFILE_MISSING');
    }
    return AmneziaWgProfile.fromItem(matches.single);
  }

  Future<NativeVpnCapabilities> capabilities() async {
    if (!Platform.isWindows) {
      return NativeVpnCapabilities.unavailable(VpnPlatform.windows);
    }
    try {
      final raw = await _channel.invokeMapMethod<dynamic, dynamic>(
        'getAmneziaWgCapabilities',
      );
      if (raw == null) {
        return NativeVpnCapabilities.unavailable(VpnPlatform.windows);
      }
      return NativeVpnCapabilities.fromNativeMap(
          VpnPlatform.windows, raw);
    } catch (_) {
      return NativeVpnCapabilities.unavailable(VpnPlatform.windows);
    }
  }

  static Map<String, dynamic> _validated(dynamic response) {
    if (response is! Map ||
        response['contractVersion'] != 1 ||
        response['protocol'] != 'amneziawg' ||
        !const ['interface_up', 'peer_verified', 'down',
                'needs_cleanup', 'unmanaged_service']
            .contains(response['state'])) {
      throw const FormatException('AWG_NATIVE_STATUS_INVALID');
    }
    final isVerified = response['state'] == 'peer_verified';
    if (response['peerHandshakeVerified'] != isVerified) {
      throw const FormatException('AWG_NATIVE_STATUS_INVALID');
    }
    return Map<String, dynamic>.from(response);
  }

  Future<Map<String, dynamic>> start({
    required AmneziaWgProfile profile,
    required VpnPolicy policy,
  }) async {
    if (!Platform.isWindows) {
      throw const FormatException('AWG_WINDOWS_REQUIRED');
    }
    final available = await capabilities();
    NativeVpnBridge.requireSafeToConnect(policy, available);
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'startAmneziaWg', {'config': profile.config},
    ).timeout(const Duration(seconds: 25));
    final status = _validated(raw);
    if (status['state'] != 'interface_up' &&
        status['state'] != 'peer_verified') {
      throw const FormatException('AWG_START_UNVERIFIED');
    }
    return status;
  }

  Future<Map<String, dynamic>> status() async {
    if (!Platform.isWindows) {
      throw const FormatException('AWG_WINDOWS_REQUIRED');
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'getAmneziaWgStatus',
    ).timeout(const Duration(seconds: 9));
    return _validated(raw);
  }

  Future<Map<String, dynamic>> stop() async {
    if (!Platform.isWindows) {
      throw const FormatException('AWG_WINDOWS_REQUIRED');
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'stopAmneziaWg',
    ).timeout(const Duration(seconds: 25));
    final status = _validated(raw);
    if (status['state'] != 'down') {
      throw const FormatException('AWG_STOP_UNVERIFIED');
    }
    return status;
  }
}
