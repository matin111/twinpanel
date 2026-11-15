import Foundation
import NetworkExtension

/// macOS packet tunnel entry point. A real protocol backend must be linked
/// before an active tunnel can be established. Never create dummy routes.
final class PacketTunnelProvider: NEPacketTunnelProvider {
    private func unavailable(_ reason: String) -> NSError {
        NSError(domain: "com.twinpanel.twinconnect.mac",
                code: 1001,
                userInfo: [NSLocalizedDescriptionKey: reason])
    }

    override func startTunnel(options: [String: NSObject]?,
                              completionHandler: @escaping (Error?) -> Void) {
        guard let configuration = protocolConfiguration as? NETunnelProviderProtocol,
              let protocolCode = configuration.providerConfiguration?["protocol"] as? String,
              !protocolCode.isEmpty else {
            completionHandler(unavailable("MACOS_PROFILE_PROTOCOL_MISSING"))
            return
        }
        // WireGuard requires WireGuardKit and wireguard-go, Xray and
        // sing-box require local TUN-capable engines, and OpenVPN needs
        // its own integrated engine. None are linked to this target yet.
        // Never mark a VPN connected solely because the extension launched.
        completionHandler(unavailable("MACOS_PROTOCOL_ENGINE_NOT_LINKED_\(protocolCode)"))
    }

    override func stopTunnel(with reason: NEProviderStopReason,
                             completionHandler: @escaping () -> Void) {
        completionHandler()
    }
}
