import 'dart:convert';

/// Offline Libbox TUN relay configuration for a separately authenticated
/// Mieru core running INSIDE the same signed macOS PacketTunnel extension.
///
/// This does not start Mieru, validate a remote handshake, create a tunnel,
/// or allow an independent host-side SOCKS process. In particular, do not
/// mark Mieru as an active protocol until the extension owns Mieru lifecycle,
/// network settings, loopback relay and shutdown atomically.
class MacMieruTunRelay {
  const MacMieruTunRelay._();

  static Map<String, dynamic> compose({
    required int localSocksPort,
    required bool coreOwnedByPacketTunnel,
    required bool endpointPinnedOutsideTunnel,
  }) {
    if (!coreOwnedByPacketTunnel || !endpointPinnedOutsideTunnel) {
      throw const FormatException('MAC_MIERU_TUN_RELAY_PRECONDITION_MISSING');
    }
    if (localSocksPort < 1025 || localSocksPort > 65535) {
      throw const FormatException('MAC_MIERU_TUN_RELAY_PORT_INVALID');
    }
    return <String, dynamic>{
      'log': <String, dynamic>{'level': 'error'},
      'dns': <String, dynamic>{
        'servers': [
          {'type': 'local', 'tag': 'dns-bootstrap'},
          {
            'type': 'https',
            'tag': 'dns-remote',
            'server': '1.1.1.1',
            'server_port': 443,
            'path': '/dns-query',
            'tls': <String, dynamic>{
              'enabled': true,
              'server_name': 'one.one.one.one',
            },
            'detour': 'proxy',
          },
        ],
        'final': 'dns-remote',
        'strategy': 'ipv4_only',
      },
      'inbounds': [
        {
          'type': 'tun',
          'tag': 'twinconnect-macos-tun',
          'address': ['172.19.0.1/30', 'fdfe:dcba:9876::1/126'],
          'mtu': 1400,
          'auto_route': true,
          'strict_route': true,
          'dns_mode': 'hijack',
        },
      ],
      'outbounds': [
        {
          'type': 'socks',
          'tag': 'proxy',
          'server': '127.0.0.1',
          'server_port': localSocksPort,
          'version': '5',
          'network': 'tcp',
        },
      ],
      'route': {
        'auto_detect_interface': true,
        'default_domain_resolver': 'dns-bootstrap',
        'final': 'proxy',
        'rules': [
          {'port': 53, 'action': 'hijack-dns'},
          {'ip_version': 6, 'action': 'reject'},
        ],
      },
    };
  }

  static String encode({
    required int localSocksPort,
    required bool coreOwnedByPacketTunnel,
    required bool endpointPinnedOutsideTunnel,
  }) => jsonEncode(compose(
        localSocksPort: localSocksPort,
        coreOwnedByPacketTunnel: coreOwnedByPacketTunnel,
        endpointPinnedOutsideTunnel: endpointPinnedOutsideTunnel,
      ));
}
