import Foundation
import Flutter
import NetworkExtension
import Security

/// Signed-app tunnel preferences lifecycle. No connection is declared
/// successful here: startVPNTunnel only requests an OS-managed startup.
enum TwinConnectMacOSVPNControl {
    static let providerBundle = "com.twinpanel.twinconnect.PacketTunnel"
    private static let service = "com.twinpanel.twinconnect.macos.wireguard"

    private static func failure(_ reason: String) -> FlutterError {
        FlutterError(code: reason, message: reason, details: nil)
    }

    private static func manager(_ items: [NETunnelProviderManager]) -> NETunnelProviderManager {
        items.first {
            ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                .providerBundleIdentifier == providerBundle
        } ?? NETunnelProviderManager()
    }

    static func start(_ args: Any?, backendLinked: Bool,
                      result: @escaping FlutterResult) {
        guard backendLinked else {
            result(failure("MACOS_WIREGUARD_BACKEND_NOT_LINKED"))
            return
        }
        guard let input = args as? [String: Any],
              input["protocol"] as? String == "wireguard",
              let config = input["config"] as? String,
              (65...65536).contains(config.utf8.count),
              config.contains("[Interface]"), config.contains("[Peer]"),
              let namespace = input["namespace"] as? String,
              (3...128).contains(namespace.count),
              let account = input["account"] as? String,
              (1...255).contains(account.count) else {
            result(failure("MACOS_WIREGUARD_PROFILE_INVALID"))
            return
        }

        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(failure("MACOS_VPN_PREFERENCES_LOAD_FAILED"))
                return
            }
            let selected = manager(managers ?? [])
            if let existing = selected.protocolConfiguration as? NETunnelProviderProtocol,
               let oldNamespace = existing.providerConfiguration?["namespace"] as? String,
               oldNamespace != namespace {
                result(failure("MACOS_TENANT_PROFILE_CONFLICT"))
                return
            }

            // Private keys must never be passed in providerConfiguration.
            // Keychain profile is accessible to the extension ONLY after a
            // shared Keychain access group is provisioned by Apple signing.
            guard let group = Bundle.main.object(forInfoDictionaryKey:
                "TwinConnectKeychainAccessGroup") as? String,
                !group.isEmpty else {
                result(failure("MACOS_KEYCHAIN_GROUP_NOT_CONFIGURED"))
                return
            }
            let query: [CFString: Any] = [
                kSecClass: kSecClassGenericPassword,
                kSecAttrService: service,
                kSecAttrAccount: namespace + ":" + account,
                kSecAttrAccessGroup: group
            ]
            SecItemDelete(query as CFDictionary)
            var save = query
            save[kSecValueData] = Data(config.utf8)
            save[kSecReturnPersistentRef] = kCFBooleanTrue
            var reference: CFTypeRef?
            guard SecItemAdd(save as CFDictionary, &reference) == errSecSuccess,
                  let persistent = reference as? Data else {
                result(failure("MACOS_KEYCHAIN_PROFILE_STORE_FAILED"))
                return
            }

            let settings = NETunnelProviderProtocol()
            settings.providerBundleIdentifier = providerBundle
            settings.serverAddress = "TwinConnect WireGuard"
            settings.passwordReference = persistent
            settings.providerConfiguration = [
                "protocol": "wireguard",
                "namespace": namespace
            ]
            selected.protocolConfiguration = settings
            selected.localizedDescription = "TwinConnect"
            selected.isEnabled = true
            selected.saveToPreferences { error in
                guard error == nil else {
                    result(failure("MACOS_VPN_PREFERENCES_SAVE_FAILED"))
                    return
                }
                selected.loadFromPreferences { error in
                    guard error == nil else {
                        result(failure("MACOS_VPN_PREFERENCES_RELOAD_FAILED"))
                        return
                    }
                    do {
                        try selected.connection.startVPNTunnel()
                        result([
                            "contractVersion": 1,
                            "protocol": "wireguard",
                            "state": "connecting",
                            "peerHandshakeVerified": false
                        ] as [String: Any])
                    } catch {
                        result(failure("MACOS_VPN_START_REJECTED"))
                    }
                }
            }
        }
    }

    static func stop(_ result: @escaping FlutterResult) {
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(failure("MACOS_VPN_PREFERENCES_LOAD_FAILED"))
                return
            }
            guard let selected = (managers ?? []).first(where: {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == providerBundle
            }) else {
                result(["contractVersion": 1, "state": "disconnected"])
                return
            }
            selected.connection.stopVPNTunnel()
            result(["contractVersion": 1, "state": "disconnecting"])
        }
    }

    static func status(_ result: @escaping FlutterResult) {
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(["contractVersion": 1, "state": "unknown",
                        "verified": false])
                return
            }
            let selected = (managers ?? []).first {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == providerBundle
            }
            let label: String
            switch selected?.connection.status {
            case .connected: label = "os_connected_unverified"
            case .connecting: label = "connecting"
            case .disconnecting: label = "disconnecting"
            case .reasserting: label = "reasserting"
            case .disconnected: label = "disconnected"
            case .invalid: label = "invalid"
            case .none: label = "not_configured"
            @unknown default: label = "unknown"
            }
            result(["contractVersion": 1, "state": label,
                    "verified": false] as [String: Any])
        }
    }
}
