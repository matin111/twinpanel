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
          // Bootstrap ONLY the proxy server's domain via the local resolver.
          // Sending its own hostname lookup through 'proxy' is circular:
          // no outbound connection exists until its endpoint is resolved.
          {'type': 'local', 'tag': 'dns-bootstrap'},
          // Ordinary in-tunnel DNS continues to use the selected proxy.
          {'type': 'udp', 'tag': 'dns-remote', 'server': '1.1.1.1',
           'server_port': 53, 'detour': 'proxy'},
        ],
        'final': 'dns-remote',
        // sing-box 1.14: cache repeated DNS answers and update stale
        // entries in the background. DNS still travels through the proxy.
        'cache_capacity': 4096,
        'optimistic': true,
      },
      'inbounds': [
        {
          'type': 'tun',
          'tag': 'twinconnect-tun',
          'interface_name': 'TwinConnectSB',
          'address': ['172.19.0.1/30', 'fdfe:dcba:9876::1/126'],
          'mtu': 1400,
          'auto_route': true,
          'strict_route': true,
          'dns_mode': 'hijack',
        },
      ],
      'outbounds': [serverOutbound],
      'route': {
        'auto_detect_interface': true,
        // Resolve outbound server hostnames BEFORE creating a proxy session.
        // The regular DNS final remains protected by the proxy.
        'default_domain_resolver': 'dns-bootstrap',
        'final': 'proxy',
        'rules': [
          {'action': 'sniff'},
        ],
      },
    };
  }
}
