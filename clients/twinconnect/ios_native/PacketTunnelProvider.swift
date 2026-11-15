import Foundation
import NetworkExtension

/// Packet Tunnel target source for the future signed iOS extension.
///
/// This source is NOT yet linked into Runner: Xcode must create a separate
/// app-extension target, enable Network Extensions for its App ID, embed the
/// target in Runner, and link a real packet-processing transport (WireGuard,
/// sing-box, etc.). The provider deliberately refuses to start while no
/// transport exists, instead of configuring a fake TUN or leaking packets.
final class PacketTunnelProvider: NEPacketTunnelProvider {
    private let integrationError = NSError(
        domain: "com.twinpanel.twinconnect.ios",
        code: 1001,
        userInfo: [NSLocalizedDescriptionKey:
            "PACKET_TUNNEL_ENGINE_NOT_INSTALLED"])

    override func startTunnel(
        options: [String: NSObject]?,
        completionHandler: @escaping (Error?) -> Void
    ) {
        completionHandler(integrationError)
    }

    override func stopTunnel(
        with reason: NEProviderStopReason,
        completionHandler: @escaping () -> Void
    ) {
        completionHandler()
    }
}
