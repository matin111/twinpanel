import Foundation
import NetworkExtension
import Security

#if canImport(WireGuardKit)
import WireGuardKit
#endif

/// Real WireGuardKit adapter for the macOS Network Extension.
/// The upstream WireGuardKit and WireGuardKitGo must both be linked and
/// Apple packet-tunnel entitlements granted before a live tunnel is possible.
/// Missing libraries ALWAYS fail closed; no synthetic connected state.
enum MacWireGuardError: Int, Error {
    case backendNotLinked = 2001
    case missingProfile = 2002
    case invalidConfiguration = 2003
}

final class TwinConnectMacWireGuardEngine {
    #if canImport(WireGuardKit)
    private weak var provider: NEPacketTunnelProvider?
    private var adapter: WireGuardAdapter?

    init(provider: NEPacketTunnelProvider) {
        self.provider = provider
    }

    func start(completion: @escaping (Error?) -> Void) {
        guard let provider = provider,
              let configuration = provider.protocolConfiguration as? NETunnelProviderProtocol,
              let reference = configuration.passwordReference,
              let profile = Self.readProfile(reference),
              let text = String(data: profile, encoding: .utf8),
              let tunnel = try? TunnelConfiguration(
                  fromWgQuickConfig: text, called: "TwinConnect") else {
            completion(MacWireGuardError.invalidConfiguration)
            return
        }
        let created = WireGuardAdapter(with: provider) { _, _ in }
        adapter = created
        created.start(tunnelConfiguration: tunnel) { error in
            completion(error)
        }
    }

    func stop(completion: @escaping () -> Void) {
        guard let adapter = adapter else { completion(); return }
        adapter.stop { [weak self] _ in
            self?.adapter = nil
            completion()
        }
    }

    private static func readProfile(_ reference: Data) -> Data? {
        let query: [CFString: Any] = [
            kSecValuePersistentRef: reference,
            kSecReturnData: kCFBooleanTrue as Any,
            kSecMatchLimit: kSecMatchLimitOne
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess else {
            return nil
        }
        return item as? Data
    }
    #else
    init(provider: NEPacketTunnelProvider) {}
    func start(completion: @escaping (Error?) -> Void) {
        completion(MacWireGuardError.backendNotLinked)
    }
    func stop(completion: @escaping () -> Void) { completion() }
    #endif
}
