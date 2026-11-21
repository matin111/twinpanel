// Native, Metal-independent TwinConnect directory and account snapshot.
// Matches the tenant API contract; secrets live in memory only, never logs or defaults.
import Foundation
import Darwin

struct TwinMacNativePingResult {
    let measuredMs: Int?
    let errorCode: String?
}

// ICMP probe semantics match the Windows client: one reply to the public
// literal probe_ip supplied by the *authenticated subscription panel*.
// Never probe hostnames, private/local networks, or arbitrary user input.
// This is a network diagnostic, NOT evidence of a connected VPN tunnel.
enum TwinMacNativePing {
    static func validatedPublicIP(_ address: String) -> String? {
        guard !address.isEmpty, address.count <= 64,
              address == address.trimmingCharacters(in: .whitespacesAndNewlines),
              !address.contains("%") else { return nil }
        var ipv4 = in_addr()
        let isV4 = address.withCString { inet_pton(AF_INET, $0, &ipv4) } == 1
        if isV4 {
            let parts = address.split(separator: ".").compactMap { UInt8($0) }
            guard parts.count == 4 else { return nil }
            let a = parts[0], b = parts[1], c = parts[2]
            guard a > 0, a != 10, a != 127, a < 224,
                  !(a == 169 && b == 254),
                  !(a == 172 && (16...31).contains(b)),
                  !(a == 192 && b == 168),
                  !(a == 100 && (64...127).contains(b)),
                  !(a == 198 && (b == 18 || b == 19)),
                  !(a == 192 && b == 0 && c == 0) else { return nil }
            return address
        }
        var ipv6 = in6_addr()
        guard address.withCString({ inet_pton(AF_INET6, $0, &ipv6) }) == 1 else {
            return nil
        }
        let bytes = withUnsafeBytes(of: &ipv6) { Array($0) }
        // Public global-unicast IPv6 only (2000::/3). Excludes loopback,
        // link-local, unique-local, multicast and IPv4-mapped addresses.
        guard bytes.count == 16, (bytes[0] & 0xE0) == 0x20 else { return nil }
        return address
    }

    static func probe(_ publicIP: String?,
                      completion: @escaping (TwinMacNativePingResult) -> Void) {
        DispatchQueue.global(qos: .utility).async {
            let result = measure(publicIP)
            DispatchQueue.main.async { completion(result) }
        }
    }

    private static func measure(_ address: String?) -> TwinMacNativePingResult {
        guard let ip = address, let safeIP = validatedPublicIP(ip) else {
            return TwinMacNativePingResult(measuredMs: nil,
                                           errorCode: "NO_PROBE_ADDRESS")
        }
        let isV6 = safeIP.contains(":")
        let binary = isV6 ? "/sbin/ping6" : "/sbin/ping"
        guard FileManager.default.isExecutableFile(atPath: binary) else {
            return TwinMacNativePingResult(measuredMs: nil,
                                           errorCode: "PING_PROGRAM_UNAVAILABLE")
        }
        let task = Process()
        task.executableURL = URL(fileURLWithPath: binary)
        // macOS ping's -W is milliseconds, but macOS ping6 uses -W
        // for an unrelated legacy IPv6 query: never pass 1500 to ping6.
        // Use a bounded asynchronous watchdog for both variants.
        // Numeric destination only; never invoke a shell.
        task.arguments = isV6 ? ["-n", "-c", "1", safeIP] :
            ["-n", "-c", "1", "-W", "1500", safeIP]
        let output = Pipe()
        task.standardOutput = output
        task.standardError = output
        do {
            try task.run()
            DispatchQueue.global(qos: .utility).asyncAfter(
                deadline: .now() + .seconds(4)) {
                if task.isRunning { task.terminate() }
            }
            task.waitUntilExit()
        } catch {
            return TwinMacNativePingResult(measuredMs: nil,
                                           errorCode: "PING_PROGRAM_UNAVAILABLE")
        }
        guard task.terminationStatus == 0 else {
            return TwinMacNativePingResult(measuredMs: nil,
                                           errorCode: "ICMP_TIMEOUT_OR_BLOCKED")
        }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        let response = String(decoding: data, as: UTF8.self)
        // Read ICMP RTT from the actual response, not process startup time.
        let pattern = #"time\s*[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms"#
        guard let matcher = try? NSRegularExpression(
            pattern: pattern, options: [.caseInsensitive]),
              let result = matcher.firstMatch(in: response,
                                               range: NSRange(response.startIndex...,
                                                              in: response)),
              let range = Range(result.range(at: 1), in: response),
              let milliseconds = Double(response[range]),
              milliseconds.isFinite, (0...60000).contains(milliseconds) else {
            return TwinMacNativePingResult(measuredMs: nil,
                                           errorCode: "PING_REPLY_UNPARSEABLE")
        }
        return TwinMacNativePingResult(measuredMs: max(1, Int(ceil(milliseconds))),
                                       errorCode: nil)
    }
}

