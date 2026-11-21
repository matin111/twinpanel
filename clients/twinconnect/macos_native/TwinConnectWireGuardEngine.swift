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
    case alreadyRunning = 2004
}

final class TwinConnectMacWireGuardEngine {
    #if canImport(WireGuardKit)
    private weak var provider: NEPacketTunnelProvider?
    private var adapter: WireGuardAdapter?

    init(provider: NEPacketTunnelProvider) {
        self.provider = provider
    }

    func start(completion: @escaping (Error?) -> Void) {
        // Never replace a live adapter: doing so would orphan a tunnel and
        // leave the app unable to disconnect it.
        guard adapter == nil else {
            completion(MacWireGuardError.alreadyRunning)
            return
        }
        guard let provider = provider,
              let configuration = provider.protocolConfiguration as? NETunnelProviderProtocol,
              let reference = configuration.passwordReference,
              let profile = Self.readProfile(reference) else {
            completion(MacWireGuardError.missingProfile)
            return
        }
        guard let text = String(data: profile, encoding: .utf8),
              let tunnel = try? TwinConnectWgQuickParser.parse(text) else {
            completion(MacWireGuardError.invalidConfiguration)
            return
        }
        let created = WireGuardAdapter(with: provider) { _, _ in }
        adapter = created
        created.start(tunnelConfiguration: tunnel) { [weak self] error in
            guard let error else {
                completion(nil)
                return
            }
            // A failed start may have already allocated a userspace backend.
            // Tear it down before allowing NetworkExtension to retry.
            created.stop { _ in
                if self?.adapter === created {
                    self?.adapter = nil
                }
                completion(error)
            }
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


#if canImport(WireGuardKit)
// WireGuardKit does not export the app target's wg-quick convenience parser.
// Keep this strict parser local to the packet-tunnel target and fail closed on
// unfamiliar options instead of silently changing routing or DNS semantics.
private enum TwinConnectWgQuickParser {
    enum ParseError: Error {
        case invalidProfile
    }

    static func parse(_ text: String) throws -> TunnelConfiguration {
        var interfaceValues: [String: String] = [:]
        var peerValues: [[String: String]] = []
        var current: String?
        var fields: [String: String] = [:]

        func commit() throws {
            guard let current = current else { return }
            if current == "interface" {
                guard interfaceValues.isEmpty else { throw ParseError.invalidProfile }
                interfaceValues = fields
            } else if current == "peer" {
                peerValues.append(fields)
            }
        }

        for line in text.components(separatedBy: .newlines) {
            let clean = String(line.prefix(while: { $0 != "#" }))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if clean.isEmpty { continue }
            let lower = clean.lowercased()
            if lower == "[interface]" || lower == "[peer]" {
                try commit()
                current = lower == "[interface]" ? "interface" : "peer"
                fields = [:]
                continue
            }
            guard current != nil, let separator = clean.firstIndex(of: "=") else {
                throw ParseError.invalidProfile
            }
            let key = clean[..<separator].trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let value = clean[clean.index(after: separator)...]
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { throw ParseError.invalidProfile }
            let permitted: Set<String> = current == "interface"
                ? ["privatekey", "address", "dns", "mtu", "listenport"]
                : ["publickey", "presharedkey", "allowedips", "endpoint", "persistentkeepalive"]
            guard permitted.contains(key) else { throw ParseError.invalidProfile }
            if let existing = fields[key] {
                guard ["address", "dns", "allowedips"].contains(key) else {
                    throw ParseError.invalidProfile
                }
                fields[key] = existing + "," + value
            } else {
                fields[key] = value
            }
        }
        try commit()
        guard let keyString = interfaceValues["privatekey"],
              let key = PrivateKey(base64Key: keyString),
              let addresses = parseAddresses(interfaceValues["address"]),
              !addresses.isEmpty,
              !peerValues.isEmpty else { throw ParseError.invalidProfile }

        var interface = InterfaceConfiguration(privateKey: key)
        interface.addresses = addresses
        if let value = interfaceValues["listenport"] {
            guard let port = UInt16(value) else { throw ParseError.invalidProfile }
            interface.listenPort = port
        }
        if let value = interfaceValues["mtu"] {
            guard let mtu = UInt16(value), mtu >= 576 else { throw ParseError.invalidProfile }
            interface.mtu = mtu
        }
        if let value = interfaceValues["dns"] {
            let entries = split(value)
            var servers: [DNSServer] = []
            var searches: [String] = []
            for entry in entries {
                if let server = DNSServer(from: entry) {
                    servers.append(server)
                } else {
                    // DNS search domains are intentionally not accepted until
                    // their validation policy is explicitly defined.
                    searches.append(entry)
                }
            }
            guard searches.isEmpty else { throw ParseError.invalidProfile }
            interface.dns = servers
        }
        var peers: [PeerConfiguration] = []
        var seen = Set<String>()
        for fields in peerValues {
            guard let publicString = fields["publickey"],
                  let publicKey = PublicKey(base64Key: publicString),
                  seen.insert(publicString).inserted,
                  let allowed = parseAddresses(fields["allowedips"]),
                  !allowed.isEmpty else { throw ParseError.invalidProfile }
            var peer = PeerConfiguration(publicKey: publicKey)
            peer.allowedIPs = allowed
            if let value = fields["presharedkey"] {
                guard let secret = PreSharedKey(base64Key: value) else {
                    throw ParseError.invalidProfile
                }
                peer.preSharedKey = secret
            }
            // TwinConnect is a client: a peer without a valid endpoint
            // cannot initiate the connection and must not be shown as ready.
            guard let endpointString = fields["endpoint"],
                  let endpoint = Endpoint(from: endpointString) else {
                throw ParseError.invalidProfile
            }
            peer.endpoint = endpoint
            if let value = fields["persistentkeepalive"] {
                guard let interval = UInt16(value) else { throw ParseError.invalidProfile }
                peer.persistentKeepAlive = interval
            }
            peers.append(peer)
        }
        return TunnelConfiguration(name: "TwinConnect", interface: interface, peers: peers)
    }

    private static func split(_ value: String) -> [String] {
        value.split(separator: ",").map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }

    private static func parseAddresses(_ value: String?) -> [IPAddressRange]? {
        guard let value = value else { return nil }
        let pieces = split(value)
        guard !pieces.isEmpty else { return nil }
        var ranges: [IPAddressRange] = []
        for piece in pieces {
            guard let range = IPAddressRange(from: piece) else { return nil }
            ranges.append(range)
        }
        return ranges
    }
}
#endif
