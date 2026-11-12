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

  static Future<String> _publicIp() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 4)
      ..findProxy = (_) => 'DIRECT';
    try {
      final request = await client.getUrl(
        Uri.https('api.ipify.org', '/', {'format': 'json'}),
      ).timeout(const Duration(seconds: 6));
      final response = await request.close()
          .timeout(const Duration(seconds: 6));
      if (response.statusCode != 200) {
        throw const FormatException('L2TP_PUBLIC_IP_UNAVAILABLE');
      }
      final body = await utf8.decoder.bind(response).join()
          .timeout(const Duration(seconds: 6));
      if (body.length > 512) {
        throw const FormatException('L2TP_PUBLIC_IP_INVALID');
      }
      final json = jsonDecode(body);
      final raw = json is Map ? json['ip'] : null;
      final ip = raw is String ? InternetAddress.tryParse(raw) : null;
      if (ip == null || ip.type != InternetAddressType.IPv4) {
        throw const FormatException('L2TP_PUBLIC_IP_INVALID');
      }
      return ip.address;
    } finally {
      client.close(force: true);
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
      default: return 'L2TP_CONNECTION_FAILED';
    }
  }

  Future<String> start(L2tpProfile profile) async {
    if (!Platform.isWindows) throw const FormatException('L2TP_WINDOWS_ONLY');
    if (_busy || _ownsEntry) throw const FormatException('L2TP_ALREADY_RUNNING');
    _busy = true;
    try {
      final baselineIp = await _publicIp();
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
    if (_verifiedIp == null) return false;
    try {
      final status = await _status();
      if (status.state != 2) {
        _verifiedIp = null;
        return false;
      }
      return await _publicIp() == _verifiedIp;
    } catch (_) {
      return false;
    }
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
    } finally {
      _busy = false;
    }
  }
}
