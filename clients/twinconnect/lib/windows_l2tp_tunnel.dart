import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';

import 'l2tp_profile.dart';

/// Owns exactly the Windows RAS connection created by TwinConnect.
/// The pre-shared key is passed over the in-process native channel, never
/// through a shell or external command line.
class WindowsL2tpTunnel {
  static const _channel = MethodChannel('com.twinpanel.twinconnect/vpn');
  bool _busy = false;
  bool _ownsEntry = false;
  String? _verifiedIp;

  bool get isRunning => _verifiedIp != null;
  bool get hasChild => _ownsEntry;
  String? get exitIp => _verifiedIp;

  String? _baselineIp;
  String? _lastHealthError;

  /// A RAS status, HTTPS outage, and real route bypass are different failures.
  /// Do not collapse them into a generic "server disconnected" diagnostic.
  String? get lastHealthError => _lastHealthError;

  static Future<String> _readIp({
    required Uri url,
    required bool jsonBody,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 4)
      ..findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(url)
          .timeout(const Duration(seconds: 6));
      request.followRedirects = false;
      final response = await request.close()
          .timeout(const Duration(seconds: 6));
      if (response.statusCode != HttpStatus.ok) {
        throw const FormatException('L2TP_PUBLIC_IP_UNAVAILABLE');
      }
      final content = await utf8.decoder.bind(response).join()
          .timeout(const Duration(seconds: 6));
      if (content.length > 512) {
        throw const FormatException('L2TP_PUBLIC_IP_INVALID');
      }
      final String? text;
      if (jsonBody) {
        final decoded = jsonDecode(content);
        text = decoded is Map && decoded['ip'] is String
            ? decoded['ip'] as String : null;
      } else {
        text = content.trim();
      }
      final address = text == null ? null : InternetAddress.tryParse(text);
      if (address == null || address.type != InternetAddressType.IPv4 ||
          address.isLoopback || address.isLinkLocal ||
          address.isMulticast || address.address == '0.0.0.0') {
        throw const FormatException('L2TP_PUBLIC_IP_INVALID');
      }
      return address.address;
    } finally {
      client.close(force: true);
    }
  }

  /// Probe two independent HTTPS IPv4 echo services, on the current OS route.
  /// Both use DIRECT: an OS-level L2TP route must carry these packets.
  static Future<String> _publicIp() async {
    try {
      return await _readIp(
        url: Uri.https('api.ipify.org', '/', {'format': 'json'}),
        jsonBody: true,
      );
    } catch (_) {
      return _readIp(
        url: Uri.https('ipv4.icanhazip.com', '/'),
        jsonBody: false,
      );
    }
  }

  Future<({int state, int code})> _status() async {
    final values = await _channel.invokeMapMethod<String, dynamic>(
        'l2tpStatus').timeout(const Duration(seconds: 5));
    if (values == null || values['state'] is! int) {
      throw const FormatException('L2TP_STATUS_UNAVAILABLE');
    }
    return (state: values['state'] as int,
            code: values['code'] is int ? values['code'] as int : 0);
  }

  static String _failure(int code) {
    switch (code) {
      case 691: return 'L2TP_LOGIN_REJECTED';
      case 789: return 'L2TP_IPSEC_NEGOTIATION_FAILED';
      case 809: return 'L2TP_SERVER_UNREACHABLE';
      case 868: return 'L2TP_DNS_UNAVAILABLE';
      case 600: return 'L2TP_RAS_OPERATION_PENDING_600';
      case 632: return 'L2TP_RAS_ENTRY_SIZE_INVALID_632';
      case 633: return 'L2TP_RAS_PORT_IN_USE_633';
      case 635: return 'L2TP_RAS_UNKNOWN_ERROR_635';
      case 638: return 'L2TP_SERVER_NO_RESPONSE_638';
      case 645: return 'L2TP_RAS_AUTH_FAILURE_645';
      case 646: return 'L2TP_RAS_ACCOUNT_RESTRICTED_646';
      case 649: return 'L2TP_RAS_ACCOUNT_PERMISSION_649';
      case 651: return 'L2TP_RAS_MODEM_OR_NETWORK_ERROR_651';
      case 720: return 'L2TP_PPP_PROTOCOL_NEGOTIATION_FAILED_720';
      case 734: return 'L2TP_PPP_LINK_TERMINATED_734';
      case 766: return 'L2TP_IPSEC_CERTIFICATE_MISSING_766';
      case 768: return 'L2TP_IPSEC_VALIDATION_FAILED_768';
      case 788: return 'L2TP_IPSEC_POLICY_FAILED_788';
      case 806: return 'L2TP_GRE_BLOCKED_806';
      case 807: return 'L2TP_CONNECTION_INTERRUPTED_807';
      case 812: return 'L2TP_RAS_POLICY_REJECTED_812';
      case 13801: return 'L2TP_IKE_AUTH_FAILED_13801';
      case 13806: return 'L2TP_IKE_POLICY_FAILED_13806';
      default: return code > 0
          ? 'L2TP_RAS_ERROR_$code'
          : 'L2TP_NATIVE_FAILURE_NO_CODE';
    }
  }

  Future<String> start(L2tpProfile profile) async {
    if (!Platform.isWindows) throw const FormatException('L2TP_WINDOWS_ONLY');
    if (_busy || _ownsEntry) throw const FormatException('L2TP_ALREADY_RUNNING');
    _busy = true;
    try {
      final baselineIp = await _publicIp();
      _baselineIp = baselineIp;
      _lastHealthError = null;
      final started = await _channel.invokeMethod<bool>('startL2tp', {
        'server': profile.server,
        'username': profile.username,
        'password': profile.password,
        'psk': profile.psk,
      }).timeout(const Duration(seconds: 10));
      if (started != true) {
        throw const FormatException('L2TP_NATIVE_START_FAILED');
      }
      _ownsEntry = true;
      final deadline = DateTime.now().add(const Duration(seconds: 65));
      while (DateTime.now().isBefore(deadline)) {
        final status = await _status();
        if (status.state == 2) {
          final newIp = await _publicIp();
          if (newIp == baselineIp) {
            throw const FormatException('L2TP_EGRESS_NOT_VERIFIED');
          }
          _verifiedIp = newIp;
          _lastHealthError = null;
          return newIp;
        }
        if (status.state == -1) {
          throw FormatException(_failure(status.code));
        }
        await Future<void>.delayed(const Duration(milliseconds: 700));
      }
      throw const FormatException('L2TP_CONNECT_TIMEOUT');
    } catch (_) {
      // Never claim successful connection if Windows RAS remains pending.
      if (_ownsEntry) {
        try { await _channel.invokeMethod<bool>('stopL2tp'); } catch (_) {}
        try { await _channel.invokeMethod<bool>('resetL2tpFailure'); }
        catch (_) {}
      }
      _verifiedIp = null;
      _baselineIp = null;
      try {
        final status = await _status();
        _ownsEntry = status.state != 0;
      } catch (_) {}
      rethrow;
    } finally {
      _busy = false;
    }
  }

  Future<bool> checkHealth() async {
    if (_verifiedIp == null) {
      _lastHealthError = 'L2TP_RAS_DISCONNECTED';
      return false;
    }
    try {
      final status = await _status();
      if (status.state != 2) {
        _lastHealthError = status.state == -1 && status.code > 0
            ? _failure(status.code)
            : 'L2TP_RAS_DISCONNECTED';
        _verifiedIp = null;
        return false;
      }
    } catch (_) {
      _lastHealthError = 'L2TP_RAS_STATUS_UNAVAILABLE';
      return false;
    }
    String currentIp;
    try {
      currentIp = await _publicIp();
    } catch (_) {
      // One failed HTTPS provider is not evidence of a broken L2TP server;
      // two separate providers have both failed by the time we get here.
      _lastHealthError = 'L2TP_HEALTH_PROBE_UNAVAILABLE';
      return false;
    }
    if (currentIp == _baselineIp) {
      // RAS may still report connected even after the default route is lost.
      // Do not claim "online" when direct traffic has bypassed the VPN.
      _lastHealthError = 'L2TP_ROUTE_BYPASS_DETECTED';
      return false;
    }
    // An exit-side IP can legitimately rotate while the same RAS session is
    // still connected. Compare against pre-VPN baseline, not the first exit.
    _verifiedIp = currentIp;
    _lastHealthError = null;
    return true;
  }

  Future<({int received, int sent})?> readTrafficTotals() async {
    if (!isRunning) return null;
    try {
      final values = await _channel.invokeMapMethod<String, dynamic>(
          'l2tpTraffic').timeout(const Duration(seconds: 5));
      if (values == null || values['rxBytes'] is! int ||
          values['txBytes'] is! int) return null;
      final rx = values['rxBytes'] as int, tx = values['txBytes'] as int;
      return rx >= 0 && tx >= 0 ? (received: rx, sent: tx) : null;
    } catch (_) {
      return null;
    }
  }

  Future<void> stop() async {
    if (_busy) throw const FormatException('L2TP_TUNNEL_BUSY');
    _busy = true;
    try {
      final result = await _channel.invokeMethod<bool>('stopL2tp')
          .timeout(const Duration(seconds: 15));
      if (result != true) {
        throw const FormatException('L2TP_DISCONNECT_NOT_CONFIRMED');
      }
      _ownsEntry = false;
      _verifiedIp = null;
      _baselineIp = null;
      _lastHealthError = null;
    } finally {
      _busy = false;
    }
  }
}
