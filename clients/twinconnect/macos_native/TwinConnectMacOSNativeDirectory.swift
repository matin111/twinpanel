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

struct TwinMacNativeAccount {
    let status: String
    let usedBytes: Int64
    let limitBytes: Int64
    let expiresAt: Date?
}

struct TwinMacNativeSnapshot {
    let protocols: [TwinMacNativeProtocol]
    let servers: [TwinMacNativeServer]
    let account: TwinMacNativeAccount
    let planName: String
    let deviceLimit: Int
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

    func loadSnapshot(_ session: TwinMacNativeSession,
                      completion: @escaping (Result<TwinMacNativeSnapshot, Error>) -> Void) {
        let panel = session.apiOrigin
        let token = session.accessToken
        request(endpoint(panel, "v1/central-app/session/protocols"),
                payload: nil, bearer: token) { [weak self] result in
            guard let self = self else { return }
            guard case .success(let catalog) = result else {
                if case .failure(let error) = result { completion(.failure(error)) }
                return
            }
            guard self.validEnvelope(catalog, session.namespace),
                  let entries = catalog["protocols"] as? [[String: Any]],
                  entries.count <= 16 else {
                completion(.failure(TwinMacNativeError.failure("INVALID_PROTOCOL_CATALOG")))
                return
            }
            var selected = [TwinMacNativeProtocol]()
            var seen = Set<String>()
            for entry in entries {
                guard let code = entry["code"] as? String,
                      let name = self.canonicalNames[code],
                      seen.insert(code).inserted else {
                    completion(.failure(TwinMacNativeError.failure("INVALID_PROTOCOL_CATALOG")))
                    return
                }
                if entry["selected"] as? Bool == true {
                    selected.append(TwinMacNativeProtocol(
                        code: code, name: name,
                        configured: entry["config_record_present"] as? Bool == true
                    ))
                }
            }
            self.request(self.endpoint(panel, "v1/central-app/session/plan"),
                         payload: nil, bearer: token) { planResult in
                guard case .success(let plan) = planResult,
                      self.validEnvelope(plan, session.namespace),
                      let category = plan["subscription_type"] as? String,
                      let deviceLimit = plan["device_limit"] as? Int,
                      deviceLimit >= 0,
                      let _ = plan["plan_id"] as? Int else {
                    completion(.failure(TwinMacNativeError.failure("PLAN_UNAVAILABLE")))
                    return
                }
                if let allowed = plan["allowed_protocols"] {
                    guard let codes = allowed as? [String],
                          codes.count <= 16,
                          codes.allSatisfy({ self.canonicalNames[$0] != nil }) else {
                        completion(.failure(TwinMacNativeError.failure("INVALID_PLAN_PROTOCOLS")))
                        return
                    }
                    let whitelist = Set(codes)
                    selected = selected.filter { whitelist.contains($0.code) }
                }
                let type = category.lowercased()
                if type.contains("vitory") || type.contains("v2ray") ||
                    type.contains("ویتوری") {
                    selected = selected.filter {
                        $0.code == "v2ray" || $0.code == "hysteria2"
                    }
                }
                self.request(self.endpoint(panel, "v1/central-app/session/servers"),
                             payload: nil, bearer: token, maxBytes: 128 * 1024) { serverResult in
                    guard case .success(let raw) = serverResult,
                          self.validEnvelope(raw, session.namespace),
                          let rows = raw["servers"] as? [[String: Any]],
                          rows.count <= 500 else {
                        completion(.failure(TwinMacNativeError.failure("SERVER_INVENTORY_UNAVAILABLE")))
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
                              !name.isEmpty, name.count <= 120,
                              let country = row["country_code"] as? String,
                              !country.isEmpty, country.count <= 8,
                              let online = row["node_online"] as? Bool else {
                            completion(.failure(TwinMacNativeError.failure("INVALID_SERVER_INVENTORY")))
                            return
                        }
                        let rawLatency = row["latency_ms"] as? Int
                        let latency = rawLatency.flatMap { (1...60000).contains($0) ? $0 : nil }
                        nodes.append(TwinMacNativeServer(id: id, name: name,
                             country: country, online: online, latencyMs: latency))
                    }
                    self.request(self.endpoint(panel, "v1/central-app/session/account"),
                                 payload: nil, bearer: token) { accountResult in
                        guard case .success(let account) = accountResult,
                              self.validEnvelope(account, session.namespace),
                              let used = account["traffic_used_bytes"] as? NSNumber,
                              let limit = account["traffic_limit_bytes"] as? NSNumber,
                              used.int64Value >= 0, limit.int64Value >= 0,
                              let status = account["status"] as? String else {
                            completion(.failure(TwinMacNativeError.failure("ACCOUNT_UNAVAILABLE")))
                            return
                        }
                        var expiry: Date?
                        if let dateText = account["expires_at"] as? String {
                            expiry = ISO8601DateFormatter().date(from: dateText)
                            if expiry == nil {
                                completion(.failure(TwinMacNativeError.failure("INVALID_ACCOUNT_EXPIRY")))
                                return
                            }
                        }
                        completion(.success(TwinMacNativeSnapshot(
                            protocols: selected, servers: nodes,
                            account: TwinMacNativeAccount(status: status,
                               usedBytes: used.int64Value, limitBytes: limit.int64Value,
                               expiresAt: expiry),
                            planName: category, deviceLimit: deviceLimit
                        )))
                    }
                }
            }
        }
    }

    private func validEnvelope(_ object: [String: Any], _ namespace: String) -> Bool {
        return (object["schema"] as? Int) == 1 &&
            (object["namespace"] as? String)?.uppercased() == namespace
    }

    deinit { transport.invalidateAndCancel() }
}
