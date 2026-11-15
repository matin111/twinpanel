/// Validates the panel-issued inline .ovpn format before any native engine
/// sees it. No profile text, private key or credentials enter error messages.
class OpenVpnProfileValidator {
  static String validate(Map<String, dynamic> item) {
    final config = item['config'];
    if (config is! String || config.isEmpty || config.length > 262144) {
      throw const FormatException('OPENVPN_PROFILE_MISSING');
    }
    if (config.contains('\x00') || config.contains('\r')) {
      throw const FormatException('OPENVPN_PROFILE_INVALID');
    }
    final lines = config.split('\n');
    final directives = <String, List<String>>{};
    String? block;
    final blocks = <String, int>{};
    for (final raw in lines) {
      final line = raw.trim();
      if (line.isEmpty || line.startsWith('#') || line.startsWith(';')) {
        continue;
      }
      if (block != null) {
        if (line == '</$block>') {
          block = null;
        } else if (line.startsWith('<') || line.startsWith('</')) {
          throw const FormatException('OPENVPN_INLINE_BLOCK_INVALID');
        }
        continue;
      }
      if (line.startsWith('<')) {
        final match = RegExp(r'^<(ca|cert|key)>$').firstMatch(line);
        if (match == null) {
          throw const FormatException('OPENVPN_EXTERNAL_MATERIAL_FORBIDDEN');
        }
        block = match.group(1)!;
        blocks[block] = (blocks[block] ?? 0) + 1;
        continue;
      }
      final parts = line.split(RegExp(r'\s+'));
      final name = parts.first.toLowerCase();
      const allowed = {
        'client', 'dev', 'proto', 'remote', 'redirect-gateway',
        'tun-mtu', 'mssfix', 'resolv-retry', 'nobind', 'persist-key',
        'persist-tun', 'remote-cert-tls', 'verb', 'data-ciphers', 'auth',
      };
      if (!allowed.contains(name)) {
        throw const FormatException('OPENVPN_UNSAFE_DIRECTIVE');
      }
      directives.putIfAbsent(name, () => []).add(parts.skip(1).join(' '));
    }
    if (block != null || blocks['ca'] != 1 || blocks['cert'] != 1 ||
        blocks['key'] != 1 || directives['client']?.length != 1 ||
        directives['dev']?.singleOrNull != 'tun' ||
        directives['remote-cert-tls']?.singleOrNull != 'server' ||
        directives['remote']?.length != 1) {
      throw const FormatException('OPENVPN_PROFILE_INCOMPLETE');
    }
    final remote = directives['remote']!.single.split(RegExp(r'\s+'));
    if (remote.length != 2 ||
        !RegExp(r'^[A-Za-z0-9.-]{1,253}$').hasMatch(remote[0]) ||
        remote[0].startsWith('-') || remote[0].contains('..') ||
        int.tryParse(remote[1]) == null ||
        int.parse(remote[1]) < 1 || int.parse(remote[1]) > 65535) {
      throw const FormatException('OPENVPN_ENDPOINT_INVALID');
    }
    final proto = directives['proto']?.singleOrNull;
    if (proto != 'udp' && proto != 'tcp-client') {
      throw const FormatException('OPENVPN_TRANSPORT_UNSUPPORTED');
    }
    return config;
  }
}
