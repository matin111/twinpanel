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
    private static func shadowTlsProfileAllowed(_ json: [String: Any]) -> Bool {
        guard let outbounds = json["outbounds"] as? [[String: Any]],
              outbounds.count == 2,
              let inner = outbounds.first, let outer = outbounds.last,
              inner["type"] as? String == "shadowsocks",
              inner["tag"] as? String == "proxy",
              inner["detour"] as? String == "shadowtls-transport",
              let method = inner["method"] as? String,
              ["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305",
               "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
               "2022-blake3-chacha20-poly1305"].contains(method),
              let innerSecret = inner["password"] as? String,
              !innerSecret.isEmpty,
              inner["server"] == nil,
              Set(inner.keys).isSubset(of: [
                "type", "tag", "detour", "method", "password"
              ]),
              outer["type"] as? String == "shadowtls",
              outer["tag"] as? String == "shadowtls-transport",
              outer["version"] as? Int == 3,
              let outerSecret = outer["password"] as? String,
              !outerSecret.isEmpty,
              let endpoint = outer["server"] as? String,
              !endpoint.isEmpty,
              let port = outer["server_port"] as? Int,
              (1...65535).contains(port),
              Set(outer.keys).isSubset(of: [
                "type", "tag", "version", "server", "server_port",
                "password", "tls"
              ]),
              let tls = outer["tls"] as? [String: Any],
              tls["enabled"] as? Bool == true,
              let sni = tls["server_name"] as? String,
              !sni.isEmpty,
              Set(tls.keys).isSubset(of: ["enabled", "server_name"]),
              let inbounds = json["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds[0]["type"] as? String == "tun",
              inbounds[0]["strict_route"] as? Bool == true,
              inbounds[0]["auto_route"] as? Bool == true,
              let route = json["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let dns = json["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote"
        else { return false }
        return true
    }

    private static func snellProfileAllowed(_ json: [String: Any]) -> Bool {
        guard let outbounds = json["outbounds"] as? [[String: Any]],
              outbounds.count == 1, let outbound = outbounds.first,
              outbound["type"] as? String == "snell",
              outbound["tag"] as? String == "proxy",
              let version = outbound["version"] as? Int,
              [4, 6].contains(version),
              let secret = outbound["psk"] as? String,
              !secret.isEmpty, secret.utf8.count <= 4096,
              (version != 6 || (12...255).contains(secret.utf8.count)),
              let endpoint = outbound["server"] as? String,
              !endpoint.isEmpty,
              let port = outbound["server_port"] as? Int,
              (1...65535).contains(port),
              Set(outbound.keys).isSubset(of: [
                  "type", "tag", "server", "server_port", "version",
                  "psk", "userkey", "reuse", "network", "obfs_mode",
                  "obfs_host", "mode"
              ]),
              (version != 4 || outbound["mode"] == nil),
              (version != 6 || (outbound["obfs_mode"] == nil &&
                   outbound["obfs_host"] == nil)),
              let inbounds = json["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds[0]["type"] as? String == "tun",
              inbounds[0]["auto_route"] as? Bool == true,
              inbounds[0]["strict_route"] as? Bool == true,
              let route = json["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let dns = json["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote" else { return false }
        return true
    }

    private static func socks5ProfileAllowed(_ json: [String: Any]) -> Bool {
        guard let outbounds = json["outbounds"] as? [[String: Any]],
              outbounds.count == 1, let outbound = outbounds.first,
              outbound["type"] as? String == "socks",
              outbound["tag"] as? String == "proxy",
              outbound["version"] as? String == "5",
              outbound["network"] as? String == "tcp",
              let username = outbound["username"] as? String,
              !username.isEmpty, username.utf8.count <= 255,
              let secret = outbound["password"] as? String,
              !secret.isEmpty, secret.utf8.count <= 255,
              let endpoint = outbound["server"] as? String,
              !endpoint.isEmpty, endpoint.count <= 255,
              !endpoint.contains("/"), !endpoint.contains(" "),
              let port = outbound["server_port"] as? Int,
              (1...65535).contains(port),
              Set(outbound.keys).isSubset(of: [
                  "type", "tag", "version", "network", "username",
                  "password", "server", "server_port"
              ]),
              let inbounds = json["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds[0]["type"] as? String == "tun",
              inbounds[0]["auto_route"] as? Bool == true,
              inbounds[0]["strict_route"] as? Bool == true,
              let route = json["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let dns = json["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote"
        else { return false }
        return true
    }

    /// Preflight only for a future in-extension Mieru process. The Libbox
    /// relay MUST NOT start before a signed, extension-owned Mieru core has
    /// authenticated and pinned its egress endpoint outside the TUN.
    /// This method is intentionally not used by start() until that bridge exists.
    private static func mieruRelayProfileAllowed(_ json: [String: Any]) -> Bool {
        guard let outbounds = json["outbounds"] as? [[String: Any]],
              outbounds.count == 1, let outbound = outbounds.first,
              Set(outbound.keys).isSubset(of: [
                  "type", "tag", "server", "server_port", "version", "network"
              ]),
              outbound["type"] as? String == "socks",
              outbound["tag"] as? String == "proxy",
              outbound["server"] as? String == "127.0.0.1",
              outbound["version"] as? String == "5",
              outbound["network"] as? String == "tcp",
              let port = outbound["server_port"] as? Int,
              (1025...65535).contains(port),
              let inbounds = json["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds[0]["type"] as? String == "tun",
              inbounds[0]["auto_route"] as? Bool == true,
              inbounds[0]["strict_route"] as? Bool == true,
              inbounds[0]["dns_mode"] as? String == "hijack",
              let route = json["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              route["default_domain_resolver"] as? String == "dns-bootstrap",
              let rules = route["rules"] as? [[String: Any]],
              rules.count == 2,
              rules[0]["port"] as? Int == 53,
              rules[0]["action"] as? String == "hijack-dns",
              rules[1]["ip_version"] as? Int == 6,
              rules[1]["action"] as? String == "reject",
              let dns = json["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote",
              let servers = dns["servers"] as? [[String: Any]],
              servers.count == 2,
              servers[0]["tag"] as? String == "dns-bootstrap",
              servers[0]["type"] as? String == "local",
              servers[1]["tag"] as? String == "dns-remote",
              servers[1]["detour"] as? String == "proxy",
              servers[1]["type"] as? String == "https"
        else { return false }
        return true
    }

    private static func profileIsAllowed(_ config: String) -> Bool {
        guard let data = config.data(using: .utf8),
              let json = (try? JSONSerialization.jsonObject(with: data))
                  as? [String: Any],
              let outbounds = json["outbounds"] as? [[String: Any]] else {
            return false
        }
        if outbounds.count == 2 {
            return shadowTlsProfileAllowed(json)
        }
        if outbounds.count == 1 && outbounds.first?["type"] as? String == "snell" {
            return snellProfileAllowed(json)
        }
        if outbounds.count == 1 && outbounds.first?["type"] as? String == "socks" {
            return socks5ProfileAllowed(json)
        }
        guard outbounds.count == 1,
              let outbound = outbounds.first,
              let protocolCode = outbound["type"] as? String,
              ["hysteria2", "tuic", "anytls", "naive", "shadowtls"].contains(protocolCode),
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
                  ["hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5"].contains(code),
                  let reference = settings.passwordReference,
                  let config = Self.readProfile(reference),
                  Self.profileIsAllowed(config),
              let json = (try? JSONSerialization.jsonObject(
                    with: Data(config.utf8))) as? [String: Any],
              let outbounds = json["outbounds"] as? [[String: Any]],
              (code == "shadowtls" ?
                  (outbounds.count == 2 &&
                   outbounds.first?["type"] as? String == "shadowsocks" &&
                   outbounds.last?["type"] as? String == "shadowtls") :
                  (outbounds.count == 1 &&
                   outbounds.first?["type"] as? String ==
                      (code == "socks5" ? "socks" : code))) else {
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
