import Foundation
import NetworkExtension

/// macOS full-tunnel routing policy for a future in-process Libbox adapter.
///
/// No routes or DNS are applied until a real PlatformInterface/packetFlow
/// transport is initialized and serving. Creating settings is only a preflight.
/// The installed signed extension must make this policy effective via
/// setTunnelNetworkSettings after the native transport is ready.
enum TwinConnectMacTunnelPolicy {
    static func hysteria2Settings() -> NEPacketTunnelNetworkSettings {
        let settings = NEPacketTunnelNetworkSettings(
            tunnelRemoteAddress: "127.0.0.1")
        settings.mtu = NSNumber(value: 1400)

        let ipv4 = NEIPv4Settings(
            addresses: ["172.19.0.1"], subnetMasks: ["255.255.255.252"])
        ipv4.includedRoutes = [NEIPv4Route.default()]
        ipv4.excludedRoutes = []
        settings.ipv4Settings = ipv4

        // Keep IPv6 inside the tunnel; Libbox's initial Hysteria2 routing
        // rejects IPv6 until forwarding and no-leak tests are complete.
        let ipv6 = NEIPv6Settings(
            addresses: ["fdfe:dcba:9876::1"],
            networkPrefixLengths: [NSNumber(value: 126)])
        ipv6.includedRoutes = [NEIPv6Route.default()]
        ipv6.excludedRoutes = []
        settings.ipv6Settings = ipv6

        // System DNS traffic must go through the tunnel, where sing-box
        // hijacks DNS and sends DNS-over-HTTPS via the selected proxy.
        let dns = NEDNSSettings(servers: ["1.1.1.1", "1.0.0.1"])
        dns.matchDomains = [""]
        dns.matchDomainsNoSearch = true
        settings.dnsSettings = dns
        return settings
    }
}
