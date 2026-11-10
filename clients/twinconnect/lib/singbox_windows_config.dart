import 'singbox_profile_validator.dart';

/// Prepares an isolated Windows TUN config IN MEMORY.
/// Only a privileged and verified native runner may apply it. This function
/// does not start or verify a VPN connection.
/// Never log or persist the returned object because it contains credentials.
class SingBoxWindowsConfig {
  const SingBoxWindowsConfig._();

  static Map<String, dynamic> compose({
    required String protocol,
    required Map<String, dynamic> item,
  }) {
    final outbound = SingBoxProfileValidator.validateOutbound(
      protocolCode: protocol, item: item);
    final serverOutbound = {...outbound, 'tag': 'proxy'};
    return {
      'log': {'level': 'error', 'timestamp': true},
      'dns': {
        'servers': [
          {'type': 'udp', 'tag': 'dns-remote', 'server': '1.1.1.1',
           'server_port': 53, 'detour': 'proxy'},
        ],
        'final': 'dns-remote',
      },
      'inbounds': [
        {
          'type': 'tun',
          'tag': 'twinconnect-tun',
          'interface_name': 'TwinConnectSB',
          'address': ['172.19.0.1/30'],
          'mtu': 1400,
          'auto_route': true,
          'strict_route': true,
          'dns_mode': 'hijack',
        },
      ],
      'outbounds': [
        serverOutbound,
        {'type': 'block', 'tag': 'block'},
      ],
      'route': {
        'auto_detect_interface': true,
        'final': 'proxy',
        'rules': [
          {'action': 'sniff'},
        ],
      },
    };
  }
}
