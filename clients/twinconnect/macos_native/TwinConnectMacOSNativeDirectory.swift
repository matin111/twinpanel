// Native, Metal-independent TwinConnect directory and account snapshot.
// Matches the tenant API contract; secrets live in memory only, never logs or defaults.
import Foundation

struct TwinMacNativeSession {
    let namespace: String
    let username: String
    let accessToken: String
    let apiOrigin: URL
    let brandName: String
    let accentHex: String
    let supportURL: URL?
    let renewalURL: URL?
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
                let code: String
                switch http.statusCode {
                case 401: code = "APP_LOGIN_INVALID"
                case 403: code = "APP_NOT_AUTHORIZED"
                case 404: code = "PANEL_NOT_FOUND"
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
                            supportURL: self.publicURL(brand["telegram_url"] ?? brand["website_url"]),
                            renewalURL: self.publicURL(brand["renewal_url"])
                        )))
                    }
                }
            }
        }
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
                    nodes.append(TwinMacNativeServer(
                        id: id, name: name, country: country, online: online,
                        latencyMs: rawLatency
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

    private func validEnvelope(_ object: [String: Any], _ namespace: String) -> Bool {
        return (object["schema"] as? Int) == 1 &&
            (object["namespace"] as? String)?.uppercased() == namespace
    }

    deinit { transport.invalidateAndCancel() }
}
