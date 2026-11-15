import Foundation
import NetworkExtension
import Security

#if canImport(WireGuardKit)
import WireGuardKit
#endif

/// WireGuard packet-tunnel adapter for a *signed* iOS Network Extension.
///
// Nothing in this file runs in a Flutter iOS simulator preview. For a device
// build, a separate PacketTunnel target must link the upstream WireGuardKit
// and WireGuardKitGo libraries, carry the packet-tunnel-provider entitlement,
// and share a Keychain access group with Runner. The app must put a wg-quick
// config into that shared Keychain group and set passwordReference to its
// persistent reference; do not put private keys into providerConfiguration.
enum TwinConnectWireGuardError: Int, Error {
    case engineNotLinked = 1001
    case missingKeychainReference = 1002
    case invalidConfiguration = 1003
    case failedToStart = 1004
}

final class TwinConnectWireGuardEngine {
    #if canImport(WireGuardKit)
    private weak var provider: NEPacketTunnelProvider?
    private var adapter: WireGuardAdapter?

    init(provider: NEPacketTunnelProvider) {
        self.provider = provider
    }

    func start(completionHandler: @escaping (Error?) -> Void) {
        guard let provider = provider,
              let configuration = provider.protocolConfiguration as? NETunnelProviderProtocol,
              let reference = configuration.passwordReference,
              let secret = Self.readKeychainPersistentReference(reference),
              let config = String(data: secret, encoding: .utf8),
              let tunnel = try? TunnelConfiguration(
                  fromWgQuickConfig: config, called: "TwinConnect") else {
            completionHandler(TwinConnectWireGuardError.invalidConfiguration)
            return
        }
        // No credentials, config text or remote endpoints are logged.
        let adapter = WireGuardAdapter(with: provider) { _, _ in }
        self.adapter = adapter
        adapter.start(tunnelConfiguration: tunnel) { error in
            completionHandler(error)
        }
    }

    func stop(completionHandler: @escaping () -> Void) {
        guard let adapter else {
            completionHandler()
            return
        }
        adapter.stop { [weak self] _ in
            self?.adapter = nil
            completionHandler()
        }
    }

    private static func readKeychainPersistentReference(_ reference: Data) -> Data? {
        let query: [CFString: Any] = [
            kSecValuePersistentRef: reference,
            kSecReturnData: kCFBooleanTrue as Any,
            kSecMatchLimit: kSecMatchLimitOne
        ]
        var raw: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &raw) == errSecSuccess else {
            return nil
        }
        return raw as? Data
    }
    #else
    init(provider: NEPacketTunnelProvider) {}

    func start(completionHandler: @escaping (Error?) -> Void) {
        completionHandler(TwinConnectWireGuardError.engineNotLinked)
    }

    func stop(completionHandler: @escaping () -> Void) {
        completionHandler()
    }
    #endif
}
