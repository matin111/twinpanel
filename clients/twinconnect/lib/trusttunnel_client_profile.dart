import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'xray_endpoint_route.dart';

/// Strict decoder of official TrustTunnel tt://? v1 TLV links.
/// Never log, cache, or pass the credential-bearing URI to process argv.
class TrustTunnelClientProfile {
  TrustTunnelClientProfile._(this.hostname, this.address, this.username,
      this.password, this.certificatePem, this.upstream, this.clientRandom,
      this.antiDpi, this.customSni);

  final String hostname, address, username, password;
  final String certificatePem, upstream, clientRandom;
  final bool antiDpi;
  final String? customSni;

  static int _varint(Uint8List bytes, List<int> index) {
    if (index[0] >= bytes.length) {
      throw const FormatException('TRUSTTUNNEL_TLV_INVALID');
    }
    final first = bytes[index[0]];
    final count = 1 << (first >> 6);
    if (count > 8 || index[0] + count > bytes.length) {
      throw const FormatException('TRUSTTUNNEL_TLV_INVALID');
    }
    var value = first & 0x3f;
    for (var i = 1; i < count; i++) {
      value = value * 256 + bytes[index[0] + i];
    }
    index[0] += count;
    return value;
  }

  static String _pem(Uint8List der) {
    final out = StringBuffer();
    var position = 0, certCount = 0;
    while (position < der.length) {
      if (der[position] != 0x30 || position + 2 > der.length) {
        throw const FormatException('TRUSTTUNNEL_CERT_INVALID');
      }
      final first = der[position + 1];
      var length = first, header = 2;
      if ((first & 0x80) != 0) {
        final n = first & 0x7f;
        if (n == 0 || n > 4 || position + 2 + n > der.length) {
          throw const FormatException('TRUSTTUNNEL_CERT_INVALID');
        }
        length = 0;
        for (var i = 0; i < n; i++) {
          length = length * 256 + der[position + 2 + i];
        }
        header += n;
      }
      final end = position + header + length;
      if (end > der.length || length < 100 || ++certCount > 8) {
        throw const FormatException('TRUSTTUNNEL_CERT_INVALID');
      }
      final base = base64.encode(der.sublist(position, end));
      out.writeln('-----BEGIN CERTIFICATE-----');
      for (var i = 0; i < base.length; i += 64) {
        final endLine = i + 64 > base.length ? base.length : i + 64;
        out.writeln(base.substring(i, endLine));
      }
      out.writeln('-----END CERTIFICATE-----');
      position = end;
    }
    return out.toString();
  }

