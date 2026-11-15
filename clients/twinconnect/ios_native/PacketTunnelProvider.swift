import Foundation
import NetworkExtension

/// Signed device extension: selects the *local* protocol transport without
/// trusting panel claims of native support. Never starts a tunnel with no engine.
final class PacketTunnelProvider: NEPacketTunnelProvider {
    private var wireGuard: TwinConnectWireGuardEngine?

    private func unavailable(_ reason: String) -> NSError {
        NSError(domain: "com.twinpanel.twinconnect.ios", code: 1001,
                userInfo: [NSLocalizedDescriptionKey: reason])
    }

    override func startTunnel(
        options: [String: NSObject]?,
        completionHandler: @escaping (Error?) -> Void
    ) {
        guard let configuration = protocolConfiguration as? NETunnelProviderProtocol,
              let code = configuration.providerConfiguration?["protocol"] as? String else {
            completionHandler(unavailable("MISSING_PROTOCOL_SELECTION"))
            return
        }
        switch code {
        case "wireguard":
            // A missing linked WireGuardKit fails immediately without
            // installing fake tunnel routes or accepting unprotected traffic.
            let engine = TwinConnectWireGuardEngine(provider: self)
            wireGuard = engine
            engine.start { [weak self] error in
                if error != nil { self?.wireGuard = nil }
                completionHandler(error)
            }
        default:
            completionHandler(unavailable("IOS_PROTOCOL_ENGINE_NOT_INSTALLED"))
        }
    }

    override func stopTunnel(
        with reason: NEProviderStopReason,
        completionHandler: @escaping () -> Void
    ) {
        guard let engine = wireGuard else {
            completionHandler()
            return
        }
        engine.stop { [weak self] in
            self?.wireGuard = nil
            completionHandler()
        }
    }
}
