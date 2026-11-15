import Flutter
import Foundation
import NetworkExtension
import Security

/// Real host-side lifecycle for a signed Packet Tunnel extension.
///
/// The Flutter app obtains a fresh, authorized single-node profile before
/// calling this. This layer neither mocks success nor accepts other engines.
/// A Keychain sharing entitlement and embedded PacketTunnel.appex are required.
enum TwinConnectIOSVPNControl {
    private static let providerID = "com.twinpanel.twinconnect.PacketTunnel"
    private static let keychainService = "com.twinpanel.twinconnect.wireguard"

    private static func failure(_ code: String) -> FlutterError {
        FlutterError(code: code, message: code, details: nil)
    }

    private static func extensionInstalled() -> Bool {
        guard let path = Bundle.main.builtInPlugInsPath else { return false }
        let url = URL(fileURLWithPath: path)
            .appendingPathComponent("PacketTunnel.appex", isDirectory: true)
        guard let bundle = Bundle(url: url),
              bundle.bundleIdentifier == providerID else { return false }
        return true
    }

    static func checkInstallation(_ result: @escaping FlutterResult) {
        result([
            "contractVersion": 1,
            "extensionInstalled": extensionInstalled(),
            // Presence of the .appex alone is NOT evidence of a WireGuardGo
            // backend, provisioned entitlement, live peer or protected DNS.
            "engineReady": false,
            "wireguardReady": false,
            "reason": extensionInstalled()
                ? "IOS_ENGINE_NOT_RUNTIME_VERIFIED"
                : "IOS_PACKET_TUNNEL_EXTENSION_MISSING"
        ] as [String: Any])
    }

    static func start(_ args: Any?, result: @escaping FlutterResult) {
        guard extensionInstalled() else {
            result(failure("IOS_PACKET_TUNNEL_EXTENSION_MISSING"))
            return
        }
        guard let fields = args as? [String: Any],
              fields["protocol"] as? String == "wireguard",
              let config = fields["config"] as? String,
              config.utf8.count > 64, config.utf8.count <= 65536,
              config.contains("[Interface]"),
              config.contains("[Peer]"),
              let namespace = fields["namespace"] as? String,
              namespace.count >= 3, namespace.count <= 128,
              let account = fields["account"] as? String,
              !account.isEmpty, account.count < 256,
              let group = Bundle.main.object(forInfoDictionaryKey:
                  "TwinConnectKeychainAccessGroup") as? String,
              !group.isEmpty else {
            result(failure("IOS_WIREGUARD_PROFILE_OR_KEYCHAIN_GROUP_INVALID"))
            return
        }
        // A saved profile is not an active tunnel. Always start from a
        // fresh single-node entitlement obtained by the authenticated app.
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            if error != nil {
                result(failure("IOS_VPN_PREFERENCES_LOAD_FAILED"))
                return
            }
            let selected = (managers ?? []).first {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == providerID
            } ?? NETunnelProviderManager()
            // Refuse to overwrite a VPN managed by a different tenant.
            if let existing = selected.protocolConfiguration as?
                    NETunnelProviderProtocol,
               let storedNamespace = existing.providerConfiguration?["namespace"]
                    as? String,
               storedNamespace != namespace {
                result(failure("IOS_TENANT_PROFILE_CONFLICT"))
                return
            }

            let keychainQuery: [CFString: Any] = [
                kSecClass: kSecClassGenericPassword,
                kSecAttrService: keychainService,
                kSecAttrAccount: namespace + ":" + account,
                kSecAttrAccessGroup: group,
            ]
            // A per-tenant account key is replaced only after authorization.
            SecItemDelete(keychainQuery as CFDictionary)
            var save = keychainQuery
            save[kSecValueData] = Data(config.utf8)
            save[kSecAttrAccessible] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            save[kSecReturnPersistentRef] = kCFBooleanTrue
            var item: CFTypeRef?
            guard SecItemAdd(save as CFDictionary, &item) == errSecSuccess,
                  let reference = item as? Data else {
                result(failure("IOS_KEYCHAIN_PROFILE_STORE_FAILED"))
                return
            }

            let protocolSettings = NETunnelProviderProtocol()
            protocolSettings.providerBundleIdentifier = providerID
            protocolSettings.serverAddress = "TwinConnect WireGuard"
            protocolSettings.passwordReference = reference
            protocolSettings.providerConfiguration = [
                "protocol": "wireguard",
                "namespace": namespace
            ]
            selected.protocolConfiguration = protocolSettings
            selected.localizedDescription = "TwinConnect"
            selected.isEnabled = true
            selected.saveToPreferences { error in
                guard error == nil else {
                    result(failure("IOS_VPN_PREFERENCES_SAVE_FAILED"))
                    return
                }
                selected.loadFromPreferences { error in
                    guard error == nil else {
                        result(failure("IOS_VPN_PREFERENCES_RELOAD_FAILED"))
                        return
                    }
                    do {
                        try selected.connection.startVPNTunnel()
                        // This is NOT a handshake confirmation; the actual
                        // extension must start and report its own status.
                        result([
                            "contractVersion": 1,
                            "protocol": "wireguard",
                            "state": "connecting",
                            "peerHandshakeVerified": false
                        ] as [String: Any])
                    } catch {
                        result(failure("IOS_VPN_START_REJECTED"))
                    }
                }
            }
        }
    }

    static func stop(_ result: @escaping FlutterResult) {
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(failure("IOS_VPN_PREFERENCES_LOAD_FAILED"))
                return
            }
            let selected = (managers ?? []).first {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == providerID
            }
            guard let selected = selected else {
                result(["contractVersion": 1, "state": "disconnected"])
                return
            }
            selected.connection.stopVPNTunnel()
            result(["contractVersion": 1, "state": "disconnecting"])
        }
    }
}
