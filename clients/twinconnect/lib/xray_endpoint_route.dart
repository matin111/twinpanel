import 'dart:async';
import 'dart:io';

import 'xray_inbound_profiles.dart';

/// Resolves and pins the selected VLESS server's IPv4 endpoint before
/// Windows TUN routes are installed. Only that one VPN server IP is exempted
/// from TUN routing, preventing Xray's upstream connection from looping
/// back into its own local SOCKS bridge. No other traffic is exempted.
class XrayEndpointRoute {
  const XrayEndpointRoute._();

  static String requirePublicIPv4(String raw) {
    final address = InternetAddress.tryParse(raw);
    if (address == null || address.type != InternetAddressType.IPv4 ||
        address.isLoopback || address.isLinkLocal ||
        address.isMulticast) {
      throw const FormatException('XRAY_ENDPOINT_IP_INVALID');
    }
    final octets = address.rawAddress;
    // Never bypass the VPN for an internal, shared, or reserved route.
    final a = octets[0], b = octets[1];
    if (a == 0 || a == 10 || a == 127 || a >= 224 ||
        (a == 100 && b >= 64 && b <= 127) ||
        (a == 169 && b == 254) ||
        (a == 172 && b >= 16 && b <= 31) ||
        (a == 192 && b == 168) ||
        (a == 198 && (b == 18 || b == 19))) {
      throw const FormatException('XRAY_ENDPOINT_IP_INVALID');
    }
    return address.address;
  }

  static Future<String> resolve(XrayInboundProfile profile) async {
    final hostname = profile.uri.host;
    final literal = InternetAddress.tryParse(hostname);
    if (literal != null) return requirePublicIPv4(literal.address);
    try {
      final addresses = await InternetAddress.lookup(
        hostname,
        type: InternetAddressType.IPv4,
      ).timeout(const Duration(seconds: 6));
      for (final address in addresses) {
        try {
          return requirePublicIPv4(address.address);
        } on FormatException {
          // Reject private and suspicious DNS responses. Do not install
          // exceptions for a private DNS address.
        }
      }
      throw const FormatException('XRAY_ENDPOINT_DNS_UNAVAILABLE');
    } catch (_) {
      throw const FormatException('XRAY_ENDPOINT_DNS_UNAVAILABLE');
    }
  }
}