struct TwinMacNativeSession {
    let namespace: String
    let username: String
    let accessToken: String
    let apiOrigin: URL
    let brandName: String
    let accentHex: String
    let backgroundHex: String?
    let cardHex: String?
    let supportURL: URL?
    let renewalURL: URL?
    let websiteURL: URL?
    let logoURL: URL?
}

struct TwinMacNativeProtocol {
    let code: String
    let name: String
    let configured: Bool
}

struct TwinMacNativeServer {
    let id: String
    let name: String
    let country: String
    let online: Bool
    let latencyMs: Int?
    // Validated public IP only, used for a one-reply ICMP diagnostic.
    let probeIP: String?
}

// Mirrors the already defined Flutter ReservedRenewalSnapshot JSON contract.
// Optional reservation data never contaminates current consumption totals.
struct TwinMacReservedRenewal {
    let status: String
    let planName: String
    let trafficBytes: Int64
    let durationDays: Int
    let reservedAt: Date
    var needsReview: Bool { status == "needs_review" }
}

struct TwinMacNativeAccount {
    let status: String
    let usedBytes: Int64
    let limitBytes: Int64
    let expiresAt: Date?
    let activationDurationDays: Int?
    let reservedRenewal: TwinMacReservedRenewal?
}

struct TwinMacNativeSnapshot {
    // A failed panel subrequest must not erase successfully loaded data.
    let protocols: [TwinMacNativeProtocol]
    let servers: [TwinMacNativeServer]
    let account: TwinMacNativeAccount?
    let planName: String?
    let deviceLimit: Int?
    let sectionsLoaded: Set<String>
    let errors: [String: String]
    let isComplete: Bool
}

enum TwinMacNativeError: LocalizedError {
    case failure(String)
    var errorDescription: String? {
        if case .failure(let message) = self { return message }
        return "UNKNOWN_ERROR"
    }
}

final class TwinConnectMacOSNativeDirectory: NSObject, URLSessionTaskDelegate {
    private lazy var transport: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 12
        config.timeoutIntervalForResource = 25
        config.urlCache = nil
        config.httpShouldSetCookies = false
        config.httpCookieAcceptPolicy = .never
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()

    private let canonicalNames: [String: String] = [
        "cisco": "Cisco / OpenConnect",
        "openvpn": "OpenVPN", "wireguard": "WireGuard",
        "l2tp": "L2TP / IPsec", "v2ray": "V2Ray / Xray",
        "hysteria2": "Hysteria2", "tuic": "TUIC", "anytls": "AnyTLS",
        "naive": "NaiveProxy", "shadowtls": "ShadowTLS",
        "snell": "Snell", "socks5": "SOCKS5", "mieru": "Mieru",
        "trusttunnel": "TrustTunnel", "amneziawg": "AmneziaWG",
        "sudoku": "Sudoku"
    ]

