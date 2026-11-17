import Foundation
import NetworkExtension
import Security

/// PacketTunnel lifecycle owner for the separate Mieru and Libbox engines.
/// Never read account secrets from providerConfiguration or launch a CLI.
/// A signed preview is still unusable until the real endpoint bypass and
/// packetFlow relay have been installed and verified on an entitled Mac.
final class TwinConnectMacMieruTunnelEngine {
    private weak var tunnel: NEPacketTunnelProvider?
    private let workQueue = DispatchQueue(
        label: "com.twinpanel.twinconnect.macos.mieru")
    private var core: TwinConnectMacMieruCore?

    init(tunnel: NEPacketTunnelProvider) { self.tunnel = tunnel }

    private static func failure(_ reason: String) -> NSError {
        NSError(domain: "com.twinpanel.twinconnect.mieru", code: 2901,
                userInfo: [NSLocalizedDescriptionKey: reason])
    }

    /// Fetch only a shared Keychain persistent reference. Credentials must
    /// not appear in NETunnelProviderProtocol.providerConfiguration.
    private static func readBundle(_ reference: Data) -> [String: Any]? {
        let query: [CFString: Any] = [
            kSecValuePersistentRef: reference,
            kSecReturnData: kCFBooleanTrue as Any,
            kSecMatchLimit: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) ==
                errSecSuccess,
              let raw = result as? Data,
              (256...131072).contains(raw.count),
              let object = (try? JSONSerialization.jsonObject(with: raw))
                    as? [String: Any],
              Set(object.keys) == Set(["core", "relay"]),
              let core = object["core"] as? [String: Any],
              let relay = object["relay"] as? [String: Any],
              core["rpcPort"] as? Int == 0,
              core["httpProxyPort"] == nil,
              core["socks5ListenLAN"] as? Bool == false,
              core["httpProxyListenLAN"] as? Bool == false,
              let socksPort = core["socks5Port"] as? Int,
              (1025...65535).contains(socksPort),
              let outbounds = relay["outbounds"] as? [[String: Any]],
              outbounds.count == 1,
              outbounds[0]["type"] as? String == "socks",
              outbounds[0]["server"] as? String == "127.0.0.1",
              outbounds[0]["server_port"] as? Int == socksPort,
              outbounds[0]["version"] as? String == "5",
              outbounds[0]["username"] == nil,
              outbounds[0]["password"] == nil,
              let inbound = relay["inbounds"] as? [[String: Any]],
              inbound.count == 1,
              inbound[0]["type"] as? String == "tun",
              inbound[0]["strict_route"] as? Bool == true,
              inbound[0]["auto_route"] as? Bool == true,
              let route = relay["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let rules = route["rules"] as? [[String: Any]],
              rules.count == 2,
              rules[0]["action"] as? String == "hijack-dns",
              rules[1]["ip_version"] as? Int == 6,
              rules[1]["action"] as? String == "reject",
              let dns = relay["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote" else {
            return nil
        }
        return object
    }

    func start(completion: @escaping (Error?) -> Void) {
        workQueue.async { [weak self] in
            guard let self, let tunnel = self.tunnel,
                  let configuration = tunnel.protocolConfiguration
                      as? NETunnelProviderProtocol,
                  configuration.providerConfiguration?["protocol"] as? String ==
                      "mieru",
                  let reference = configuration.passwordReference,
                  Self.readBundle(reference) != nil else {
                completion(Self.failure("MACOS_MIERU_KEYCHAIN_BUNDLE_INVALID"))
                return
            }

            // This is an intentional hard safety gate, NOT a mock success.
            // The next signed integration must pin the remote Mieru endpoint
            // to the physical interface before installing TUN routes.
            // Then start core, wait for loopback listener, start Libbox relay
            // and verify real egress. Never enable direct fallback routing.
            completion(Self.failure(
                "MACOS_MIERU_EGRESS_ROUTE_PIN_NOT_IMPLEMENTED"))
        }
    }

    func stop(completion: @escaping () -> Void) {
        workQueue.async { [weak self] in
            self?.core?.stop()
            self?.core = nil
            completion()
        }
    }
}
