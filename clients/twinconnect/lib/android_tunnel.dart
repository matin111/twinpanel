import 'dart:io';

import 'package:flutter/services.dart';

import 'native_vpn_bridge.dart';
import 'protocols.dart';
import 'vpn_policy.dart';

/// Android-only bridge using the actual WireGuard JNI tunnel implementation.
///
/// Cisco/OpenConnect requires its own native transport and is never converted
/// to WireGuard. Client secrets are transferred only via the in-memory
/// platform channel, never stored in shared preferences.
class AndroidTunnelController {
  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  const AndroidTunnelController();

  /// Only existing panel-provided profiles, never synthetic endpoint data.
  /// The user explicitly chooses a node when multiple profiles are present.
  static List<WireGuardNode> wireGuardNodes(ClientProtocolProfiles profiles) {
    if (profiles.protocol.code != 'wireguard') {
      throw const FormatException('WRONG_NATIVE_PROTOCOL');
    }
    final results = <WireGuardNode>[];
    for (final item in profiles.items) {
      final raw = item['config'];
      if (raw is! String || raw.trim().isEmpty) continue;
      final nodeName = item['node'] ?? item['server'] ?? item['name'];
      final displayName = nodeName is String && nodeName.trim().isNotEmpty
          ? nodeName.trim()
          : 'WireGuard server ${results.length + 1}';
      // The configuration itself is kept in process memory only.
      results.add(WireGuardNode(name: displayName, config: raw));
    }
    return List.unmodifiable(results);
  }

  Future<Map<String, dynamic>> connectWireGuard({
    required WireGuardNode node,
    required VpnPolicy policy,
    required NativeVpnCapabilities capabilities,
    required NativeProtocolReadiness nativeProtocols,
  }) async {
    if (!Platform.isAndroid) {
      throw PlatformException(
        code: 'PLATFORM_UNSUPPORTED',
        message: 'WireGuard native integration is Android-only in this build.',
      );
    }
    final definition = VpnProtocols.byCode('wireguard')!;
    NativeVpnBridge.requireProtocolSafeToConnect(
      policy, capabilities, definition, nativeProtocols,
    );
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'startTunnel',
      {
        'protocol': definition.code,
        'config': node.config,
        'policy': policy.toJson(),
      },
    );
    if (raw == null || raw['protocol'] != 'wireguard' ||
        raw['state'] != 'interface_up' ||
        raw['peerHandshakeVerified'] != false) {
      throw const FormatException('NATIVE_TUNNEL_STATUS_INVALID');
    }
    return Map.unmodifiable(raw);
  }

  Future<Map<String, dynamic>> stop() async {
    if (!Platform.isAndroid) {
      throw PlatformException(
        code: 'PLATFORM_UNSUPPORTED',
        message: 'No Android native VPN bridge.',
      );
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>('stopTunnel');
    if (raw == null || raw['state'] != 'down') {
      throw const FormatException('NATIVE_TUNNEL_STOP_UNVERIFIED');
    }
    return Map.unmodifiable(raw);
  }

  Future<Map<String, dynamic>> status() async {
    if (!Platform.isAndroid) {
      return const {'state': 'unavailable'};
    }
    final raw = await _channel.invokeMapMethod<String, dynamic>(
      'getTunnelStatus',
    );
    if (raw == null) return const {'state': 'unavailable'};
    return Map.unmodifiable(raw);
  }

  /// Cisco cannot be started by WireGuard; fail closed until a reviewed
  /// libopenconnect engine forwards packets via Android VpnService.
  Future<Never> connectCisco() async {
    throw PlatformException(
      code: 'OPENCONNECT_CORE_NOT_INSTALLED',
      message: 'Cisco/OpenConnect native core is not installed in this build.',
    );
  }
}

class WireGuardNode {
  const WireGuardNode({
    required this.name,
    required this.config,
    this.nodeId,
  });

  final String? nodeId;
  final String name;
  /// Sensitive: never print or persist.
  final String config;
}
