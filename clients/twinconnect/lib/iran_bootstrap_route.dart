import 'dart:async' show TimeoutException;
import 'dart:io';

/// Bootstrap route for a domestic access point when international DNS/routing
/// to the panel is unavailable. TCP dials the domestic IPv4 address, but the
/// original HTTPS hostname is retained for SNI and certificate validation.
///
/// No certificate exceptions, login bypass or local profile credentials.
/// A live Iranian gateway must forward this TLS SNI to the actual panel.
/// This code alone cannot restore a severed cross-border uplink.
class IranBootstrapRoute {
  const IranBootstrapRoute._();

  static const trustedHost = 'panel.matindnspro.sbs';
  static const configuredIpv4 = String.fromEnvironment(
    'TWINCONNECT_IRAN_BOOTSTRAP_IP',
    defaultValue: '94.183.231.158',
  );

  static bool supports(Uri url) =>
      url.scheme == 'https' &&
      url.host.toLowerCase() == trustedHost &&
      url.port == 443 &&
      url.userInfo.isEmpty;

  static InternetAddress? parsePublicIpv4(String value) {
    final candidate = InternetAddress.tryParse(value.trim());
    if (candidate == null || candidate.type != InternetAddressType.IPv4 ||
        candidate.isLoopback || candidate.isLinkLocal ||
        candidate.isMulticast) return null;
    final bytes = candidate.rawAddress;
    final a = bytes[0], b = bytes[1], c = bytes[2];
    // No internal, broadcast, benchmarking, carrier NAT or documentation IPs.
    if (a == 0 || a == 10 || a == 127 || a >= 224 ||
        a == 169 && b == 254 ||
        a == 172 && b >= 16 && b <= 31 ||
        a == 192 && b == 168 ||
        a == 100 && b >= 64 && b <= 127 ||
        a == 198 && (b == 18 || b == 19) ||
        a == 192 && b == 0 && c == 2 ||
        a == 198 && b == 51 && c == 100 ||
        a == 203 && b == 0 && c == 113) return null;
    return candidate;
  }

  static InternetAddress? targetFor(Uri url) =>
      supports(url) ? parsePublicIpv4(configuredIpv4) : null;

  /// HttpClient performs TLS over the returned TCP socket and validates the
  /// certificate against the ORIGINAL request URL hostname. Never change the
  /// request URL to https://<IP>/ or disable bad-certificate verification.
  static HttpClient clientFor(Uri requestUrl, InternetAddress destination) {
    if (!supports(requestUrl) ||
        destination.type != InternetAddressType.IPv4 ||
        parsePublicIpv4(destination.address) == null) {
      throw const FormatException('UNTRUSTED_IRAN_BOOTSTRAP_ROUTE');
    }
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 6)
      ..findProxy = (_) => 'DIRECT';
    client.connectionFactory = (Uri url, String? proxyHost, int? proxyPort) {
      if (!supports(url) || proxyHost != null || proxyPort != null) {
        throw const FormatException('UNTRUSTED_IRAN_BOOTSTRAP_ROUTE');
      }
      return Socket.startConnect(destination, url.port);
    };
    return client;
  }

  static bool isTransient(Object error) =>
      error is SocketException ||
      error is HandshakeException ||
      error is TimeoutException ||
      error is HttpException;
}
