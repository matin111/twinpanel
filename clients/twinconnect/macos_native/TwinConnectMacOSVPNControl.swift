import Foundation
import FlutterMacOS
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
        items.first { candidate in
            guard let config = candidate.protocolConfiguration
                as? NETunnelProviderProtocol else { return false }
            return config.providerBundleIdentifier == providerBundle &&
                config.providerConfiguration?["protocol"] as? String
                    == "wireguard"
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
            let conflicting = (managers ?? []).contains { candidate in
                guard let config = candidate.protocolConfiguration
                    as? NETunnelProviderProtocol,
                    config.providerBundleIdentifier == providerBundle else {
                    return false
                }
                switch candidate.connection.status {
                case .connected, .connecting, .reasserting, .disconnecting:
                    return true
                default:
                    return false
                }
            }
            guard !conflicting else {
                result(failure("MACOS_VPN_ALREADY_ACTIVE"))
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
            TwinConnectMacOSKillSwitch.applySavedPolicy(settings, manager: selected)
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
            // Stop only connections that are actually in flight or active,
            // never the first unrelated protocol preference in the array.
            let active = (managers ?? []).filter { candidate in
                guard let config = candidate.protocolConfiguration
                    as? NETunnelProviderProtocol,
                    config.providerBundleIdentifier == providerBundle else {
                    return false
                }
                switch candidate.connection.status {
                case .connected, .connecting, .reasserting:
                    return true
                default:
                    return false
                }
            }
            for selected in active {
                selected.connection.stopVPNTunnel()
            }
            result([
                "contractVersion": 1,
                "state": active.isEmpty ? "disconnected" : "disconnecting"
            ] as [String: Any])
        }
    }

    static func status(_ result: @escaping FlutterResult) {
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(["contractVersion": 1, "state": "unknown",
                        "verified": false])
                return
            }
            let candidates = (managers ?? []).filter { candidate in
                (candidate.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == providerBundle
            }
            // Prefer the actual active tunnel instead of whichever saved
            // protocol preference macOS happens to return first.
            let selected = candidates.first { candidate in
                switch candidate.connection.status {
                case .connected, .connecting, .reasserting, .disconnecting:
                    return true
                default:
                    return false
                }
            } ?? candidates.first
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


/// Apple-managed VPN routing protection; no PF firewall modifications.
/// "Configured" is never synonymous with verified packet blocking.
enum TwinConnectMacOSKillSwitch {
    private static let preference = "twinconnect.macos.killSwitch.requested.v1"
    private static let bundleID = "com.twinpanel.twinconnect.PacketTunnel"

    static func applySavedPolicy(_ tunnel: NETunnelProviderProtocol,
                                 manager: NETunnelProviderManager) {
        let requested = UserDefaults.standard.bool(forKey: preference)
        tunnel.includeAllNetworks = requested
        tunnel.excludeLocalNetworks = false
        manager.onDemandRules = requested ? [NEOnDemandRuleConnect()] : []
        manager.isOnDemandEnabled = requested
    }

    static func status(_ result: @escaping FlutterResult) {
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(["contractVersion": 1, "requested": false,
                        "configured": false, "verified": false,
                        "reason": "MACOS_KILLSWITCH_PREFERENCES_UNAVAILABLE"])
                return
            }
            let candidates = (managers ?? []).filter {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == bundleID
            }
            let requested = UserDefaults.standard.bool(forKey: preference)
            let configured = !candidates.isEmpty && candidates.allSatisfy {
                guard let p = $0.protocolConfiguration as? NETunnelProviderProtocol else {
                    return false
                }
                return p.includeAllNetworks && $0.isOnDemandEnabled &&
                    !($0.onDemandRules ?? []).isEmpty
            }
            result([
                "contractVersion": 1,
                "requested": requested,
                "configured": requested && configured,
                "verified": false,
                "reason": "MACOS_KILLSWITCH_REQUIRES_SIGNED_EGRESS_TEST"
            ] as [String: Any])
        }
    }

    static func set(_ args: Any?, result: @escaping FlutterResult) {
        guard let requested = (args as? [String: Any])?["enabled"] as? Bool else {
            result(FlutterError(code: "MACOS_KILLSWITCH_ARGUMENT_INVALID",
                                message: nil, details: nil))
            return
        }
        NETunnelProviderManager.loadAllFromPreferences { managers, error in
            guard error == nil else {
                result(FlutterError(code: "MACOS_KILLSWITCH_PREFERENCES_UNAVAILABLE",
                                    message: nil, details: nil))
                return
            }
            let candidates = (managers ?? []).filter {
                ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                    .providerBundleIdentifier == bundleID
            }
            // Never rewrite OS route controls underneath an active tunnel.
            let busy = candidates.contains {
                switch $0.connection.status {
                case .connected, .connecting, .reasserting, .disconnecting:
                    return true
                default:
                    return false
                }
            }
            guard !busy else {
                result(FlutterError(code: "MACOS_KILLSWITCH_DISCONNECT_FIRST",
                                    message: nil, details: nil))
                return
            }
            // In the absence of a provisioned VPN profile, retain the request
            // but report that OS enforcement is NOT configured.
            if candidates.isEmpty {
                UserDefaults.standard.set(requested, forKey: preference)
                result(["contractVersion": 1, "requested": requested,
                        "configured": false, "verified": false] as [String: Any])
                return
            }
            let group = DispatchGroup()
            let lock = NSLock()
            var failed = false
            for manager in candidates {
                guard let protocolConfig = manager.protocolConfiguration
                    as? NETunnelProviderProtocol else { continue }
                protocolConfig.includeAllNetworks = requested
                protocolConfig.excludeLocalNetworks = false
                manager.onDemandRules = requested ? [NEOnDemandRuleConnect()] : []
                manager.isOnDemandEnabled = requested
                group.enter()
                manager.saveToPreferences { error in
                    if error != nil {
                        lock.lock()
                        failed = true
                        lock.unlock()
                    }
                    group.leave()
                }
            }
            group.notify(queue: .main) {
                guard !failed else {
                    result(FlutterError(code: "MACOS_KILLSWITCH_SAVE_FAILED",
                                        message: nil, details: nil))
                    return
                }
                UserDefaults.standard.set(requested, forKey: preference)
                result(["contractVersion": 1, "requested": requested,
                        "configured": true, "verified": false] as [String: Any])
            }
        }
    }
}
