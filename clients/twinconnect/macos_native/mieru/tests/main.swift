import Foundation
import NetworkExtension

func fail(_ message: String) -> Never {
    fputs("Mieru route test failed: \(message)\n", stderr)
    exit(1)
}

func endpoint(_ ip: String, domain: String = "") -> [String: Any] {
    [
        "profiles": [[
            "profileName": "synthetic-user",
            "servers": [[
                "ipAddress": ip,
                "domainName": domain,
                "portBindings": [
                    ["protocol": "TCP", "port": 24567],
                    ["protocol": "UDP", "portRange": "24000-24005"]
                ]
            ]]
        ]],
        "activeProfile": "synthetic-user"
    ]
}

func expectValid(_ ip: String) {
    do {
        let plan = try TwinConnectMacMieruEndpointRoute.plan(
            from: endpoint(ip))
        let settings = try TwinConnectMacMieruEndpointRoute
            .tunnelSettings(for: plan)
        if plan.endpoint != ip ||
            plan.excludedRoute.destinationAddress != ip ||
            plan.excludedRoute.destinationSubnetMask !=
                "255.255.255.255" ||
            settings.tunnelRemoteAddress != ip ||
            settings.ipv4Settings?.includedRoutes?.count != 1 ||
            settings.ipv4Settings?.excludedRoutes?.count != 1 ||
            settings.ipv4Settings?.excludedRoutes?.first?
                .destinationAddress != ip ||
            settings.ipv4Settings?.excludedRoutes?.first?
                .destinationSubnetMask != "255.255.255.255" ||
            settings.ipv6Settings?.includedRoutes?.count != 1 ||
            settings.ipv6Settings?.excludedRoutes?.count != 0 ||
            settings.dnsSettings?.matchDomains != [""] {
            fail("invalid Network Extension route/DNS policy for \(ip)")
        }
    } catch {
        fail("rejected public endpoint \(ip)")
    }
}

func expectRejected(_ payload: [String: Any]) {
    do {
        _ = try TwinConnectMacMieruEndpointRoute.plan(from: payload)
        fail("accepted untrusted Mieru endpoint")
    } catch {
        // Expected fail closed.
    }
}

expectValid("1.1.1.1")
expectValid("8.8.8.8")

for ip in ["127.0.0.1", "10.1.2.3", "172.16.0.1",
           "192.168.10.5", "100.64.0.4", "169.254.1.1",
           "198.18.0.5", "192.0.2.1", "203.0.113.4",
           "0.1.2.3", "224.0.0.1", "255.255.255.255",
           "001.1.1.1", "1.1.1", "1.1.1.256"] {
    expectRejected(endpoint(ip))
}

expectRejected(endpoint("1.1.1.1", domain: "example.org"))
var badPort = endpoint("1.1.1.1")
var profiles = badPort["profiles"] as! [[String: Any]]
var servers = profiles[0]["servers"] as! [[String: Any]]
servers[0]["portBindings"] = [["protocol": "TCP", "port": 0]]
profiles[0]["servers"] = servers
badPort["profiles"] = profiles
expectRejected(badPort)

print("Mieru macOS public endpoint and /32 route preflight passed")
