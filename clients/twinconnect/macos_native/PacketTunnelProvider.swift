import Foundation
import NetworkExtension

/// Native packet-tunnel extension. A tunnel is only started by a linked,
/// functioning protocol backend. All unsupported protocols fail closed.
final class PacketTunnelProvider: NEPacketTunnelProvider {
    private var wireGuard: TwinConnectMacWireGuardEngine?
    #if canImport(Libbox)
    private var libbox: TwinConnectMacLibboxEngine?
    #endif

    private func unavailable(_ reason: String) -> NSError {
        NSError(domain: "com.twinpanel.twinconnect.mac", code: 1001,
                userInfo: [NSLocalizedDescriptionKey: reason])
    }

    override func startTunnel(options: [String: NSObject]?,
                              completionHandler: @escaping (Error?) -> Void) {
        guard let configuration = protocolConfiguration as? NETunnelProviderProtocol,
              let code = configuration.providerConfiguration?["protocol"] as? String else {
            completionHandler(unavailable("MACOS_PROFILE_PROTOCOL_MISSING"))
            return
        }

        switch code {
        case "wireguard":
            let engine = TwinConnectMacWireGuardEngine(provider: self)
            wireGuard = engine
            engine.start { [weak self] error in
                if error != nil { self?.wireGuard = nil }
                completionHandler(error)
            }
        case "hysteria2", "tuic", "anytls", "naive":
            #if canImport(Libbox)
            let engine = TwinConnectMacLibboxEngine(tunnel: self)
            libbox = engine
            engine.start { [weak self] error in
                if error != nil { self?.libbox = nil }
                completionHandler(error)
            }
            #else
            completionHandler(unavailable("MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING"))
            #endif
        default:
            // OpenVPN, Cisco and Xray require separate native backends.
            // Never claim a successful connection without one.
            completionHandler(unavailable("MACOS_PROTOCOL_ENGINE_NOT_LINKED_\(code)"))
        }
    }

    override func stopTunnel(with reason: NEProviderStopReason,
                             completionHandler: @escaping () -> Void) {
        if let engine = wireGuard {
            engine.stop { [weak self] in
                self?.wireGuard = nil
                completionHandler()
            }
            return
        }
        #if canImport(Libbox)
        if let engine = libbox {
            engine.stop { [weak self] in
                self?.libbox = nil
                completionHandler()
            }
            return
        }
        #endif
        completionHandler()
    }
}
