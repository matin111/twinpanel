import Foundation
import FlutterMacOS
import NetworkExtension
import Security

/// Host-only preparation of an account-scoped Mieru core + Libbox relay.
///
/// This method NEVER starts a VPN. It stores the validated pair in a shared
/// Apple-provisioned Keychain group and passes only a persistent reference
/// to PacketTunnel. The signed provider must still pin physical egress,
/// authenticate Mieru, start Libbox and verify egress independently.
enum TwinConnectMacOSMieruControl {
    private static let bundleID = "com.twinpanel.twinconnect.PacketTunnel"
    private static let service = "com.twinpanel.twinconnect.macos.mieru"

    private static func failure(_ code: String) -> FlutterError {
        FlutterError(code: code, message: code, details: nil)
    }

    private static func validBundle(_ core: [String: Any],
                                    _ relay: [String: Any]) -> Bool {
        guard core["rpcPort"] as? Int == 0,
              core["httpProxyPort"] == nil,
              core["socks5ListenLAN"] as? Bool == false,
              core["httpProxyListenLAN"] as? Bool == false,
              let port = core["socks5Port"] as? Int,
              (1025...65535).contains(port),
              let profiles = core["profiles"] as? [[String: Any]],
              profiles.count == 1,
              let profile = profiles.first,
              let identity = profile["profileName"] as? String,
              !identity.isEmpty, core["activeProfile"] as? String == identity,
              let user = profile["user"] as? [String: Any],
              user["name"] as? String == identity,
              let password = user["password"] as? String,
              !password.isEmpty, password.utf8.count <= 4096,
              let servers = profile["servers"] as? [[String: Any]],
              servers.count == 1,
              let endpoint = servers[0]["ipAddress"] as? String,
              !endpoint.isEmpty,
              servers[0]["domainName"] as? String == "",
              let bindings = servers[0]["portBindings"] as? [[String: Any]],
              !bindings.isEmpty, bindings.count <= 32,
              let outbounds = relay["outbounds"] as? [[String: Any]],
              outbounds.count == 1,
              outbounds[0]["type"] as? String == "socks",
              outbounds[0]["tag"] as? String == "proxy",
              outbounds[0]["server"] as? String == "127.0.0.1",
              outbounds[0]["server_port"] as? Int == port,
              outbounds[0]["version"] as? String == "5",
              outbounds[0]["network"] as? String == "tcp",
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
            return false
        }
        // Host checks shape; provider independently validates public IPv4
        // and /32 route before any transport or TUN is allowed to start.
        return true
    }

    static func prepare(_ args: Any?, result: @escaping FlutterResult) {
        guard let args = args as? [String: Any],
              args["protocol"] as? String == "mieru",
              let namespace = args["namespace"] as? String,
              (3...128).contains(namespace.count),
              let account = args["account"] as? String,
              (1...255).contains(account.count),
              let core = args["core"] as? [String: Any],
              let relay = args["relay"] as? [String: Any],
              validBundle(core, relay),
              let group = Bundle.main.object(
                forInfoDictionaryKey: "TwinConnectKeychainAccessGroup"
              ) as? String,
              !group.isEmpty,
              JSONSerialization.isValidJSONObject(["core": core, "relay": relay]),
              let data = try? JSONSerialization.data(
                  withJSONObject: ["core": core, "relay": relay]),
              (256...131072).contains(data.count) else {
            result(failure("MACOS_MIERU_PREPARE_INVALID"))
            return
        }

        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(failure("MACOS_MIERU_PREFERENCES_LOAD_FAILED"))
                return
            }
            let manager = (managers ?? []).first {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == bundleID
            } ?? NETunnelProviderManager()
            guard manager.connection.status == .disconnected ||
                    manager.connection.status == .invalid else {
                result(failure("MACOS_MIERU_VPN_ALREADY_ACTIVE"))
                return
            }
            if let previous = manager.protocolConfiguration
                as? NETunnelProviderProtocol,
               let oldNamespace = previous.providerConfiguration?["namespace"]
                    as? String, oldNamespace != namespace {
                result(failure("MACOS_MIERU_TENANT_PROFILE_CONFLICT"))
                return
            }

            let item: [CFString: Any] = [
                kSecClass: kSecClassGenericPassword,
                kSecAttrService: service,
                kSecAttrAccount: namespace + ":" + account + ":mieru",
                kSecAttrAccessGroup: group
            ]
            var store = item
            store[kSecValueData] = data
            store[kSecReturnPersistentRef] = kCFBooleanTrue
            // Replacing one account's profile does not replace a different
            // account or tenant; the provider never sees credentials in plist.
            SecItemDelete(item as CFDictionary)
            var ref: CFTypeRef?
            guard SecItemAdd(store as CFDictionary, &ref) == errSecSuccess,
                  let persistent = ref as? Data else {
                result(failure("MACOS_MIERU_KEYCHAIN_STORE_FAILED"))
                return
            }

            let provider = NETunnelProviderProtocol()
            provider.providerBundleIdentifier = bundleID
            provider.serverAddress = "TwinConnect MIERU"
            provider.passwordReference = persistent
            provider.providerConfiguration = [
                "protocol": "mieru",
                "namespace": namespace
            ]
            manager.protocolConfiguration = provider
            manager.localizedDescription = "TwinConnect"
            // Only prepare the profile. Never startVPNTunnel until the
            // signed extension's full Mieru/Libbox path has been proven.
            manager.isEnabled = false
            manager.saveToPreferences { error in
                guard error == nil else {
                    SecItemDelete(item as CFDictionary)
                    result(failure("MACOS_MIERU_PREFERENCES_SAVE_FAILED"))
                    return
                }
                result([
                    "contractVersion": 1,
                    "protocol": "mieru",
                    "state": "prepared_not_connectable",
                    "engineReady": false,
                    "peerHandshakeVerified": false,
                    "connected": false
                ] as [String: Any])
            }
        }
    }
}
