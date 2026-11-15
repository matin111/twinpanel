import 'dart:convert';
import 'dart:io';

/// Strictly validates an entitled TwinPanel AmneziaWG v1 tunnel profile.
/// Never downgrades obfuscation parameters to ordinary WireGuard.
class AmneziaWgProfile {
  AmneziaWgProfile._(this.config);
  final String config;

  static AmneziaWgProfile fromItem(Map<String, dynamic> item) {
    if (item['config_format'] != 'amneziawg') {
      throw const FormatException('AWG_PROFILE_FORMAT_INVALID');
    }
    final text = item['config'];
    if (text is! String || text.length < 120 || text.length > 65536 ||
        text.contains('\u0000')) {
      throw const FormatException('AWG_CONFIG_MISSING');
    }
    const ifaceFields = {
      'address', 'privatekey', 'dns', 'mtu', 'listenport',
      'jc', 'jmin', 'jmax', 's1', 's2', 's3', 's4',
      'h1', 'h2', 'h3', 'h4',
    };
    const peerFields = {
      'publickey', 'presharedkey', 'allowedips',
      'endpoint', 'persistentkeepalive',
    };
    final bySection = <String, Map<String, String>>{};
    String? section;
    var peers = 0;
    for (final source in const LineSplitter().convert(text)) {
      final line = source.trim();
      if (line.isEmpty || line.startsWith('#') || line.startsWith(';')) {
        continue;
      }
      if (line.startsWith('[') && line.endsWith(']')) {
        final header = line.toLowerCase();
        if (header == '[interface]' && section == null) {
          section = header;
        } else if (header == '[peer]' && peers == 0) {
          section = header;
          peers++;
        } else {
          throw const FormatException('AWG_CONFIG_SECTION_INVALID');
        }
        bySection[header] = <String, String>{};
        continue;
      }
      final at = line.indexOf('=');
      if (at <= 0 || section == null) {
        throw const FormatException('AWG_CONFIG_KEY_INVALID');
      }
      final key = line.substring(0, at).trim().toLowerCase();
      final value = line.substring(at + 1).trim();
      if (value.isEmpty || value.contains('\r') ||
          !(section == '[interface]' ? ifaceFields : peerFields)
              .contains(key) ||
          bySection[section]!.containsKey(key)) {
        throw const FormatException('AWG_CONFIG_KEY_INVALID');
      }
      bySection[section]![key] = value;
    }
    final iface = bySection['[interface]'];
    final peer = bySection['[peer]'];
    if (iface == null || peer == null || peers != 1) {
      throw const FormatException('AWG_CONFIG_SECTION_INVALID');
    }

    bool base64Key(String? value) {
      if (value == null || value.length != 44) return false;
      try { return base64.decode(value).length == 32; } catch (_) { return false; }
    }
    if (!base64Key(iface['privatekey']) || !base64Key(peer['publickey']) ||
        (peer['presharedkey'] != null &&
         !base64Key(peer['presharedkey']))) {
      throw const FormatException('AWG_KEY_INVALID');
    }
    final local = iface['address'];
    final dns = iface['dns'];
    final allowed = peer['allowedips'];
    final endpoint = peer['endpoint'];
    if (local == null || !local.split(',').any((a) =>
        a.trim().contains('/') &&
        InternetAddress.tryParse(a.trim().split('/').first)?.type ==
            InternetAddressType.IPv4) ||
        dns == null || dns.isEmpty ||
        !dns.split(',').every((d) =>
            InternetAddress.tryParse(d.trim()) != null) ||
        allowed == null ||
        !allowed.split(',').map((s) => s.trim()).contains('0.0.0.0/0') ||
        !allowed.split(',').map((s) => s.trim()).contains('::/0') ||
        endpoint == null || !endpoint.contains(':') ||
        endpoint.contains(' ') || endpoint.contains('@')) {
      throw const FormatException('AWG_NETWORK_CONFIG_INVALID');
    }
    final portText = endpoint.substring(endpoint.lastIndexOf(':') + 1);
    final port = int.tryParse(portText);
    if (port == null || port < 1 || port > 65535) {
      throw const FormatException('AWG_ENDPOINT_INVALID');
    }
    // Do not allow silently removing or rewriting the essential obfuscation
    // fields. Their exact values are part of the server protocol contract.
    for (final name in ['jc','jmin','jmax','s1','s2','h1','h2','h3','h4']) {
      if (iface[name] == null) {
        throw const FormatException('AWG_OBFUSCATION_MISSING');
      }
    }
    int number(String key, int max) {
      final value = int.tryParse(iface[key]!);
      if (value == null || value < 0 || value > max) {
        throw const FormatException('AWG_OBFUSCATION_INVALID');
      }
      return value;
    }
    final jc = number('jc', 65535);
    final jmin = number('jmin', 65535);
    final jmax = number('jmax', 65535);
    if (jmin > jmax || (jc > 0 && jmax == 0)) {
      throw const FormatException('AWG_OBFUSCATION_INVALID');
    }
    for (final key in ['s1','s2']) { number(key, 65535); }
    for (final key in ['h1','h2','h3','h4']) { number(key, 4294967295); }
    final magic = ['h1','h2','h3','h4'].map((k) => iface[k]!).toSet();
    if (magic.length != 4) {
      throw const FormatException('AWG_OBFUSCATION_INVALID');
    }
    return AmneziaWgProfile._(text);
  }
}
