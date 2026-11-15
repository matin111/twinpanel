import 'dart:async';
import 'dart:io';

import 'package:flutter_vless/flutter_vless.dart';

import 'xray_inbound_profiles.dart';

/// Embedded Android Xray runtime specifically for VLESS/XHTTP Reality.
/// Native Xray owns its own Android VpnService. Never share the old libbox
/// TUN with this runtime or treat a socket-open event as VPN verification.
class AndroidXrayTunnel {
  AndroidXrayTunnel._() {
    _runtime = FlutterVless(onStatusChanged: (status) {
      _lastStatus = status;
    });
  }

  static final AndroidXrayTunnel instance = AndroidXrayTunnel._();
  late final FlutterVless _runtime;
  VlessStatus? _lastStatus;
  bool _initialized = false;
  bool _connected = false;
  int? _latencyMs;
  String? _activeNodeId;
  String? _activeInboundId;
  String? get activeNodeId => _activeNodeId;
  String? get activeInboundId => _activeInboundId;

  bool get isConnected => _connected;
  int? get latencyMs => _latencyMs;
  double? get downloadBps => _lastStatus?.downloadSpeed.toDouble();
  double? get uploadBps => _lastStatus?.uploadSpeed.toDouble();
  int? get receivedBytes => _lastStatus?.download;
  int? get sentBytes => _lastStatus?.upload;

  Future<void> initialize() async {
    if (!Platform.isAndroid) {
      throw const FormatException('XRAY_ANDROID_ONLY');
    }
    if (_initialized) return;
    await _runtime.initializeVless();
    _initialized = true;
  }

  Future<void> connect(XrayInboundProfile inbound) async {
    if (inbound.id != 'xhttp_reality' ||
        inbound.uri.scheme != 'vless' ||
        inbound.uri.queryParameters['type'] != 'xhttp' ||
        inbound.uri.queryParameters['security'] != 'reality') {
      throw const FormatException('XRAY_XHTTP_PROFILE_INVALID');
    }
    await initialize();
    if (!await _runtime.requestPermission()) {
      throw const FormatException('XRAY_VPN_PERMISSION_DENIED');
    }
    // Use the exact authenticated VLESS profile from the panel. The parser
    // preserves XHTTP settings (including path, mode, SNI, Reality public key
    // and short ID) and generates the native Xray configuration. Do not log or
    // persist config text: it includes user credentials.
    final config = FlutterVless.parseFromURL(inbound.uri.toString())
        .getFullConfiguration(indent: 0);
    try {
      await _runtime.startVless(
        remark: 'TwinConnect',
        config: config,
        proxyOnly: false,
      );
      // Only a real remote outbound delay response verifies the route.
      // The session can be up while the gateway blocks internet access.
      final verifiedDelay = await _runtime.getConnectedServerDelay(
          url: 'https://www.cloudflare.com/cdn-cgi/trace')
          .timeout(const Duration(seconds: 18));
      if (verifiedDelay <= 0) {
        throw const FormatException('XRAY_XHTTP_EGRESS_NOT_VERIFIED');
      }
      _latencyMs = verifiedDelay;
      _activeNodeId = inbound.serverId;
      _activeInboundId = inbound.id;
      _connected = true;
    } catch (_) {
      _connected = false;
      _latencyMs = null;
      _activeNodeId = null;
      _activeInboundId = null;
      try { await _runtime.stopVless(); } catch (_) {}
      rethrow;
    }
  }

  Future<void> disconnect() async {
    if (!_initialized) return;
    try {
      await _runtime.stopVless();
    } finally {
      _connected = false;
      _latencyMs = null;
      _activeNodeId = null;
      _activeInboundId = null;
      _lastStatus = null;
    }
  }
}
