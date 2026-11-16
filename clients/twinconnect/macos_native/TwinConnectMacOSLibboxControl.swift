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

    private static func allowedConfig(_ text: String) -> Bool {
        guard (64...131072).contains(text.utf8.count),
              let data = text.data(using: .utf8),
              let raw = (try? JSONSerialization.jsonObject(with: data))
                    as? [String: Any],
              let outbounds = raw["outbounds"] as? [[String: Any]],
              outbounds.count == 1,
              let outbound = outbounds.first,
              outbound["type"] as? String == "hysteria2",
              outbound["tag"] as? String == "proxy",
              outbound["password"] is String,
              let tls = outbound["tls"] as? [String: Any],
              tls["enabled"] as? Bool == true,
              tls["insecure"] == nil,
              let inbounds = raw["inbounds"] as? [[String: Any]],
              inbounds.count == 1,
              inbounds.first?["type"] as? String == "tun",
              inbounds.first?["strict_route"] as? Bool == true,
              let route = raw["route"] as? [String: Any],
              route["final"] as? String == "proxy",
              let dns = raw["dns"] as? [String: Any],
              dns["final"] as? String == "dns-remote"
        else { return false }
        return true
    }

    static func start(_ args: Any?, backendLinked: Bool,
                      result: @escaping FlutterResult) {
        guard backendLinked else {
            result(failure("MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING"))
            return
        }
        guard let input = args as? [String: Any],
              input["protocol"] as? String == "hysteria2",
              let config = input["config"] as? String,
              allowedConfig(config),
              let namespace = input["namespace"] as? String,
              (3...128).contains(namespace.count),
              let account = input["account"] as? String,
              (1...255).contains(account.count) else {
            result(failure("MACOS_HYSTERIA2_PROFILE_INVALID"))
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
            let manager = (managers ?? []).first {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == bundleID
            } ?? NETunnelProviderManager()
            if let previous = manager.protocolConfiguration
                as? NETunnelProviderProtocol,
               let oldNamespace = previous.providerConfiguration?["namespace"]
                    as? String, oldNamespace != namespace {
                result(failure("MACOS_TENANT_PROFILE_CONFLICT"))
                return
            }

            let keychain: [CFString: Any] = [
                kSecClass: kSecClassGenericPassword,
                kSecAttrService: keychainService,
                kSecAttrAccount: namespace + ":" + account,
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
                result(failure("MACOS_HYSTERIA2_KEYCHAIN_STORE_FAILED"))
                return
            }

            let tunnel = NETunnelProviderProtocol()
            tunnel.providerBundleIdentifier = bundleID
            tunnel.serverAddress = "TwinConnect Hysteria2"
            tunnel.passwordReference = reference
            tunnel.providerConfiguration = [
                "protocol": "hysteria2",
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
                            "protocol": "hysteria2",
                            "state": "connecting",
                            "peerHandshakeVerified": false
                        ] as [String: Any])
                    } catch {
                        result(failure("MACOS_HYSTERIA2_OS_START_REJECTED"))
                    }
                }
            }
        }
    }
}
