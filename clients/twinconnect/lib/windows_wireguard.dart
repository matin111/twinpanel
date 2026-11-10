import 'dart:io';

import 'package:flutter/services.dart';

import 'android_tunnel.dart';
import 'native_vpn_bridge.dart';
import 'protocols.dart';
import 'vpn_policy.dart';

/// Official WireGuard for Windows service bridge.
///
/// Requires an installed official WireGuard client and an Administrator-run
/// TwinConnect process. The native bridge encrypts the config with Windows
/// DPAPI; no plaintext profile is written to disk or shared preferences.
///
/// 'interface_up' is not a peer handshake or internet connectivity proof.
class WindowsWireGuardController {
  const WindowsWireGuardController();

  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  static WireGuardNode configForSingleNode(
      ClientProtocolProfiles profiles, String selectedId) {
    if (profiles.protocol.code != 'wireguard') {
      throw const FormatException('WRONG_NATIVE_PROTOCOL');
    }
    final matches = profiles.items.where((item) {
      final id = item['node_id'];
      return id is String && id == selectedId ||
          id is int && id.toString() == selectedId;
    }).toList(growable: false);
    if (matches.length != 1 || matches.single['config'] is! String) {
      throw const FormatException('WIREGUARD_NODE_PROFILE_MISSING');
    }
    final config = matches.single['config'] as String;
    if (config.isEmpty || config.length > 65536) {
      throw const FormatException('WIREGUARD_NODE_PROFILE_INVALID');
    }
    final name = matches.single['node'];
    return WireGuardNode(
      name: name is String && name.isNotEmpty ? name : selectedId,
      config: config,
    );
  }

  Future<Map<String, dynamic>> start({
    required WireGuardNode node,
    required VpnPolicy policy,
    required NativeVpnCapabilities capabilities,
    required NativeProtocolReadiness nativeProtocols,
  }) async {
    if (!Platform.isWindows) {
      throw PlatformException(code: 'WINDOWS_REQUIRED');
    }
    NativeVpnBridge.requireProtocolSafeToConnect(
      policy, capabilities, VpnProtocols.byCode('wireguard')!, nativeProtocols,
    );
    final raw = await _channel.invokeMapMethod<String, dynamic>('startTunnel', {
      'protocol': 'wireguard',
      'config': node.config,
      'policy': policy.toJson(),
    });
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['protocol'] != 'wireguard' ||
        (raw['state'] != 'interface_up' &&
         raw['state'] != 'peer_verified') ||
        (raw['state'] == 'peer_verified'
            ? raw['peerHandshakeVerified'] != true
            : raw['peerHandshakeVerified'] != false)) {
      throw const FormatException('NATIVE_TUNNEL_STATUS_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<Map<String, dynamic>> status() async {
    if (!Platform.isWindows) return const {'state': 'unavailable'};
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'getTunnelStatus',
    );
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['protocol'] != 'wireguard' ||
        (raw['state'] != 'interface_up' &&
         raw['state'] != 'peer_verified' &&
         raw['state'] != 'needs_cleanup' &&
         raw['state'] != 'down') ||
        (raw['state'] == 'peer_verified'
            ? raw['peerHandshakeVerified'] != true
            : raw['peerHandshakeVerified'] != false)) {
      throw const FormatException('NATIVE_TUNNEL_STATUS_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<Map<String, dynamic>> stop() async {
    if (!Platform.isWindows) {
      throw PlatformException(code: 'WINDOWS_REQUIRED');
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>('stopTunnel');
    if (raw == null || raw['contractVersion'] != 1 ||
        raw['protocol'] != 'wireguard' || raw['state'] != 'down') {
      throw const FormatException('NATIVE_TUNNEL_STOP_UNVERIFIED');
    }
    return Map.unmodifiable(raw);
  }
}
