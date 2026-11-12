import 'dart:io';

import 'singbox_profile_validator.dart';
import 'shadowtls_chain.dart';
import 'xray_endpoint_route.dart';

/// Prepares an isolated Windows TUN config IN MEMORY.
/// Only a privileged and verified native runner may apply it. This function
/// does not start or verify a VPN connection.
/// Never log or persist the returned object because it contains credentials.
class SingBoxWindowsConfig {
  const SingBoxWindowsConfig._();

  static Map<String, dynamic> compose({
    required String protocol,
    required Map<String, dynamic> item,
    String? resolvedServer,
    int? telemetryPort,
    String? telemetrySecret,
    int? xraySocksPort,
    String? xrayEndpointIPv4,
    int? sudokuSocksPort,
    String? sudokuEndpointIPv4,
    int? mieruSocksPort,
    String? mieruEndpointIPv4,
  }) {
    if ([xraySocksPort, sudokuSocksPort, mieruSocksPort]
        .where((port) => port != null).length > 1) {
      throw const FormatException('MULTIPLE_LOCAL_PROXY_UPSTREAMS');
    }
    if (sudokuSocksPort != null &&
        (protocol != 'sudoku' || sudokuSocksPort < 1024 ||
         sudokuSocksPort > 65535 || resolvedServer != null)) {
      throw const FormatException('SUDOKU_SOCKS_BRIDGE_INVALID');
    }
    if ((sudokuSocksPort == null) != (sudokuEndpointIPv4 == null)) {
      throw const FormatException('SUDOKU_ENDPOINT_ROUTE_MISSING');
    }
    if (mieruSocksPort != null &&
        (protocol != 'mieru' || mieruSocksPort < 1024 ||
         mieruSocksPort > 65535 || resolvedServer != null)) {
      throw const FormatException('MIERU_SOCKS_BRIDGE_INVALID');
    }
    if ((mieruSocksPort == null) != (mieruEndpointIPv4 == null)) {
      throw const FormatException('MIERU_ENDPOINT_ROUTE_MISSING');
    }
    final activeSocksPort = xraySocksPort ?? sudokuSocksPort ?? mieruSocksPort;
    // An app-owned, loopback-only Xray-core SOCKS bridge is the sole
    // supported external outbound. Never accept an arbitrary proxy host.
    if (xraySocksPort != null &&
        (protocol != 'v2ray' || xraySocksPort < 1024 ||
         xraySocksPort > 65535 || resolvedServer != null)) {
      throw const FormatException('XRAY_SOCKS_BRIDGE_INVALID');
    }
    if ((xraySocksPort == null) != (xrayEndpointIPv4 == null)) {
      throw const FormatException('XRAY_ENDPOINT_ROUTE_MISSING');
    }
    // A narrow /32 exception only for the exact preverified VLESS server.
    // Never make a general LAN/IPv4 exception or weaken strict_route.
    final pinnedEndpoint = xrayEndpointIPv4 ?? sudokuEndpointIPv4 ??
        mieruEndpointIPv4;
    final endpointRoute = pinnedEndpoint == null
        ? null : XrayEndpointRoute.requirePublicIPv4(pinnedEndpoint);
    final chain = activeSocksPort == null && protocol == 'shadowtls'
        ? ShadowTlsChain.fromItem(item) : null;
    final outbound = activeSocksPort == null
        ? chain == null
            ? SingBoxProfileValidator.validateOutbound(
                protocolCode: protocol, item: item)
            : chain.transport
        : <String, dynamic>{
            'type': 'socks',
            'server': '127.0.0.1',
            'server_port': activeSocksPort,
            'version': '5',
          };
    final serverOutbound = {...outbound, 'tag': 'proxy'};
    // Resolve the endpoint before installing TUN routes to avoid a DNS
    // bootstrap loop. Preserve the original TLS identity when dialing an IP.
    if (resolvedServer != null) {
      if (InternetAddress.tryParse(resolvedServer) == null) {
        throw const FormatException('SINGBOX_BOOTSTRAP_IP_INVALID');
      }
      final originalServer = outbound['server'] as String;
      if (InternetAddress.tryParse(originalServer) == null &&
          serverOutbound['tls'] is Map) {
        final tls = Map<String, dynamic>.from(serverOutbound['tls'] as Map);
        final name = tls['server_name'];
        if (name == null || (name is String && name.isEmpty)) {
          tls['server_name'] = originalServer;
        }
        serverOutbound['tls'] = tls;
      }
      serverOutbound['server'] = resolvedServer;
    }
    if ((telemetryPort == null) != (telemetrySecret == null) ||
        (telemetryPort != null &&
         (telemetryPort < 1024 || telemetryPort > 65535 ||
          telemetrySecret == null || telemetrySecret.length < 32))) {
      throw const FormatException('SINGBOX_TELEMETRY_INVALID');
    }
    return {
      if (telemetryPort != null)
        'experimental': {
          'clash_api': {
            'external_controller': '127.0.0.1:$telemetryPort',
            'secret': telemetrySecret,
          },
        },
      'log': {'level': 'error', 'timestamp': true},
      'dns': {
        'servers': [
          // Bootstrap ONLY the proxy server's domain via the local resolver.
          // Sending its own hostname lookup through 'proxy' is circular:
          // no outbound connection exists until its endpoint is resolved.
          {'type': 'local', 'tag': 'dns-bootstrap'},
          // Ordinary in-tunnel DNS continues to use the selected proxy.
          // Use HTTPS/TCP for protected DNS: not all modern proxies
          // implement UDP relay (notably NaiveProxy).
          {'type': 'https', 'tag': 'dns-remote', 'server': '1.1.1.1',
           'server_port': 443, 'path': '/dns-query',
           'tls': {'enabled': true, 'server_name': 'one.one.one.one'},
           'headers': {'Host': 'one.one.one.one'},
           'detour': 'proxy'},
        ],
        'final': 'dns-remote',
        // Diagnostic IPv4-only mode: do not return AAAA targets while
        // the modern TUN's IPv6 HTTPS route is failing on Windows.
        'strategy': 'ipv4_only',
        // sing-box 1.14: cache repeated DNS answers and update stale
        // entries in the background. DNS still travels through the proxy.
        'cache_capacity': 4096,
        'optimistic': false,
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
          if (endpointRoute != null)
            'route_exclude_address': ['$endpointRoute/32'],
          'dns_mode': 'hijack',
        },
      ],
      'outbounds': chain == null
          ? [serverOutbound]
          : chain.outbounds(resolvedServer: resolvedServer),
      'route': {
        'auto_detect_interface': true,
        // Resolve outbound server hostnames BEFORE creating a proxy session.
        // The regular DNS final remains protected by the proxy.
        'default_domain_resolver': 'dns-bootstrap',
        'final': 'proxy',
        'rules': [
          {'port': 53, 'action': 'hijack-dns'},
          // Fail closed for literal IPv6 targets; never bypass the TUN via
          // the physical Wi-Fi route while testing IPv4 compatibility.
          {'ip_version': 6, 'action': 'reject'},
          {'action': 'sniff'},
        ],
      },
    };
  }
}