  static TrustTunnelClientProfile fromItem(Map<String, dynamic> item) {
    if (item['config_format'] != 'trusttunnel-deeplink') {
      throw const FormatException('TRUSTTUNNEL_FORMAT_INVALID');
    }
    final link = item['config'];
    if (link is! String || !link.startsWith('tt://?') ||
        link.length <= 6 || link.length > 32768) {
      throw const FormatException('TRUSTTUNNEL_DEEPLINK_INVALID');
    }
    late final Uint8List bytes;
    try {
      bytes = base64Url.decode(base64Url.normalize(link.substring(6)));
    } catch (_) {
      throw const FormatException('TRUSTTUNNEL_DEEPLINK_INVALID');
    }
    if (bytes.length > 16384) {
      throw const FormatException('TRUSTTUNNEL_DEEPLINK_INVALID');
    }
    final fields = <int, List<Uint8List>>{};
    var pos = 0;
    while (pos < bytes.length) {
      final index = [pos];
      final tag = _varint(bytes, index);
      final len = _varint(bytes, index);
      if (len > bytes.length - index[0]) {
        throw const FormatException('TRUSTTUNNEL_TLV_INVALID');
      }
      fields.putIfAbsent(tag, () => []).add(
          Uint8List.sublistView(bytes, index[0], index[0] + len));
      pos = index[0] + len;
    }
    Uint8List? raw(int tag) => fields[tag]?.last;
    String read(int tag) {
      try {
        return utf8.decode(raw(tag) ?? Uint8List(0), allowMalformed: false);
      } catch (_) {
        throw const FormatException('TRUSTTUNNEL_TLV_INVALID');
      }
    }
    int number(int tag, int fallback) {
      final value = raw(tag);
      if (value == null) return fallback;
      final idx = [0];
      final n = _varint(value, idx);
      if (idx[0] != value.length) {
        throw const FormatException('TRUSTTUNNEL_TLV_INVALID');
      }
      return n;
    }
    if (number(0, 0) > 1) {
      throw const FormatException('TRUSTTUNNEL_DEEPLINK_VERSION_UNSUPPORTED');
    }
    final hostname = read(1), username = read(5), password = read(6);
    if (hostname.isEmpty || hostname.length > 253 ||
        username.isEmpty || password.isEmpty ||
        username.length > 512 || password.length > 512 ||
        hostname.contains(RegExp(r'[\s@"\\/]'))) {
      throw const FormatException('TRUSTTUNNEL_IDENTITY_INVALID');
    }
    final addresses = fields[2];
    if (addresses == null || addresses.isEmpty || addresses.length > 8) {
      throw const FormatException('TRUSTTUNNEL_ENDPOINT_INVALID');
    }
    final address = utf8.decode(addresses.first, allowMalformed: false);
    final parsed = Uri.tryParse('tcp://' + address);
    if (parsed == null || parsed.host.isEmpty || parsed.port < 1 ||
        parsed.port > 65535 || address.contains('@') ||
        address.contains('/') || address.contains('?')) {
      throw const FormatException('TRUSTTUNNEL_ENDPOINT_INVALID');
    }
    final version = number(9, 1);
    if (version != 1 && version != 2) {
      throw const FormatException('TRUSTTUNNEL_PROTOCOL_INVALID');
    }
    final verification = raw(7);
    if (verification != null && 
        (verification.length != 1 || verification[0] != 0)) {
      throw const FormatException('TRUSTTUNNEL_CERT_VERIFICATION_DISABLED');
    }
    final clientRandom = read(11);
    if (clientRandom.isNotEmpty &&
        !RegExp(r'^[a-fA-F0-9]+(?:/[a-fA-F0-9]+)?$')
            .hasMatch(clientRandom)) {
      throw const FormatException('TRUSTTUNNEL_CLIENT_RANDOM_INVALID');
    }
    final antiDpi = raw(10);
    if (antiDpi != null && 
        (antiDpi.length != 1 || antiDpi[0] > 1)) {
      throw const FormatException('TRUSTTUNNEL_TLV_INVALID');
    }
    final customSni = read(3);
    return TrustTunnelClientProfile._(hostname, address, username, password,
        raw(8) == null ? '' : _pem(raw(8)!),
        version == 2 ? 'http3' : 'http2',
        clientRandom, antiDpi?.first == 1,
        customSni.isEmpty ? null : customSni);
  }

  Future<String> resolveEndpointIPv4({
    Future<List<InternetAddress>> Function(String)? lookup,
  }) async {
    final host = Uri.parse('tcp://' + address).host;
    final literal = InternetAddress.tryParse(host);
    if (literal != null) {
      return XrayEndpointRoute.requirePublicIPv4(literal.address);
    }
    try {
      final values = await (lookup == null
          ? InternetAddress.lookup(host, type: InternetAddressType.IPv4)
          : lookup(host)).timeout(const Duration(seconds: 6));
      for (final value in values) {
        try {
          return XrayEndpointRoute.requirePublicIPv4(value.address);
        } on FormatException {
          // Never bypass TUN for private/reserved DNS answers.
        }
      }
    } catch (_) {
      throw const FormatException('TRUSTTUNNEL_ENDPOINT_DNS_UNAVAILABLE');
    }
    throw const FormatException('TRUSTTUNNEL_ENDPOINT_DNS_UNAVAILABLE');
  }

  String privateSocksToml(String pinnedIPv4, int socksPort) {
    final ip = XrayEndpointRoute.requirePublicIPv4(pinnedIPv4);
    if (socksPort < 1025 || socksPort > 65535) {
      throw const FormatException('TRUSTTUNNEL_LOCAL_PORT_INVALID');
    }
    final port = Uri.parse('tcp://' + address).port;
    String q(String v) => jsonEncode(v);
    final remote = (customSni == null || customSni!.isEmpty)
        ? hostname : (customSni! + '|' + hostname);
    return [
      'loglevel = "info"', 'vpn_mode = "general"',
      'killswitch_enabled = true', '[endpoint]',
      'hostname = ' + q(remote),
      'addresses = [' + q(ip + ':' + port.toString()) + ']',
      'username = ' + q(username),
      'password = ' + q(password),
      'has_ipv6 = false',
      'upstream_protocol = ' + q(upstream),
      'skip_verification = false',
      'client_random = ' + q(clientRandom),
      'anti_dpi = ' + antiDpi.toString(),
      if (certificatePem.isNotEmpty) 'certificate = ' + q(certificatePem),
      '[listener.socks]',
      'address = ' + q('127.0.0.1:' + socksPort.toString()),
      ''
    ].join('\n');
  }
}
