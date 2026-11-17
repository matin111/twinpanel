import Foundation
import NetworkExtension

/// Strict preflight for Mieru's upstream egress route. PacketTunnel must
/// exclude the pinned upstream address from its TUN route before starting
/// Mieru. Building a route object is NOT proof the OS has applied it.
///
/// Only one already-resolved public IPv4 endpoint is accepted. Do not
/// silently fall back to DNS or a default/direct outbound.
enum TwinConnectMacMieruEndpointRoute {
    enum ValidationError: Error {
        case invalidProfile
        case endpointNotPublic
        case endpointNotPinned
    }

    struct Plan {
        let endpoint: String
        let excludedRoute: NEIPv4Route
    }

    private static func publicIPv4(_ value: String) -> Bool {
        let parts = value.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4 else { return false }
        var bytes = [Int]()
        for part in parts {
            guard !part.isEmpty, part.count <= 3,
                  (part.count == 1 || part.first != "0"),
                  part.allSatisfy({ $0.isASCII && $0.isNumber }),
                  let number = Int(part), (0...255).contains(number) else {
                return false
            }
            bytes.append(number)
        }
        let a = bytes[0], b = bytes[1], c = bytes[2]
        // Private, loopback, link-local, shared, documentation, benchmark,
        // reserved, multicast and special-purpose IPv4 addresses.
        if a == 0 || a == 10 || a == 127 || a >= 224 ||
           (a == 100 && (64...127).contains(b)) ||
           (a == 169 && b == 254) ||
           (a == 172 && (16...31).contains(b)) ||
           (a == 192 && b == 168) ||
           (a == 192 && b == 0 && c == 0) ||
           (a == 192 && b == 0 && c == 2) ||
           (a == 192 && b == 88 && c == 99) ||
           (a == 198 && (b == 18 || b == 19)) ||
           (a == 198 && b == 51 && c == 100) ||
           (a == 203 && b == 0 && c == 113) ||
           (a == 192 && b == 0 && c == 0) {
            return false
        }
        return true
    }

    static func plan(from core: [String: Any]) throws -> Plan {
        guard let profiles = core["profiles"] as? [[String: Any]],
              profiles.count == 1,
              let profile = profiles.first,
              let active = core["activeProfile"] as? String,
              !active.isEmpty,
              profile["profileName"] as? String == active,
              let servers = profile["servers"] as? [[String: Any]],
              servers.count == 1,
              let server = servers.first,
              let rawAddress = server["ipAddress"] as? String,
              server["domainName"] as? String == "",
              let bindings = server["portBindings"] as? [[String: Any]],
              !bindings.isEmpty, bindings.count <= 32 else {
            throw ValidationError.invalidProfile
        }

        guard publicIPv4(rawAddress) else {
            throw ValidationError.endpointNotPublic
        }

        for binding in bindings {
            guard let proto = binding["protocol"] as? String,
                  proto == "TCP" || proto == "UDP" else {
                throw ValidationError.invalidProfile
            }
            if let port = binding["port"] as? Int {
                guard (1...65535).contains(port),
                      binding["portRange"] == nil else {
                    throw ValidationError.invalidProfile
                }
            } else if let range = binding["portRange"] as? String {
                let parts = range.split(separator: "-", omittingEmptySubsequences: false)
                guard parts.count == 2,
                      let low = Int(parts[0]), let high = Int(parts[1]),
                      (1...65535).contains(low),
                      (1...65535).contains(high), low <= high else {
                    throw ValidationError.invalidProfile
                }
            } else {
                throw ValidationError.invalidProfile
            }
        }

        return Plan(
            endpoint: rawAddress,
            excludedRoute: NEIPv4Route(
                destinationAddress: rawAddress,
                subnetMask: "255.255.255.255"
            )
        )
    }
}
