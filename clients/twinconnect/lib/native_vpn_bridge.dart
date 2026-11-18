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


  /// Read-only WFP preflight. In particular, WFP availability is never
  /// proof that a privileged kill-switch service exists or is enforcing
  /// a global network block. Missing/legacy channels fail closed.
  static Future<Map<String, dynamic>> globalKillSwitchStatus() async {
    const unavailable = <String, dynamic>{
      'contractVersion': 1,
      'wfpAvailable': false,
      'serviceInstalled': false,
      'armed': false,
      'enforcedV4': false,
      'enforcedV6': false,
      'recoveryVerified': false,
      'reason': 'NATIVE_GLOBAL_GUARD_UNAVAILABLE',
    };
    if (platform != VpnPlatform.windows) return unavailable;
    try {
      final raw = await _channel.invokeMethod<Map<dynamic, dynamic>>(
        'getGlobalKillSwitchStatus',
      );
      if (raw == null || raw['contractVersion'] != 1) {
        return unavailable;
      }
      // Do not trust one reported flag. All key conditions are mandatory.
      final armed = raw['armed'] == true &&
          raw['serviceInstalled'] == true &&
          raw['enforcedV4'] == true &&
          raw['enforcedV6'] == true &&
          raw['recoveryVerified'] == true;
      return <String, dynamic>{
        ...unavailable,
        'wfpAvailable': raw['wfpAvailable'] == true,
        'serviceInstalled': raw['serviceInstalled'] == true,
        'armed': armed,
        'enforcedV4': raw['enforcedV4'] == true,
        'enforcedV6': raw['enforcedV6'] == true,
        'recoveryVerified': raw['recoveryVerified'] == true,
        'reason': raw['reason'] is String
            ? raw['reason'] : 'NATIVE_GLOBAL_GUARD_UNAVAILABLE',
      };
    } catch (_) {
      return unavailable;
    }
  }

  /// Experimental VM-only command bridge, NOT a production protection toggle.
  /// The Windows native layer independently requires TWINCONNECT_DISPOSABLE_VM=1
  /// and Windows Administrators access to the privileged guard pipe.
  /// A positive acknowledgement alone is not proof of leak-free filtering.
  static Future<Map<String, dynamic>> experimentalVmGlobalGuard({
    required String action,
    String alias = '',
    String endpoint = '',
    String executable = '',
  }) async {
    if (platform != VpnPlatform.windows ||
        Platform.environment['TWINCONNECT_DISPOSABLE_VM'] != '1') {
      return const {'contractVersion': 1, 'success': false,
        'reason': 'VM_ONLY'};
    }
    if (!const {'status', 'arm', 'disarm'}.contains(action)) {
      return const {'contractVersion': 1, 'success': false,
        'reason': 'INVALID_ACTION'};
    }
    try {
      final raw = await _channel.invokeMethod<Map<dynamic, dynamic>>(
        'experimentalVmGlobalGuard', {
          'action': action,
          'alias': alias,
          'endpoint': endpoint,
          'executable': executable,
        },
      ).timeout(const Duration(seconds: 5));
      if (raw == null || raw['contractVersion'] != 1) {
        return const {'contractVersion': 1, 'success': false,
          'reason': 'INVALID_NATIVE_RESPONSE'};
      }
      return {
        'contractVersion': 1,
        'success': raw['success'] == true,
        'reason': raw['reason'] is String ? raw['reason'] : 'UNKNOWN',
      };
    } catch (_) {
      return const {'contractVersion': 1, 'success': false,
        'reason': 'GUARD_CONTROL_UNAVAILABLE'};
    }
  }

  static Future<NativeProtocolReadiness> protocolReadiness({
    NativeVpnCapabilities? validatedCapabilities,
  }) async {
    // Missing plugin is expected until real protocol engines are built.
    if (platform != VpnPlatform.android && platform != VpnPlatform.windows) {
      // No iOS/macOS protocol adapter has been installed.
      return const NativeProtocolReadiness(supportedCodes: {});
    }
    // This additional OS-level probe is mandatory: a plugin must not report
    // protocol names without an actually initialized native VPN engine.
    // An immediately preceding native capability probe can be reused
    // during the same connect attempt instead of calling the platform
    // channel twice. All other callers still probe normally.
    final capabilities = validatedCapabilities ?? await probe();
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

  /// Applies an account-scoped policy to the NEXT Android VpnService.Builder.
  /// A native acknowledgement is mandatory; this never changes live routes.
  static Future<void> configureAndroidAppRouting(VpnPolicy policy) async {
    if (platform != VpnPlatform.android) return;
    if (policy.routingMode != VpnRoutingMode.fullTunnel &&
        policy.killSwitchRequested) {
      throw StateError('SPLIT_TUNNEL_GUARD_CONFLICT');
    }
    final response = await _channel.invokeMapMethod<String, dynamic>(
      'configureAppRouting',
      {
        'routingMode': policy.routingMode.name,
        'appIds': policy.appIds,
      },
    );
    if (response?['routingMode'] != policy.routingMode.name ||
        response?['appliedOnNextTunnel'] != true) {
      throw StateError('APP_ROUTING_NOT_CONFIRMED');
    }
  }

  /// Cisco uses pinned libopenconnect with SharedTunVpnService (not GoBackend).
  /// It supports the in-process shared-TUN guard; other unsupported policy
  /// features must still fail closed before loading credentials.
  static void requireAndroidCiscoSafeToConnect(VpnPolicy policy) {
    final problems = <String>[];
    if (platform != VpnPlatform.android) problems.add('ANDROID_ONLY');
    if (policy.routingMode != VpnRoutingMode.fullTunnel &&
        policy.killSwitchRequested) {
      problems.add('SPLIT_TUNNEL_GUARD_CONFLICT');
    }
    if (policy.routingMode != VpnRoutingMode.fullTunnel &&
        policy.appIds.isEmpty) problems.add('NO_SELECTED_APPS');
    if (policy.dnsMode != VpnDnsMode.protected) {
      problems.add('DNS_POLICY_NOT_SUPPORTED');
    }
    if (policy.ipv6Mode != VpnIpv6Mode.tunnelOrBlock) {
      problems.add('IPV6_POLICY_NOT_SUPPORTED');
    }
    if (policy.allowLan) problems.add('LAN_BYPASS_NOT_IMPLEMENTED');
    if (policy.autoConnect) problems.add('AUTOCONNECT_NOT_IMPLEMENTED');
    if (policy.autoReconnect) problems.add('AUTO_RECONNECT_NOT_IMPLEMENTED');
    if (problems.isNotEmpty) {
      throw StateError('CISCO_POLICY_NOT_SUPPORTED: ${problems.join(',')}');
    }
  }

  /// Shared full-device TUN contract enforced by all non-WireGuard cores.
  /// Per-app routing, bypass and unverified reconnect cannot silently weaken
  /// the one-button packet guard.
  static void requireAndroidSharedTunSafeToConnect(VpnPolicy policy) {
    requireAndroidCiscoSafeToConnect(policy);
  }

  /// AWG has different native cryptography from WireGuard, but the same
  /// shared-TUN full-device routing and disconnected-traffic guard policy.
  static void requireAndroidAmneziaWgSafeToConnect(VpnPolicy policy) {
    try {
      requireAndroidCiscoSafeToConnect(policy);
    } on StateError {
      throw StateError('AWG_POLICY_NOT_SUPPORTED');
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
