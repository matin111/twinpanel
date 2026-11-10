import 'dart:io';

import 'package:flutter/services.dart';

import 'vpn_policy.dart';
import 'protocols.dart';

/// Versioned channel for OS-native VPN capabilities.
///
/// Windows now has a real native channel, but no tunnel engine yet.
/// Missing plugins, incompatible contract versions, or errors always return
/// "unavailable" rather than making false kill-switch/connection claims.
class NativeVpnBridge {
  static const MethodChannel _channel =
      MethodChannel('com.twinpanel.twinconnect/vpn');

  static VpnPlatform get platform {
    if (Platform.isAndroid) return VpnPlatform.android;
    if (Platform.isWindows) return VpnPlatform.windows;
    if (Platform.isIOS) return VpnPlatform.ios;
    if (Platform.isMacOS) return VpnPlatform.macos;
    return VpnPlatform.other;
  }

  static Future<NativeVpnCapabilities> probe() async {
    final os = platform;
    if (os != VpnPlatform.android && os != VpnPlatform.windows) {
      // iOS/macOS have no native VPN bridge yet.
      return NativeVpnCapabilities.unavailable(os);
    }
    try {
      final capabilities = await _channel.invokeMethod<Map<dynamic, dynamic>>(
        'getCapabilities',
      );
      if (capabilities == null) {
        return NativeVpnCapabilities.unavailable(os);
      }
      return NativeVpnCapabilities.fromNativeMap(os, capabilities);
    } on MissingPluginException {
      return NativeVpnCapabilities.unavailable(os);
    } on PlatformException {
      return NativeVpnCapabilities.unavailable(os);
    } catch (_) {
      return NativeVpnCapabilities.unavailable(os);
    }
  }


  static Future<NativeProtocolReadiness> protocolReadiness() async {
    // Missing plugin is expected until real protocol engines are built.
    if (platform != VpnPlatform.android && platform != VpnPlatform.windows) {
      // No iOS/macOS protocol adapter has been installed.
      return const NativeProtocolReadiness(supportedCodes: {});
    }
    // This additional OS-level probe is mandatory: a plugin must not report
    // protocol names without an actually initialized native VPN engine.
    final capabilities = await probe();
    if (!capabilities.engineReady || !capabilities.fullTunnel) {
      return const NativeProtocolReadiness(supportedCodes: {});
    }
    try {
      final raw = await _channel.invokeMethod<Map<dynamic, dynamic>>(
        'getProtocolCapabilities',
      );
      return NativeProtocolReadiness.fromNative(raw);
    } on MissingPluginException {
      return const NativeProtocolReadiness(supportedCodes: {});
    } on PlatformException {
      return const NativeProtocolReadiness(supportedCodes: {});
    } catch (_) {
      return const NativeProtocolReadiness(supportedCodes: {});
    }
  }

  /// A protocol-specific connection may be attempted in a future client only
  /// when BOTH the native policy guard and protocol integration are confirmed.
  static void requireProtocolSafeToConnect(
    VpnPolicy policy,
    NativeVpnCapabilities capabilities,
    VpnProtocolDefinition protocol,
    NativeProtocolReadiness nativeProtocols,
  ) {
    requireSafeToConnect(policy, capabilities);
    if (!capabilities.engineReady || !nativeProtocols.supports(protocol.code)) {
      throw StateError('PROTOCOL_ENGINE_NOT_READY: ${protocol.code}');
    }
  }

  /// Future engines must call this gate before requesting a connection.
  ///
  /// Saving a policy NEVER invokes or connects a native VPN tunnel.
  static void requireSafeToConnect(
    VpnPolicy policy,
    NativeVpnCapabilities capabilities,
  ) {
    final reasons = policy.connectionProblems(capabilities);
    if (reasons.isNotEmpty) {
      throw StateError('NATIVE_VPN_POLICY_NOT_ENFORCED: ${reasons.join(',')}');
    }
  }
}
