import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Read-only public IP probe. Never declares a VPN online or changes routes.
/// A single external service can be blocked while the tunnel is healthy.
class WindowsPublicIpProbe {
  static String? parseResponse(String response) {
    final text = response.trim();
    String? candidate = text;
    if (text.startsWith('{')) {
      try {
        final decoded = jsonDecode(text);
        candidate = decoded is Map ? decoded['ip'] as String? : null;
      } on FormatException {
        return null;
      } on TypeError {
        return null;
      }
    }
    if (candidate == null || candidate.length > 45) return null;
    final address = InternetAddress.tryParse(candidate);
    if (address == null) return null;
    if (address.isLoopback || address.isLinkLocal || address.isMulticast) {
      return null;
    }
    return address.address;
  }

  static Future<String> read() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 4)
      ..findProxy = (_) => 'DIRECT';
    try {
      for (final uri in [
        Uri.https('api.ipify.org', '/', {'format': 'json'}),
        Uri.https('checkip.amazonaws.com', '/'),
      ]) {
        try {
          final request = await client.getUrl(uri)
              .timeout(const Duration(seconds: 5));
          final response = await request.close()
              .timeout(const Duration(seconds: 5));
          if (response.statusCode != 200) continue;
          final body = await utf8.decoder.bind(response).join()
              .timeout(const Duration(seconds: 5));
          if (body.length > 256) continue;
          final ip = parseResponse(body);
          if (ip != null) return ip;
        } catch (_) {
          // Try the independent provider, never infer that a tunnel is down.
        }
      }
      throw const FormatException('PUBLIC_IP_UNAVAILABLE');
    } finally {
      client.close(force: true);
    }
  }
}