    // Never follow redirects with credentials or bearer tokens.
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }

    private func safeOrigin(_ value: String) -> URL? {
        guard let url = URL(string: value),
              let scheme = url.scheme, scheme.lowercased() == "https",
              let host = url.host?.lowercased(), host.contains("."),
              url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil,
              (url.path.isEmpty || url.path == "/"),
              (url.port == nil || url.port == 443),
              !host.hasSuffix(".local"), !host.hasSuffix(".internal"),
              !host.hasSuffix(".localhost"), !host.hasSuffix(".test"),
              !host.hasSuffix(".invalid"), !host.hasSuffix(".example"),
              host != "localhost", !host.contains(".."),
              !host.contains(":") else { return nil }
        let labels = host.split(separator: ".", omittingEmptySubsequences: false)
        guard labels.count >= 2,
              labels.allSatisfy({ label in
                  let part = String(label)
                  return !part.isEmpty && part.count <= 63 &&
                      !part.hasPrefix("-") && !part.hasSuffix("-") &&
                      part.range(of: "^[a-z0-9-]+$", options: .regularExpression) != nil
              }),
              host.range(of: "^[0-9.]+$", options: .regularExpression) == nil
        else { return nil }
        return URL(string: "https://" + host)
    }

    private func userNamespace(_ username: String) -> String? {
        let value = username.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let pattern = "^(TP(?:[A-F0-9]{6}|[A-F0-9]{8}|[A-F0-9]{10}|[A-F0-9]{12}|[A-F0-9]{14}|[A-F0-9]{16}))_(?:R[0-9A-F]+|A)_[A-Z0-9_.-]+$"
        guard let re = try? NSRegularExpression(pattern: pattern),
              let match = re.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)),
              let range = Range(match.range(at: 1), in: value)
        else { return nil }
        return String(value[range])
    }

    private func request(_ url: URL, payload: [String: String]?,
                         bearer: String? = nil, maxBytes: Int = 32768,
                         completion: @escaping (Result<[String: Any], Error>) -> Void) {
        var request = URLRequest(url: url)
        request.httpMethod = payload == nil ? "GET" : "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        if let bearer = bearer {
            request.setValue("Bearer " + bearer, forHTTPHeaderField: "Authorization")
        }
        if let payload = payload {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            guard let json = try? JSONSerialization.data(withJSONObject: payload) else {
                completion(.failure(TwinMacNativeError.failure("INVALID_REQUEST")))
                return
            }
            request.httpBody = json
        }
        transport.dataTask(with: request) { data, response, error in
            let result: Result<[String: Any], Error>
            if error != nil {
                result = .failure(TwinMacNativeError.failure("NETWORK_UNAVAILABLE"))
            } else if let http = response as? HTTPURLResponse, http.statusCode == 200,
                      let data = data, data.count <= maxBytes,
                      let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                result = .success(value)
            } else if let http = response as? HTTPURLResponse {
                // Surface only known, non-sensitive API error identifiers.
                // The service may return PROFILES_NOT_READY as JSON detail;
                // treating every 404 as PANEL_NOT_FOUND concealed the real
                // missing-profile problem during macOS engine setup.
                let safeDetails: Set<String> = [
                    "PROFILES_NOT_READY", "PROTOCOL_NOT_SELECTED",
                    "APP_NOT_AUTHORIZED", "APP_LOGIN_INVALID",
                    "SERVER_NOT_ALLOWED", "PROTOCOL_NOT_ALLOWED",
                    "SUBSCRIPTION_NOT_FOUND", "SUBSCRIPTION_EXPIRED",
                    "SUBSCRIPTION_DISABLED", "DEVICE_LIMIT_REACHED"
                ]
                var detail: String?
                if let data = data, data.count < 8192,
                   let obj = try? JSONSerialization.jsonObject(with: data)
                       as? [String: Any],
                   let candidate = obj["detail"] as? String,
                   safeDetails.contains(candidate) {
                    detail = candidate
                }
                let code: String
                switch http.statusCode {
                case 401: code = "APP_LOGIN_INVALID"
                case 403: code = detail ?? "APP_NOT_AUTHORIZED"
                case 404: code = detail ?? "PANEL_NOT_FOUND"
                case 429: code = "APP_LOGIN_LOCKED"
                case 301, 302, 303, 307, 308: code = "UNSAFE_REDIRECT"
                default: code = "INVALID_SERVER_RESPONSE"
                }
                result = .failure(TwinMacNativeError.failure(code))
            } else {
                result = .failure(TwinMacNativeError.failure("INVALID_SERVER_RESPONSE"))
            }
            DispatchQueue.main.async { completion(result) }
        }.resume()
    }

    private func endpoint(_ origin: URL, _ path: String) -> URL {
        origin.appendingPathComponent(path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
    }

    private func publicURL(_ value: Any?) -> URL? {
        guard let text = value as? String, let url = URL(string: text),
              url.scheme?.lowercased() == "https",
              let host = url.host,
              safeOrigin("https://" + host) != nil,
              url.user == nil, url.password == nil else { return nil }
        return url
    }

    func login(username rawUsername: String, password: String,
               completion: @escaping (Result<TwinMacNativeSession, Error>) -> Void) {
        let username = rawUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let namespace = userNamespace(username),
              !password.isEmpty, password.utf8.count <= 4096 else {
            completion(.failure(TwinMacNativeError.failure("INVALID_APP_CREDENTIALS")))
            return
        }
        let configured = Bundle.main.object(forInfoDictionaryKey: "TwinConnectDirectoryURL")
            as? String ?? "https://panel.matindnspro.sbs"
        guard let vendor = safeOrigin(configured) else {
            completion(.failure(TwinMacNativeError.failure("DIRECTORY_NOT_CONFIGURED")))
            return
        }
        request(endpoint(vendor, "v1/app/resolve/" + namespace), payload: nil) {
            [weak self] discovery in
            guard let self = self else { return }
            switch discovery {
            case .failure(let error): completion(.failure(error))
            case .success(let directory):
                guard (directory["namespace"] as? String)?.uppercased() == namespace,
                      let panelText = directory["api_origin"] as? String,
                      let panel = self.safeOrigin(panelText) else {
                    completion(.failure(TwinMacNativeError.failure("INVALID_DIRECTORY_RESPONSE")))
                    return
                }
                self.request(self.endpoint(panel, "v1/central-app/public/login"),
                             payload: ["username": username, "password": password]) { login in
                    switch login {
                    case .failure(let error): completion(.failure(error))
                    case .success(let info):
                        guard (info["namespace"] as? String)?.uppercased() == namespace,
                              let token = info["session_token"] as? String,
                              token.count >= 40,
                              let brand = info["brand"] as? [String: Any],
                              (brand["namespace"] as? String)?.uppercased() == namespace else {
                            completion(.failure(TwinMacNativeError.failure("INVALID_SESSION_RESPONSE")))
                            return
                        }
                        let owner = (brand["owner_type"] as? String) ?? ""
                        let prefix = (brand["app_username_prefix"] as? String) ?? ""
                        if owner == "reseller" && (prefix.isEmpty || !username.hasPrefix(prefix)) {
                            completion(.failure(TwinMacNativeError.failure("RESELLER_PREFIX_MISMATCH")))
                            return
                        }
                        let name = (brand["brand_name"] as? String) ?? "TwinConnect"
                        let accent = (brand["primary_color"] as? String) ?? "#7C3AED"
                        completion(.success(TwinMacNativeSession(
                            namespace: namespace, username: username,
                            accessToken: token, apiOrigin: panel,
                            brandName: name.isEmpty ? "TwinConnect" : name,
                            accentHex: accent,
                            backgroundHex: brand["background_color"] as? String,
                            cardHex: brand["card_color"] as? String,
                            supportURL: self.publicURL(brand["telegram_url"] ?? brand["website_url"]),
                            renewalURL: self.publicURL(brand["renewal_url"]),
                            websiteURL: self.publicURL(brand["website_url"]),
                            logoURL: self.publicURL(brand["logo_url"])
                        )))
                    }
                }
            }
        }
    }

    // Load only tenant-provided public branding over the same ephemeral
    // redirect-refusing HTTPS transport. Never include app tokens here.
    func loadBrandLogo(_ session: TwinMacNativeSession,
                       completion: @escaping (Data?) -> Void) {
        guard let url = session.logoURL else {
            DispatchQueue.main.async { completion(nil) }
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        transport.dataTask(with: request) { data, response, error in
            let mime = (response as? HTTPURLResponse)?
                .value(forHTTPHeaderField: "Content-Type")?
                .lowercased() ?? ""
            let accepted = mime.hasPrefix("image/png") ||
                mime.hasPrefix("image/jpeg") ||
                mime.hasPrefix("image/webp")
            let imageData: Data? = error == nil &&
                (response as? HTTPURLResponse)?.statusCode == 200 &&
                accepted && (data?.count ?? 0) <= 1_048_576 ?
                    data : nil
            DispatchQueue.main.async { completion(imageData) }
        }.resume()
    }

    // Each endpoint is independent, as in the shared Flutter client.
    // Never gate the server inventory behind /session/plan (404 is possible
    // for historical subscriptions) or hide good account data after a bad
    // protocol response. This method never requests private VPN profiles.
    func loadSnapshot(_ session: TwinMacNativeSession,
                      onUpdate: @escaping (TwinMacNativeSnapshot) -> Void) {
        let panel = session.apiOrigin
        let token = session.accessToken
        var protocols = [TwinMacNativeProtocol]()
        var servers = [TwinMacNativeServer]()
        var account: TwinMacNativeAccount?
        var planName: String?
        var deviceLimit: Int?
        var allowed: Set<String>?
        var verifiedPlan = false
        var loaded = Set<String>()
        var errors = [String: String]()
        var settled = 0

        func publish(_ section: String, failure: String? = nil) {
            settled += 1
            if let error = failure { errors[section] = error }
            else { loaded.insert(section) }
            let filtered: [TwinMacNativeProtocol]
            if verifiedPlan {
                let kind = (planName ?? "").lowercased()
                filtered = protocols.filter { row in
                    let vitory = kind.contains("vitory") ||
                        kind.contains("v2ray") || kind.contains("ویتوری")
                    return (!vitory || row.code == "v2ray" ||
                            row.code == "hysteria2") &&
                        (allowed?.contains(row.code) ?? true)
                }
            } else {
                // The session catalogue is visible for diagnosis, but
                // plan entitlement is not verified and VPN is unavailable.
                filtered = protocols
            }
            onUpdate(TwinMacNativeSnapshot(
                protocols: filtered, servers: servers, account: account,
                planName: planName, deviceLimit: deviceLimit,
                sectionsLoaded: loaded, errors: errors,
                isComplete: settled == 4
            ))
        }

        request(endpoint(panel, "v1/central-app/session/protocols"),
                payload: nil, bearer: token) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .failure(let error):
                publish("protocols", failure: error.localizedDescription)
            case .success(let catalog):
                guard self.validEnvelope(catalog, session.namespace),
                      let entries = catalog["protocols"] as? [[String: Any]],
                      entries.count <= 16 else {
                    publish("protocols", failure: "INVALID_PROTOCOL_CATALOG")
                    return
                }
                var seen = Set<String>()
                var selected = [TwinMacNativeProtocol]()
                for entry in entries {
                    guard let code = entry["code"] as? String,
                          let name = self.canonicalNames[code],
                          seen.insert(code).inserted else {
                        publish("protocols", failure: "INVALID_PROTOCOL_CATALOG")
                        return
                    }
                    if entry["selected"] as? Bool == true {
                        selected.append(TwinMacNativeProtocol(
                            code: code, name: name,
                            configured: entry["config_record_present"] as? Bool == true
                        ))
                    }
                }
                protocols = selected
                publish("protocols")
            }
        }

        request(endpoint(panel, "v1/central-app/session/plan"),
                payload: nil, bearer: token) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .failure(let error):
                publish("plan", failure: error.localizedDescription)
            case .success(let plan):
                guard self.validEnvelope(plan, session.namespace),
                      let category = plan["subscription_type"] as? String,
                      !category.isEmpty, category.count <= 120,
                      let limit = plan["device_limit"] as? Int, limit >= 0,
                      let planId = plan["plan_id"] as? Int, planId >= 0 else {
                    publish("plan", failure: "INVALID_PLAN_CLASSIFICATION")
                    return
                }
                if let rawAllowed = plan["allowed_protocols"] {
                    guard let codes = rawAllowed as? [String],
                          codes.count <= 16,
                          codes.allSatisfy({ self.canonicalNames[$0] != nil }) else {
                        publish("plan", failure: "INVALID_PLAN_PROTOCOLS")
                        return
                    }
                    allowed = Set(codes)
                }
                planName = category
                deviceLimit = limit
                verifiedPlan = true
                publish("plan")
            }
        }

        request(endpoint(panel, "v1/central-app/session/servers"),
                payload: nil, bearer: token, maxBytes: 128 * 1024) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .failure(let error):
                publish("servers", failure: error.localizedDescription)
            case .success(let raw):
                guard self.validEnvelope(raw, session.namespace),
                      let rows = raw["servers"] as? [[String: Any]],
                      rows.count <= 500 else {
                    publish("servers", failure: "INVALID_SERVER_INVENTORY")
                    return
                }
                var nodes = [TwinMacNativeServer]()
                var ids = Set<String>()
                for row in rows {
                    guard let id = row["id"] as? String,
                          id.range(of: "^[0-9]{1,20}$",
                                   options: .regularExpression) != nil,
                          ids.insert(id).inserted,
                          let name = row["name"] as? String,
                          !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                          name.count <= 120,
                          let country = row["country_code"] as? String,
                          !country.isEmpty, country.count <= 8,
                          let online = row["node_online"] as? Bool else {
                        publish("servers", failure: "INVALID_SERVER_INVENTORY")
                        return
                    }
                    let rawLatency = row["latency_ms"] as? Int
                    if let value = rawLatency, !(1...60000).contains(value) {
                        publish("servers", failure: "INVALID_SERVER_INVENTORY")
                        return
                    }
                    let probeIP = (row["probe_ip"] as? String)
                        .flatMap { TwinMacNativePing.validatedPublicIP($0) }
                    nodes.append(TwinMacNativeServer(
                        id: id, name: name, country: country, online: online,
                        latencyMs: rawLatency, probeIP: probeIP
                    ))
                }
                servers = nodes
                publish("servers")
            }
        }

        request(endpoint(panel, "v1/central-app/session/account"),
                payload: nil, bearer: token) { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .failure(let error):
                publish("account", failure: error.localizedDescription)
            case .success(let raw):
                guard self.validEnvelope(raw, session.namespace),
                      let used = raw["traffic_used_bytes"] as? NSNumber,
                      let limit = raw["traffic_limit_bytes"] as? NSNumber,
                      used.int64Value >= 0, limit.int64Value >= 0,
                      let status = raw["status"] as? String else {
                    publish("account", failure: "INVALID_ACCOUNT_SNAPSHOT")
                    return
                }
                var expiry: Date?
                if let dateText = raw["expires_at"] as? String {
                    let parser = ISO8601DateFormatter()
                    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                    expiry = parser.date(from: dateText)
                    if expiry == nil {
                        parser.formatOptions = [.withInternetDateTime]
                        expiry = parser.date(from: dateText)
                    }
                    if expiry == nil {
                        publish("account", failure: "INVALID_ACCOUNT_EXPIRY")
                        return
                    }
                }
                var reserved: TwinMacReservedRenewal?
                if let next = raw["reserved_renewal"] as? [String: Any],
                   let renewalStatus = next["status"] as? String,
                   ["reserved", "needs_review"].contains(renewalStatus),
                   let planName = next["plan_name"] as? String,
                   !planName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                   planName.count <= 160,
                   let traffic = next["traffic_bytes"] as? NSNumber,
                   traffic.int64Value >= 0,
                   let days = next["duration_days"] as? Int, days >= 0,
                   let created = next["reserved_at"] as? String {
                    let formatter = ISO8601DateFormatter()
                    formatter.formatOptions = [.withInternetDateTime,
                                               .withFractionalSeconds]
                    var parsed = formatter.date(from: created)
                    if parsed == nil {
                        formatter.formatOptions = [.withInternetDateTime]
                        parsed = formatter.date(from: created)
                    }
                    if let parsed = parsed {
                        reserved = TwinMacReservedRenewal(
                            status: renewalStatus, planName: planName,
                            trafficBytes: traffic.int64Value,
                            durationDays: days, reservedAt: parsed)
                    }
                }
                let activationDays = raw["activation_duration_days"] as? Int
                account = TwinMacNativeAccount(
                    status: status, usedBytes: used.int64Value,
                    limitBytes: limit.int64Value, expiresAt: expiry,
                    activationDurationDays: activationDays,
                    reservedRenewal: reserved
                )
                publish("account")
            }
        }
    }


    // Strict on-demand native AppKit profile fetch. No full-tunnel claim.
    // Always request current entitlement and inventory before credentials.
    // Only Hysteria2 is enabled until each other outbound has a reviewed
    // config conversion and real transport test.
    func prepareLocalHysteria2(_ session: TwinMacNativeSession,
                               serverID: String,
                               completion: @escaping (Result<Data, Error>) -> Void) {
        guard serverID.range(of: "^[0-9]{1,20}$", options: .regularExpression) != nil
        else {
            completion(.failure(TwinMacNativeError.failure("INVALID_SERVER_ID")))
            return
        }
        let panel = session.apiOrigin
        let token = session.accessToken
        request(endpoint(panel, "v1/central-app/session/protocols"),
                payload: nil, bearer: token) { [weak self] response in
            guard let self = self else { return }
            guard case .success(let catalog) = response,
                  self.validEnvelope(catalog, session.namespace),
                  let rows = catalog["protocols"] as? [[String: Any]],
                  rows.count <= 16,
                  rows.filter({ ($0["code"] as? String) == "hysteria2" &&
                                ($0["selected"] as? Bool) == true &&
                                ($0["config_record_present"] as? Bool) == true }).count == 1
            else {
                completion(.failure(TwinMacNativeError.failure("PROTOCOL_NOT_ALLOWED")))
                return
            }
            self.request(self.endpoint(panel, "v1/central-app/session/servers"),
                         payload: nil, bearer: token, maxBytes: 131072) { inventory in
                guard case .success(let nodes) = inventory,
                      self.validEnvelope(nodes, session.namespace),
                      let all = nodes["servers"] as? [[String: Any]],
                      all.filter({ ($0["id"] as? String) == serverID }).count == 1
                else {
                    completion(.failure(TwinMacNativeError.failure("SERVER_NOT_ALLOWED")))
                    return
                }
                self.request(self.endpoint(panel, "v1/central-app/session/profiles"),
                             payload: ["protocol": "hysteria2"], bearer: token,
                             maxBytes: 1048576) { profiles in
                    guard case .success(let response) = profiles,
                          self.validEnvelope(response, session.namespace),
                          (response["protocol"] as? String) == "hysteria2",
                          let items = response["items"] as? [[String: Any]]
                    else {
                        completion(.failure(TwinMacNativeError.failure("PROFILE_UNAVAILABLE")))
                        return
                    }
                    let candidates = items.filter { item in
                        if let id = item["node_id"] as? String { return id == serverID }
                        if let id = item["node_id"] as? Int { return String(id) == serverID }
                        return false
                    }
                    guard candidates.count == 1,
                          let config = self.localHysteria2Config(candidates[0])
                    else {
                        completion(.failure(TwinMacNativeError.failure("HYSTERIA2_PROFILE_INVALID")))
                        return
                    }
                    completion(.success(config))
                }
            }
        }
    }

    // Prepare an un-routed TUN configuration from the already reviewed,
    // account-entitled Hysteria2 outbound. This does NOT start a VPN.
    // Keeping auto_route false is essential on remote/cloud macOS hosts.
    func prepareUnroutedHysteria2TUN(_ session: TwinMacNativeSession,
                                    serverID: String,
                                    completion: @escaping (Result<Data, Error>) -> Void) {
        prepareLocalHysteria2(session, serverID: serverID) { result in
            switch result {
            case .failure(let error):
                completion(.failure(error))
            case .success(let proxyConfig):
                guard let object = try? JSONSerialization.jsonObject(with: proxyConfig),
                      var config = object as? [String: Any],
                      let outbound = (config["outbounds"] as? [[String: Any]])?.first,
                      outbound["type"] as? String == "hysteria2",
                      outbound["tag"] as? String == "proxy" else {
                    completion(.failure(TwinMacNativeError.failure("TUN_PROFILE_INVALID")))
                    return
                }
                // This interface cannot capture system traffic until explicit
                // privileged routing is added with a recoverable console.
                config["inbounds"] = [[
                    "type": "tun", "tag": "twin-tun",
                    "interface_name": "twinconnect-test",
                    "address": ["172.19.254.1/30"],
                    "auto_route": false,
                    "auto_redirect": false,
                    "strict_route": false,
                    "stack": "system"
                ]]
                guard let encoded = try? JSONSerialization.data(withJSONObject: config)
                else {
                    completion(.failure(TwinMacNativeError.failure("TUN_CONFIG_ENCODING_FAILED")))
                    return
                }
                completion(.success(encoded))
            }
        }
    }

    private func localHysteria2Config(_ item: [String: Any]) -> Data? {
        var value: Any? = item["outbound"] ?? item["singbox_outbound"] ?? item["config"]
        if let text = value as? String, let data = text.data(using: .utf8) {
            value = try? JSONSerialization.jsonObject(with: data)
        }
        guard let outbound = value as? [String: Any],
              outbound["type"] as? String == "hysteria2",
              let host = outbound["server"] as? String,
              !host.isEmpty, host.count <= 255,
              !host.contains("/"), !host.contains(" "),
              let port = outbound["server_port"] as? Int,
              (1...65535).contains(port),
              let password = outbound["password"] as? String,
              !password.isEmpty, password.count <= 4096,
              let tls = outbound["tls"] as? [String: Any],
              tls["enabled"] as? Bool == true,
              tls["insecure"] as? Bool != true,
              tls["disable_sni"] as? Bool != true,
              tls["utls"] == nil,
              tls["reality"] == nil,
              outbound["detour"] == nil,
              outbound["dialer"] == nil,
              outbound["inbounds"] == nil,
              outbound["route"] == nil,
              outbound["dns"] == nil
        else { return nil }

        // Construct allowlisted outbound only: panel cannot inject routes,
        // local listeners, arbitrary commands or certificate bypass.
        var reviewed: [String: Any] = [
            "type": "hysteria2", "tag": "proxy",
            "server": host, "server_port": port,
            "password": password,
            "tls": ["enabled": true,
                    "server_name": (tls["server_name"] as? String) ?? host]
        ]
        // The account API may provide a private CA PEM or explicit SPKI pins.
        // Previously these were accidentally stripped, causing an untrusted
        // certificate error for otherwise legitimate private Hysteria2 nodes.
        // Never permit certificate_path, client_key, or insecure bypass here.
        var tlsSettings = reviewed["tls"] as! [String: Any]
        if let rawCA = tls["certificate"] {
            let lines: [String]
            if let value = rawCA as? String {
                lines = [value]
            } else if let values = rawCA as? [String] {
                lines = values
            } else {
                return nil
            }
            guard !lines.isEmpty, lines.count <= 8,
                  lines.allSatisfy({ value in
                    value.utf8.count <= 16384 &&
                    value.contains("-----BEGIN CERTIFICATE-----") &&
                    value.contains("-----END CERTIFICATE-----") &&
                    !value.contains("PRIVATE KEY")
                  }) else { return nil }
            tlsSettings["certificate"] = lines
        }
        if let rawPins = tls["certificate_public_key_sha256"] {
            guard let pins = rawPins as? [String],
                  !pins.isEmpty, pins.count <= 8,
                  pins.allSatisfy({ value in
                    guard let bytes = Data(base64Encoded: value) else {
                        return false
                    }
                    return bytes.count == 32
                  }) else { return nil }
            tlsSettings["certificate_public_key_sha256"] = pins
        }
        if tls["certificate_path"] != nil ||
           tls["client_key"] != nil ||
           tls["client_key_path"] != nil {
            return nil
        }
        reviewed["tls"] = tlsSettings
        if let obfs = outbound["obfs"] as? [String: Any],
           obfs["type"] as? String == "salamander",
           let key = obfs["password"] as? String, !key.isEmpty {
            reviewed["obfs"] = ["type": "salamander", "password": key]
        } else if outbound["obfs"] != nil { return nil }
        for key in ["up_mbps", "down_mbps"] {
            if let rate = outbound[key] as? Int {
                guard (1...100000).contains(rate) else { return nil }
                reviewed[key] = rate
            } else if outbound[key] != nil { return nil }
        }
        let result: [String: Any] = [
            "log": ["level": "error"],
            "inbounds": [[
                "type": "mixed", "tag": "local-proxy",
                "listen": "127.0.0.1", "listen_port": 17089
            ]],
            "outbounds": [reviewed],
            "route": ["final": "proxy"],
        ]
        return try? JSONSerialization.data(withJSONObject: result)
    }

    private func validEnvelope(_ object: [String: Any], _ namespace: String) -> Bool {
        return (object["schema"] as? Int) == 1 &&
            (object["namespace"] as? String)?.uppercased() == namespace
    }

    deinit { transport.invalidateAndCancel() }
}
