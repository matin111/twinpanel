import Foundation
import FlutterMacOS
import NetworkExtension
import Security

/// Host-side account scoped profile hand-off to an Apple PacketTunnel.
/// This only requests OS tunnel startup. It never reports verified egress.
enum TwinConnectMacOSLibboxControl {
    private static let bundleID = "com.twinpanel.twinconnect.PacketTunnel"
    private static let keychainService = "com.twinpanel.twinconnect.macos.libbox"

    private static func failure(_ code: String) -> FlutterError {
        FlutterError(code: code, message: code, details: nil)
    }

    private static func allowedShadowTlsConfig(_ text: String) -> Bool {
        guard (64...131072).contains(text.utf8.count),
              let data = text.data(using: .utf8),
              let raw = (try? JSONSerialization.jsonObject(with: data))
                    as? [String: Any],
              let outbounds = raw["outbounds"] as? [[String: Any]],
              outbounds.count == 2,
              let inner = outbounds.first,
              let outer = outbounds.last,
              inner["type"] as? String == "shadowsocks",
              inner["tag"] as? String == "proxy",
              inner["detour"] as? String == "shadowtls-transport",
              let method = inner["method"] as? String,
              ["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305",
               "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
               "2022-blake3-chacha20-poly1305"].contains(method),
              let innerPassword = inner["password"] as? String,
              !innerPassword.isEmpty,
              inner["server"] == nil,
              inner["server_port"] == nil,
              Set(inner.keys).isSubset(of: [
                "type", "tag", "detour", "method", "password"
              ]),
              outer["type"] as? String == "shadowtls",
              outer["tag"] as? String == "shadowtls-transport",
              outer["version"] as? Int == 3,
              let endpoint = outer["server"] as? String,
              !endpoint.isEmpty,
              let port = outer["server_port"] as? Int,
              (1...65535).contains(port),
              let outerPassword = outer["password"] as? String,
              !outerPassword.isEmpty,
              Set(outer.keys).isSubset(of: [
                "type", "tag", "version", "server", "server_port",
                "password", "tls"
              ]),
              let tls = outer["tls"] as? [String: Any],
              tls["enabled"] as? Bool == true,
              let serverName = tls["server_name"] as? String,
              !serverName.isEmpty,
              Set(tls.keys).isSubset(of: ["enabled", "server_name"]),
              let inbounds = raw["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds[0]["type"] as? String == "tun",
              inbounds[0]["auto_route"] as? Bool == true,
              inbounds[0]["strict_route"] as? Bool == true,
              inbounds[0]["dns_mode"] as? String == "hijack",
              let route = raw["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              route["default_domain_resolver"] as? String == "dns-bootstrap",
              let rules = route["rules"] as? [[String: Any]],
              rules.count == 2,
              rules[0]["port"] as? Int == 53,
              rules[0]["action"] as? String == "hijack-dns",
              rules[1]["ip_version"] as? Int == 6,
              rules[1]["action"] as? String == "reject",
              let dns = raw["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote",
              let servers = dns["servers"] as? [[String: Any]],
              servers.count == 2,
              servers[0]["tag"] as? String == "dns-bootstrap",
              servers[1]["detour"] as? String == "proxy"
        else { return false }
        return true
    }

    private static func allowedSnellConfig(_ text: String) -> Bool {
        guard (64...131072).contains(text.utf8.count),
              let data = text.data(using: .utf8),
              let raw = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let outbounds = raw["outbounds"] as? [[String: Any]],
              outbounds.count == 1,
              let outbound = outbounds.first,
              outbound["type"] as? String == "snell",
              outbound["tag"] as? String == "proxy",
              let version = outbound["version"] as? Int,
              [4, 6].contains(version),
              let psk = outbound["psk"] as? String,
              !psk.isEmpty, psk.utf8.count <= 4096,
              (version != 6 || (12...255).contains(psk.utf8.count)),
              let endpoint = outbound["server"] as? String,
              !endpoint.isEmpty, endpoint.count <= 255,
              let port = outbound["server_port"] as? Int,
              (1...65535).contains(port),
              Set(outbound.keys).isSubset(of: [
                  "type", "tag", "server", "server_port", "version",
                  "psk", "userkey", "reuse", "network", "obfs_mode",
                  "obfs_host", "mode"
              ]),
              (outbound["userkey"] == nil || (outbound["userkey"] as? String)
                  .map { $0.utf8.count <= 255 } == true),
              (outbound["reuse"] == nil || outbound["reuse"] is Bool),
              (outbound["network"] == nil ||
                  ["tcp", "udp"].contains(outbound["network"] as? String ?? "")),
              (version != 4 || (outbound["mode"] == nil &&
                  (outbound["obfs_mode"] == nil ||
                   ["none", "http"].contains(outbound["obfs_mode"] as? String ?? "")))),
              (version != 6 || (outbound["obfs_mode"] == nil &&
                  outbound["obfs_host"] == nil &&
                  (outbound["mode"] == nil ||
                   ["default", "unshaped"].contains(outbound["mode"] as? String ?? "")))),
              let inbounds = raw["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds[0]["type"] as? String == "tun",
              inbounds[0]["strict_route"] as? Bool == true,
              inbounds[0]["auto_route"] as? Bool == true,
              inbounds[0]["dns_mode"] as? String == "hijack",
              let route = raw["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let rules = route["rules"] as? [[String: Any]],
              rules.count == 2,
              rules[0]["port"] as? Int == 53,
              rules[0]["action"] as? String == "hijack-dns",
              rules[1]["ip_version"] as? Int == 6,
              rules[1]["action"] as? String == "reject",
              let dns = raw["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote",
              let servers = dns["servers"] as? [[String: Any]],
              servers.count == 2,
              servers[0]["type"] as? String == "local",
              servers[1]["detour"] as? String == "proxy"
        else { return false }
        return true
    }

    private static func allowedSocks5Config(_ text: String) -> Bool {
        guard (64...131072).contains(text.utf8.count),
              let data = text.data(using: .utf8),
              let raw = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let outbounds = raw["outbounds"] as? [[String: Any]],
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
              let inbounds = raw["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds[0]["type"] as? String == "tun",
              inbounds[0]["auto_route"] as? Bool == true,
              inbounds[0]["strict_route"] as? Bool == true,
              inbounds[0]["dns_mode"] as? String == "hijack",
              let route = raw["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              route["default_domain_resolver"] as? String == "dns-bootstrap",
              let rules = route["rules"] as? [[String: Any]],
              rules.count == 2,
              rules[0]["port"] as? Int == 53,
              rules[0]["action"] as? String == "hijack-dns",
              rules[1]["ip_version"] as? Int == 6,
              rules[1]["action"] as? String == "reject",
              let dns = raw["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote",
              let servers = dns["servers"] as? [[String: Any]],
              servers.count == 2,
              servers[0]["type"] as? String == "local",
              servers[1]["type"] as? String == "https",
              servers[1]["detour"] as? String == "proxy"
        else { return false }
        return true
    }

    private static func allowedConfig(_ text: String, protocolCode: String) -> Bool {
        if protocolCode == "socks5" { return allowedSocks5Config(text) }
        if protocolCode == "snell" { return allowedSnellConfig(text) }

        if protocolCode == "shadowtls" { return allowedShadowTlsConfig(text) }
        guard ["hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5"].contains(protocolCode) else { return false }
        guard (64...131072).contains(text.utf8.count),
              let data = text.data(using: .utf8),
              let raw = (try? JSONSerialization.jsonObject(with: data))
                    as? [String: Any],
              let outbounds = raw["outbounds"] as? [[String: Any]],
              outbounds.count == 1,
              let outbound = outbounds.first,
              outbound["type"] as? String == protocolCode,
              outbound["tag"] as? String == "proxy",
              let password = outbound["password"] as? String,
              !password.isEmpty,
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
                (outbound["quic"] == nil ||
                    outbound["quic"] as? Bool == true) &&
                (outbound["udp_over_tcp"] == nil ||
                    outbound["udp_over_tcp"] as? Bool == true) &&
                outbound["extra_headers"] == nil &&
                (outbound["quic_congestion_control"] == nil ||
                    (outbound["quic"] as? Bool == true &&
                     ["bbr", "bbr2", "cubic", "reno"].contains(
                         outbound["quic_congestion_control"] as? String ?? "")))
              )),
              let tls = outbound["tls"] as? [String: Any],
              (protocolCode != "anytls" || (
                (outbound["min_idle_session"] == nil ||
                    ((outbound["min_idle_session"] as? Int)
                        .map { (0...512).contains($0) } == true)) &&
                ["idle_session_check_interval", "idle_session_timeout"].allSatisfy { key in
                    guard let value = outbound[key] else { return true }
                    guard let seconds = value as? String else { return false }
                    return seconds.range(
                        of: "^[1-9][0-9]{0,3}(s|m)$",
                        options: .regularExpression) != nil
                }
              )),
              tls["enabled"] as? Bool == true,
              tls["insecure"] == nil,
              let inbounds = raw["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds.first?["type"] as? String == "tun",
              inbounds.first?["strict_route"] as? Bool == true,
              let route = raw["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let dns = raw["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote",
              let rules = route["rules"] as? [[String: Any]],
              rules.count == 2,
              rules[0]["port"] as? Int == 53,
              rules[0]["action"] as? String == "hijack-dns",
              rules[1]["ip_version"] as? Int == 6,
              rules[1]["action"] as? String == "reject",
              route["default_domain_resolver"] as? String == "dns-bootstrap",
              inbounds[0]["auto_route"] as? Bool == true,
              inbounds[0]["dns_mode"] as? String == "hijack",
              inbounds[0]["mtu"] as? Int == 1400,
              inbounds[0]["address"] as? [String] ==
                  ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
              let servers = dns["servers"] as? [[String: Any]],
              servers.count == 2,
              servers[0]["type"] as? String == "local",
              servers[0]["tag"] as? String == "dns-bootstrap",
              servers[1]["type"] as? String == "https",
              servers[1]["detour"] as? String == "proxy",
              servers[1]["tag"] as? String == "dns-remote",
              let name = tls["server_name"] as? String,
              !name.isEmpty,
              outbound["detour"] == nil,
              tls["disable_sni"] == nil
        else { return false }
        return true
    }

    /// Report Apple's real connection-manager state without inferring a
    /// Hysteria2 peer handshake, usable routing, or successful DNS.
    /// The response never includes account identifiers or VPN credentials.
    static func status(_ result: @escaping FlutterResult, protocolCode: String = "hysteria2") {
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result([
                    "contractVersion": 1,
                    "protocol": protocolCode,
                    "state": "status_unavailable",
                    "osConnected": false,
                    "verified": false,
                    "peerHandshakeVerified": false
                ] as [String: Any])
                return
            }
            let manager = (managers ?? []).first { candidate in
                guard let config = candidate.protocolConfiguration
                    as? NETunnelProviderProtocol else { return false }
                return config.providerBundleIdentifier == bundleID &&
                    config.providerConfiguration?["protocol"] as? String
                        == protocolCode
            }
            guard let manager else {
                result([
                    "contractVersion": 1,
                    "protocol": protocolCode,
                    "state": "not_configured",
                    "osConnected": false,
                    "verified": false,
                    "peerHandshakeVerified": false
                ] as [String: Any])
                return
            }
            let state: String
            switch manager.connection.status {
            case .connected: state = "os_connected_unverified"
            case .connecting: state = "connecting"
            case .reasserting: state = "reasserting"
            case .disconnecting: state = "disconnecting"
            case .disconnected: state = "disconnected"
            case .invalid: state = "invalid"
            @unknown default: state = "unknown"
            }
            result([
                "contractVersion": 1,
                "protocol": protocolCode,
                "state": state,
                "osConnected": manager.connection.status == .connected,
                "verified": false,
                "peerHandshakeVerified": false
            ] as [String: Any])
        }
    }

    static func start(_ args: Any?, backendLinked: Bool,
                      protocolCode: String = "hysteria2",
                      result: @escaping FlutterResult) {
        guard ["hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5"].contains(protocolCode) else {
            result(failure("MACOS_PROTOCOL_NOT_SUPPORTED"))
            return
        }
        let errorPrefix = protocolCode == "tuic" ? "MACOS_TUIC" :
            (protocolCode == "anytls" ? "MACOS_ANYTLS" :
             (protocolCode == "naive" ? "MACOS_NAIVE" :
             (protocolCode == "shadowtls" ? "MACOS_SHADOWTLS" :
             (protocolCode == "snell" ? "MACOS_SNELL" :
             (protocolCode == "socks5" ? "MACOS_SOCKS5" : "MACOS_HYSTERIA2")))))
        guard backendLinked else {
            result(failure(errorPrefix + "_PACKET_FLOW_BRIDGE_MISSING"))
            return
        }
        guard let input = args as? [String: Any],
              input["protocol"] as? String == protocolCode,
              let config = input["config"] as? String,
              allowedConfig(config, protocolCode: protocolCode),
              let namespace = input["namespace"] as? String,
              (3...128).contains(namespace.count),
              let account = input["account"] as? String,
              (1...255).contains(account.count) else {
            result(failure(errorPrefix + "_PROFILE_INVALID"))
            return
        }
        guard let group = Bundle.main.object(forInfoDictionaryKey:
                "TwinConnectKeychainAccessGroup") as? String,
              !group.isEmpty else {
            result(failure("MACOS_KEYCHAIN_GROUP_NOT_CONFIGURED"))
            return
        }

        // Shared Keychain access is granted through Apple provisioning;
        // the subscription payload never enters providerConfiguration.
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(failure("MACOS_VPN_PREFERENCES_LOAD_FAILED"))
                return
            }
            let manager = (managers ?? []).first { candidate in
                guard let previous = candidate.protocolConfiguration
                    as? NETunnelProviderProtocol else { return false }
                return previous.providerBundleIdentifier == bundleID &&
                    previous.providerConfiguration?["protocol"] as? String
                        == protocolCode
            } ?? NETunnelProviderManager()
            if let previous = manager.protocolConfiguration
                as? NETunnelProviderProtocol,
               let oldNamespace = previous.providerConfiguration?["namespace"]
                    as? String, oldNamespace != namespace {
                result(failure("MACOS_TENANT_PROFILE_CONFLICT"))
                return
            }

            guard manager.connection.status == .disconnected ||
                  manager.connection.status == .invalid else {
                result(failure("MACOS_VPN_ALREADY_ACTIVE"))
                return
            }
            let keychain: [CFString: Any] = [
                kSecClass: kSecClassGenericPassword,
                kSecAttrService: keychainService,
                kSecAttrAccount: namespace + ":" + account + ":" + protocolCode,
                kSecAttrAccessGroup: group
            ]
            // Never log the config, Keychain query or account credentials.
            SecItemDelete(keychain as CFDictionary)
            var store = keychain
            store[kSecValueData] = Data(config.utf8)
            store[kSecReturnPersistentRef] = kCFBooleanTrue
            var persistent: CFTypeRef?
            guard SecItemAdd(store as CFDictionary, &persistent) == errSecSuccess,
                  let reference = persistent as? Data else {
                result(failure(errorPrefix + "_KEYCHAIN_STORE_FAILED"))
                return
            }

            let tunnel = NETunnelProviderProtocol()
            tunnel.providerBundleIdentifier = bundleID
            tunnel.serverAddress = "TwinConnect " + protocolCode.uppercased()
            tunnel.passwordReference = reference
            tunnel.providerConfiguration = [
                "protocol": protocolCode,
                "namespace": namespace
            ]
            manager.protocolConfiguration = tunnel
            manager.localizedDescription = "TwinConnect"
            manager.isEnabled = true
            manager.saveToPreferences { error in
                guard error == nil else {
                    result(failure("MACOS_VPN_PREFERENCES_SAVE_FAILED"))
                    return
                }
                manager.loadFromPreferences { error in
                    guard error == nil else {
                        result(failure("MACOS_VPN_PREFERENCES_RELOAD_FAILED"))
                        return
                    }
                    do {
                        try manager.connection.startVPNTunnel()
                        result([
                            "contractVersion": 1,
                            "protocol": protocolCode,
                            "state": "connecting",
                            "peerHandshakeVerified": false
                        ] as [String: Any])
                    } catch {
                        result(failure(errorPrefix + "_OS_START_REJECTED"))
                    }
                }
            }
        }
    }
}
