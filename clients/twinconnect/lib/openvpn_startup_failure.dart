/// Categorizes native OpenVPN diagnostics into safe, actionable error codes.
///
/// Raw process output can contain addresses and configuration data. Only
/// allowlisted codes leave this classifier; never return an engine log line.
class OpenVpnStartupFailure {
  static String? classify(String message) {
    final line = message.toLowerCase();
    if (line.contains('auth_failed') ||
        line.contains('authentication failed')) {
      return 'OPENVPN_AUTH_REJECTED';
    }
    if (line.contains('certificate verify failed') ||
        line.contains('verify error')) {
      return 'OPENVPN_CERTIFICATE_REJECTED';
    }
    if (line.contains('cannot open tun/tap') ||
        line.contains('all tap-windows adapters') ||
        line.contains('no tap-windows adapters') ||
        line.contains('tap-windows adapter not found') ||
        line.contains('wintun adapter') && line.contains('not found')) {
      return 'OPENVPN_ADAPTER_UNAVAILABLE';
    }
    if (line.contains('access is denied') ||
        line.contains('permission denied') ||
        line.contains('requires administrator')) {
      return 'OPENVPN_PERMISSION_DENIED';
    }
    if (line.contains('options error') ||
        line.contains('unrecognized option')) {
      return 'OPENVPN_OPTIONS_INVALID';
    }
    if (line.contains('cannot resolve host address') ||
        line.contains('no such host is known')) {
      return 'OPENVPN_ENDPOINT_DNS_FAILED';
    }
    if (line.contains('windows route add command failed') ||
        line.contains('route addition failed')) {
      return 'OPENVPN_ROUTE_FAILED';
    }
    return null;
  }

  /// These errors cannot resolve by waiting for initialization.
  /// Others are only reported if the child process actually exits.
  static bool isTerminal(String reason) =>
      reason == 'OPENVPN_AUTH_REJECTED' ||
      reason == 'OPENVPN_CERTIFICATE_REJECTED' ||
      reason == 'OPENVPN_ADAPTER_UNAVAILABLE' ||
      reason == 'OPENVPN_PERMISSION_DENIED' ||
      reason == 'OPENVPN_OPTIONS_INVALID';
}
