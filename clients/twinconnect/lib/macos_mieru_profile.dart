import 'dart:convert';

import 'mieru_client_profile.dart';

/// Offline-only macOS Mieru profile preparation.
///
/// Mieru is an independent protocol core, NOT a sing-box outbound. This
/// adapter never starts a process, installs a PacketTunnel, or claims an
/// authenticated connection. The eventual signed macOS extension must
/// own the bundled Mieru core and bridge its loopback SOCKS to packetFlow.
class MacMieruProfile {
  const MacMieruProfile._();

  static Map<String, dynamic> compose({
    required Map<String, dynamic> item,
    required String pinnedEndpointIpv4,
    required int socks5Port,
    required int rpcPort,
    required int httpProxyPort,
  }) {
    final parsed = MieruClientProfile.fromItem(item);
    final runtime = parsed.runtimeConfig(
      socks5Port: socks5Port,
      rpcPort: rpcPort,
      httpProxyPort: httpProxyPort,
      resolvedEndpointIpv4: pinnedEndpointIpv4,
    );
    // The validated runtime must never expose its local proxies to LAN.
    if (runtime['socks5ListenLAN'] != false ||
        runtime['httpProxyListenLAN'] != false ||
        runtime['loggingLevel'] != 'ERROR') {
      throw const FormatException('MAC_MIERU_UNSAFE_LOCAL_PROXY');
    }
    return runtime;
  }

  static String encode({
    required Map<String, dynamic> item,
    required String pinnedEndpointIpv4,
    required int socks5Port,
    required int rpcPort,
    required int httpProxyPort,
  }) => jsonEncode(compose(
        item: item,
        pinnedEndpointIpv4: pinnedEndpointIpv4,
        socks5Port: socks5Port,
        rpcPort: rpcPort,
        httpProxyPort: httpProxyPort,
      ));
}
