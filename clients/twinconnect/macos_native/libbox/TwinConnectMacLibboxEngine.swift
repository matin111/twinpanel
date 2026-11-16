import Foundation
import NetworkExtension
import Security

#if canImport(Libbox)
import Libbox

/// In-process Hysteria2 engine owned by the PacketTunnel extension.
/// The host NEVER passes credentials through providerConfiguration.
/// A signed shared-Keychain persistent reference is the only entry point.
final class TwinConnectMacLibboxEngine {
    private weak var tunnel: PacketTunnelProvider?
    private let platform: TwinConnectMacLibboxPlatform
    private let workQueue = DispatchQueue(
        label: "com.twinpanel.twinconnect.macos.libbox")
    private var server: LibboxCommandServer?
    private var started = false

    init(tunnel: PacketTunnelProvider) {
        self.tunnel = tunnel
        platform = TwinConnectMacLibboxPlatform(tunnel: tunnel)
    }

    private static func failure(_ reason: String) -> NSError {
        NSError(domain: "com.twinpanel.twinconnect.libbox", code: 2201,
                userInfo: [NSLocalizedDescriptionKey: reason])
    }

    private static func readProfile(_ reference: Data) -> String? {
        let query: [CFString: Any] = [
            kSecValuePersistentRef: reference,
            kSecReturnData: kCFBooleanTrue as Any,
            kSecMatchLimit: kSecMatchLimitOne
        ]
        var value: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &value) == errSecSuccess,
              let data = value as? Data,
              (64...131072).contains(data.count) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Prevent a compromised or stale saved profile from injecting bypass
    /// routes, alternate protocols, or TLS verification downgrades.
    private static func profileIsAllowed(_ config: String) -> Bool {
        guard let data = config.data(using: .utf8),
              let json = (try? JSONSerialization.jsonObject(with: data))
                  as? [String: Any],
              let outbounds = json["outbounds"] as? [[String: Any]],
              outbounds.count == 1,
              let outbound = outbounds.first,
              let protocolCode = outbound["type"] as? String,
              ["hysteria2", "tuic", "anytls", "naive"].contains(protocolCode),
              (protocolCode != "tuic" || (
                (outbound["uuid"] as? String).map {
                    $0.range(of: "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", options: .regularExpression) != nil
                } == true && outbound["zero_rtt_handshake"] as? Bool == false
              )),
              (protocolCode != "naive" || (
                (outbound["username"] as? String).map {
                    !$0.isEmpty && $0.count <= 1024
                } == true &&
                outbound["insecure_concurrency"] as? Int == 0 &&
                (outbound["quic"] == nil || outbound["quic"] as? Bool == true) &&
                (outbound["udp_over_tcp"] == nil ||
                    outbound["udp_over_tcp"] as? Bool == true) &&
                outbound["extra_headers"] == nil
              )),
              outbound["tag"] as? String == "proxy",
              let secret = outbound["password"] as? String,
              !secret.isEmpty,
              let endpoint = outbound["server"] as? String,
              !endpoint.isEmpty,
              let port = outbound["server_port"] as? Int,
              (1...65535).contains(port),
              let tls = outbound["tls"] as? [String: Any],
              tls["enabled"] as? Bool == true,
              tls["insecure"] == nil,
              tls["disable_sni"] == nil,
              let inbounds = json["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds.first?["type"] as? String == "tun",
              inbounds.first?["auto_route"] as? Bool == true,
              inbounds.first?["strict_route"] as? Bool == true,
              let route = json["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let dns = json["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote" else { return false }
        return true
    }

    func start(completion: @escaping (Error?) -> Void) {
        workQueue.async { [weak self] in
            guard let self, let tunnel = self.tunnel,
                  let settings = tunnel.protocolConfiguration
                    as? NETunnelProviderProtocol,
                  let code = settings.providerConfiguration?["protocol"] as? String,
                  ["hysteria2", "tuic", "anytls", "naive"].contains(code),
                  let reference = settings.passwordReference,
                  let config = Self.readProfile(reference),
                  Self.profileIsAllowed(config),
              let json = (try? JSONSerialization.jsonObject(
                    with: Data(config.utf8))) as? [String: Any],
              let outbounds = json["outbounds"] as? [[String: Any]],
              outbounds.first?["type"] as? String == code else {
                completion(Self.failure("MACOS_LIBBOX_KEYCHAIN_PROFILE_MISSING"))
                return
            }

            do {
                let base = FileManager.default.temporaryDirectory
                    .appendingPathComponent("TwinConnect-Libbox", isDirectory: true)
                try FileManager.default.createDirectory(
                    at: base, withIntermediateDirectories: true)
                let working = base.appendingPathComponent("Working")
                let temporary = base.appendingPathComponent("Temporary")
                try FileManager.default.createDirectory(
                    at: working, withIntermediateDirectories: true)
                try FileManager.default.createDirectory(
                    at: temporary, withIntermediateDirectories: true)

                let setup = LibboxSetupOptions()
                setup.basePath = base.path
                setup.workingPath = working.path
                setup.tempPath = temporary.path
                setup.debug = false
                var setupError: NSError?
                LibboxSetup(setup, &setupError)
                if let setupError { throw setupError }

                var creationError: NSError?
                guard let server = LibboxNewCommandServer(
                    self.platform, self.platform, &creationError) else {
                    throw creationError ??
                        Self.failure("MACOS_LIBBOX_COMMAND_SERVER_UNAVAILABLE")
                }
                self.server = server
                try server.start()
                try server.startOrReloadService(
                    config, options: LibboxOverrideOptions())
                self.started = true

                // Successful startup only establishes OS/Libbox startup;
                // a real peer handshake and internet egress require
                // independent runtime verification on a signed Mac.
                completion(nil)
            } catch {
                self.close()
                completion(error)
            }
        }
    }

    func stop(completion: @escaping () -> Void) {
        workQueue.async { [weak self] in
            self?.close()
            completion()
        }
    }

    private func close() {
        if started { try? server?.closeService() }
        server?.close()
        server = nil
        started = false
        platform.reset()
    }
}
#endif
