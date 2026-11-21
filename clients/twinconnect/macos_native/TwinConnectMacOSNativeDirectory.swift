// Native, Metal-independent TwinConnect directory and account snapshot.
// Matches the tenant API contract; secrets live in memory only, never logs or defaults.
import Foundation
import Darwin
import Security

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

// A rotating refresh token belongs only in macOS Keychain, never in
// UserDefaults, the filesystem, process arguments, or diagnostic text.
private struct TwinMacSavedRefresh: Codable {
    let username: String
    let namespace: String
    let origin: String
    let token: String
}

private enum TwinMacNativeKeychain {
    private static let service = "com.twinconnect.macos.appkit.refresh.v1"
    private static let account = "active-account"

    private static var key: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    static func load() -> TwinMacSavedRefresh? {
        var query = key
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return try? JSONDecoder().decode(TwinMacSavedRefresh.self, from: data)
    }

    @discardableResult
    static func save(_ value: TwinMacSavedRefresh) -> Bool {
        guard let data = try? JSONEncoder().encode(value) else { return false }
        var item = key
        item[kSecValueData as String] = data
        // Update in place when possible. Removing old login is unnecessary.
        let status = SecItemUpdate(key as CFDictionary,
                                   [kSecValueData as String: data] as CFDictionary)
        if status == errSecSuccess { return true }
        guard status == errSecItemNotFound else { return false }
        return SecItemAdd(item as CFDictionary, nil) == errSecSuccess
    }

    static func clear() {
        SecItemDelete(key as CFDictionary)
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
                        guard let session = self.makeSession(
                            brand: brand, token: token,
                            namespace: namespace, username: username, panel: panel
                        ) else {
                            completion(.failure(TwinMacNativeError.failure("INVALID_SESSION_BRAND")))
                            return
                        }
                        if let refresh = info["refresh_token"] as? String,
                           (40...3000).contains(refresh.count) {
                            let saved = TwinMacSavedRefresh(
                                username: username, namespace: namespace,
                                origin: panel.absoluteString, token: refresh)
                            DispatchQueue.global(qos: .utility).async {
                                _ = TwinMacNativeKeychain.save(saved)
                                DispatchQueue.main.async {
                                    completion(.success(session))
                                }
                            }
                        } else {
                            completion(.success(session))
                        }
                    }
                }
            }
        }
    }

    private func makeSession(brand: [String: Any], token: String,
                             namespace: String, username: String,
                             panel: URL) -> TwinMacNativeSession? {
        guard (brand["namespace"] as? String)?.uppercased() == namespace,
              token.count >= 40 else { return nil }
        let owner = (brand["owner_type"] as? String) ?? ""
        let prefix = (brand["app_username_prefix"] as? String) ?? ""
        guard owner != "reseller" ||
              (!prefix.isEmpty && username.hasPrefix(prefix)) else { return nil }
        let name = (brand["brand_name"] as? String) ?? "TwinConnect"
        return TwinMacNativeSession(
            namespace: namespace, username: username,
            accessToken: token, apiOrigin: panel,
            brandName: name.isEmpty ? "TwinConnect" : name,
            accentHex: (brand["primary_color"] as? String) ?? "#7C3AED",
            backgroundHex: brand["background_color"] as? String,
            cardHex: brand["card_color"] as? String,
            supportURL: publicURL(brand["telegram_url"] ?? brand["website_url"]),
            renewalURL: publicURL(brand["renewal_url"]),
            websiteURL: publicURL(brand["website_url"]),
            logoURL: publicURL(brand["logo_url"])
        )
    }

    // Restores only a rotating refresh token. The account password is never
    // persisted, and the token is validated by the authenticated panel again.
    func restoreSavedSession(
        completion: @escaping (Result<TwinMacNativeSession, Error>) -> Void
    ) {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let saved = TwinMacNativeKeychain.load() else {
                DispatchQueue.main.async {
                    completion(.failure(TwinMacNativeError.failure("NO_SAVED_SESSION")))
                }
                return
            }
            DispatchQueue.main.async {
                guard let self = self,
                      self.userNamespace(saved.username) == saved.namespace,
                      let panel = self.safeOrigin(saved.origin),
                      (40...3000).contains(saved.token.count) else {
                    TwinMacNativeKeychain.clear()
                    completion(.failure(TwinMacNativeError.failure("INVALID_SAVED_SESSION")))
                    return
                }
                self.request(self.endpoint(panel, "v1/central-app/session/refresh"),
                             payload: ["refresh_token": saved.token]) { response in
                    guard case .success(let value) = response,
                          let newToken = value["session_token"] as? String,
                          newToken.count >= 40,
                          let nextRefresh = value["refresh_token"] as? String,
                          (40...3000).contains(nextRefresh.count) else {
                        if case .failure(let error) = response {
                            if ["APP_LOGIN_INVALID", "APP_NOT_AUTHORIZED"].contains(
                                error.localizedDescription) {
                                TwinMacNativeKeychain.clear()
                            }
                            completion(.failure(error))
                        } else {
                            completion(.failure(TwinMacNativeError.failure(
                                "INVALID_REFRESH_RESPONSE")))
                        }
                        return
                    }
                    // Refresh tokens are rotating and the previous token may
                    // already be invalid. Persist the replacement BEFORE the
                    // optional brand fetch, so a transient branding failure
                    // cannot strand the next login attempt.
                    let next = TwinMacSavedRefresh(
                        username: saved.username, namespace: saved.namespace,
                        origin: panel.absoluteString, token: nextRefresh)
                    DispatchQueue.global(qos: .utility).async {
                        let stored = TwinMacNativeKeychain.save(next)
                        DispatchQueue.main.async {
                            guard stored else {
                                completion(.failure(TwinMacNativeError.failure(
                                    "KEYCHAIN_SAVE_FAILED")))
                                return
                            }
                            self.request(self.endpoint(panel, "v1/central-app/session/brand"),
                                         payload: nil, bearer: newToken) { brandResult in
                                guard case .success(let brand) = brandResult,
                                      let session = self.makeSession(
                                        brand: brand, token: newToken,
                                        namespace: saved.namespace,
                                        username: saved.username, panel: panel
                                      ) else {
                                    if case .failure(let error) = brandResult {
                                        completion(.failure(error))
                                    } else {
                                        completion(.failure(TwinMacNativeError.failure(
                                            "INVALID_SESSION_BRAND")))
                                    }
                                    return
                                }
                                completion(.success(session))
                            }
                        }
                    }
                }
            }
        }
    }

    func clearSavedSession() {
        // Deletion must finish before a new account can log in; never leave
        // a queued old-token write racing with a logout.
        TwinMacNativeKeychain.clear()
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

    // Mac proxy mode shares one strictly validated sing-box launcher. Every
    // profile is fetched on demand from the current authenticated tenant and
    // must belong to the selected server. Hysteria2 keeps its existing path.
    func prepareLocalSingBox(_ session: TwinMacNativeSession,
                             serverID: String, protocolCode: String,
                             completion: @escaping (Result<Data, Error>) -> Void) {
        if protocolCode == "hysteria2" {
            prepareLocalHysteria2(session, serverID: serverID, completion: completion)
            return
        }
        let supported: Set<String> = [
            "tuic", "anytls", "socks5", "snell", "naive", "shadowtls", "v2ray"
        ]
        guard supported.contains(protocolCode),
              serverID.range(of: "^[0-9]{1,20}$",
                             options: .regularExpression) != nil else {
            completion(.failure(TwinMacNativeError.failure(
                "LOCAL_PROTOCOL_NOT_SUPPORTED")))
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
                  rows.filter({
                      ($0["code"] as? String) == protocolCode &&
                      ($0["selected"] as? Bool) == true &&
                      ($0["config_record_present"] as? Bool) == true
                  }).count == 1 else {
                completion(.failure(TwinMacNativeError.failure(
                    "PROTOCOL_NOT_ALLOWED")))
                return
            }
            self.request(self.endpoint(panel, "v1/central-app/session/servers"),
                         payload: nil, bearer: token, maxBytes: 131072) { inventory in
                guard case .success(let nodes) = inventory,
                      self.validEnvelope(nodes, session.namespace),
                      let servers = nodes["servers"] as? [[String: Any]],
                      servers.filter({
                          ($0["id"] as? String) == serverID
                      }).count == 1 else {
                    completion(.failure(TwinMacNativeError.failure(
                        "SERVER_NOT_ALLOWED")))
                    return
                }
                self.request(self.endpoint(panel, "v1/central-app/session/profiles"),
                             payload: ["protocol": protocolCode], bearer: token,
                             maxBytes: 1048576) { profiles in
                    guard case .success(let response) = profiles,
                          self.validEnvelope(response, session.namespace),
                          (response["protocol"] as? String) == protocolCode,
                          let items = response["items"] as? [[String: Any]],
                          items.count <= 200 else {
                        completion(.failure(TwinMacNativeError.failure(
                            "PROFILE_UNAVAILABLE")))
                        return
                    }
                    let matches = items.filter { item in
                        if let id = item["node_id"] as? String { return id == serverID }
                        if let id = item["node_id"] as? Int {
                            return String(id) == serverID
                        }
                        return false
                    }
                    if protocolCode == "v2ray" {
                        // The official Xray feed has multiple live inbounds
                        // per node; use the same server_groups projection as
                        // Windows rather than treating one node as one URI.
                        guard let groups = response["server_groups"] as? [[String: Any]],
                              groups.count <= 200,
                              let config = self.reviewedXrayForServer(
                                groups, serverID: serverID) else {
                            completion(.failure(TwinMacNativeError.failure(
                                "XRAY_PROFILE_NOT_READY")))
                            return
                        }
                        completion(.success(config))
                        return
                    }
                    // Distinguish an absent or duplicate node profile
                    // from an unsupported outbound without logging any
                    // credentials or returning private server addresses.
                    guard !matches.isEmpty else {
                        completion(.failure(TwinMacNativeError.failure(
                            "LOCAL_NODE_PROFILE_MISSING")))
                        return
                    }
                    guard matches.count == 1 else {
                        completion(.failure(TwinMacNativeError.failure(
                            "LOCAL_NODE_PROFILE_AMBIGUOUS")))
                        return
                    }
                    guard let config = self.reviewedSingBoxProxyConfig(
                        matches[0], protocolCode: protocolCode) else {
                        completion(.failure(TwinMacNativeError.failure(
                            "LOCAL_PROFILE_INVALID")))
                        return
                    }
                    completion(.success(config))
                }
            }
        }
    }

    // Never execute remote-provided routes, inbounds, local listeners or
    // arbitrary dialer options. Rebuild only known outbound fields.
    // Conservative Xray client: the first supported real inbound for the
    // selected entitled node, preferring TCP TLS then WS TLS then XHTTP Reality.
    // Never use unknown transports, gRPC, custom routes or insecure TLS.
    private func reviewedXrayForServer(_ groups: [[String: Any]],
                                       serverID: String) -> Data? {
        let matching = groups.filter { group in
            if let id = group["node_id"] as? String { return id == serverID }
            if let id = group["node_id"] as? Int { return String(id) == serverID }
            return false
        }
        guard matching.count == 1,
              let profiles = matching[0]["profiles"] as? [[String: Any]],
              profiles.count <= 8 else { return nil }
        let priority = ["tcp_tls", "websocket_tls", "xhttp_reality"]
        for id in priority {
            for row in profiles where (row["id"] as? String) == id {
                guard let uri = row["uri"] as? String,
                      uri.utf8.count <= 8192 else { continue }
                if let result = reviewedXrayVLESSUri(uri, profileID: id) {
                    return result
                }
            }
        }
        return nil
    }

    private func reviewedXrayVLESSUri(_ raw: String,
                                      profileID: String) -> Data? {
        guard let url = URLComponents(string: raw),
              url.scheme == "vless",
              let uuid = url.user,
              UUID(uuidString: uuid) != nil,
              url.password == nil,
              let host = url.host, safeProxyRemoteHost(host),
              host.utf8.count <= 255,
              let port = url.port, (1...65535).contains(port),
              let queryItems = url.queryItems, queryItems.count <= 24
        else { return nil }
        var params = [String: String]()
        for item in queryItems {
            guard params[item.name] == nil, let value = item.value,
                  item.name.utf8.count <= 32,
                  value.utf8.count <= 2048 else { return nil }
            params[item.name] = value
        }
        guard params["encryption"] == "none",
              let transport = params["type"],
              let security = params["security"],
              let sni = params["sni"], !sni.isEmpty,
              sni.utf8.count <= 255, !sni.contains("/"),
              !sni.contains(" "), !sni.contains("@"),
              ["chrome", "firefox", "safari", "edge"].contains(params["fp"] ?? "chrome")
        else { return nil }
        let expected: (String, String)?
        switch profileID {
        case "tcp_tls": expected = ("tcp", "tls")
        case "websocket_tls": expected = ("ws", "tls")
        case "xhttp_reality": expected = ("xhttp", "reality")
        default: expected = nil
        }
        guard let required = expected,
              transport == required.0, security == required.1 else { return nil }
        var stream: [String: Any] = [
            "network": transport, "security": security
        ]
        let fingerprint = params["fp"] ?? "chrome"
        if security == "tls" {
            var tls: [String: Any] = [
                "serverName": sni, "fingerprint": fingerprint,
                "allowInsecure": false
            ]
            if let alpn = params["alpn"], !alpn.isEmpty {
                let values = alpn.split(separator: ",").map(String.init)
                guard values.count <= 8,
                      values.allSatisfy({ !$0.isEmpty && $0.count <= 48 })
                else { return nil }
                tls["alpn"] = values
            }
            stream["tlsSettings"] = tls
        } else {
            guard let pub = params["pbk"],
                  pub.utf8.count >= 40, pub.utf8.count <= 48,
                  pub.range(of: "^[A-Za-z0-9_-]+$",
                            options: .regularExpression) != nil,
                  let sid = params["sid"],
                  !sid.isEmpty, sid.utf8.count <= 16,
                  sid.range(of: "^[A-Fa-f0-9]*$",
                            options: .regularExpression) != nil else { return nil }
            var reality: [String: Any] = [
                "serverName": sni, "fingerprint": fingerprint,
                "publicKey": pub, "shortId": sid
            ]
            if let spider = params["spx"], !spider.isEmpty {
                guard spider.hasPrefix("/"), spider.utf8.count <= 1024
                else { return nil }
                reality["spiderX"] = spider
            }
            stream["realitySettings"] = reality
        }
        if transport == "ws" || transport == "xhttp" {
            guard let path = params["path"],
                  path.hasPrefix("/"), path.utf8.count <= 1024,
                  !path.contains("\r"), !path.contains("\n") else { return nil }
            let hostHeader = params["host"] ?? ""
            guard hostHeader.utf8.count <= 255,
                  !hostHeader.contains("/"), !hostHeader.contains("\r"),
                  !hostHeader.contains("\n") else { return nil }
            if transport == "ws" {
                var ws: [String: Any] = ["path": path]
                if !hostHeader.isEmpty {
                    ws["headers"] = ["Host": hostHeader]
                }
                stream["wsSettings"] = ws
            } else {
                let mode = params["mode"] ?? "stream-one"
                guard ["stream-one", "stream-up", "packet-up"].contains(mode)
                else { return nil }
                var http: [String: Any] = [
                    "path": path, "mode": mode
                ]
                if !hostHeader.isEmpty { http["host"] = hostHeader }
                stream["xhttpSettings"] = http
            }
        }
        let config: [String: Any] = [
            "log": ["loglevel": "warning"],
            "inbounds": [[
                "tag": "twinconnect-loopback",
                "listen": "127.0.0.1", "port": 17089,
                "protocol": "socks", "settings": [
                    "auth": "noauth", "udp": false
                ]
            ]],
            "outbounds": [[
                "tag": "proxy", "protocol": "vless",
                "settings": ["vnext": [[
                    "address": host, "port": port,
                    "users": [[
                        "id": uuid, "encryption": "none"
                    ]]
                ]]],
                "streamSettings": stream
            ]],
            "routing": ["domainStrategy": "AsIs", "rules": []]
        ]
        return try? JSONSerialization.data(withJSONObject: config)
    }

    private func reviewedSingBoxProxyConfig(_ item: [String: Any],
                                            protocolCode: String) -> Data? {
        if protocolCode == "shadowtls" {
            return reviewedShadowTLSProxyConfig(item)
        }
        var source: Any? = item["outbound"] ??
            item["singbox_outbound"] ?? item["config"]
        if let text = source as? String, text.utf8.count < 131072 {
            source = try? JSONSerialization.jsonObject(
                with: Data(text.utf8))
        }
        if let wrapped = source as? [String: Any],
           let all = wrapped["outbounds"] as? [[String: Any]] {
            guard all.count == 1 else { return nil }
            source = all[0]
        }
        guard let outbound = source as? [String: Any],
              let type = outbound["type"] as? String,
              type == (protocolCode == "socks5" ? "socks" : protocolCode),
              outbound["detour"] == nil, outbound["dialer"] == nil,
              outbound["route"] == nil, outbound["dns"] == nil,
              outbound["inbounds"] == nil, outbound["multiplex"] == nil,
              let host = outbound["server"] as? String,
              host.count >= 3, host.utf8.count <= 255,
              !host.contains("/"), !host.contains(" "),
              !host.contains("@"), !host.contains("%"),
              let port = outbound["server_port"] as? Int,
              (1...65535).contains(port) else { return nil }
        // A literal loopback or private IP must not be used as a remote
        // credential-bearing proxy. DNS names are rechecked by the OS.
        if host == "localhost" || host.hasSuffix(".localhost") ||
            host == "0.0.0.0" || host == "::1" { return nil }
        // Require a public IP literal or a conservative DNS name. A private
        // dotted IPv4 value must never pass through the hostname fallback.
        let domainName = host.range(
            of: "^[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)+$",
            options: .regularExpression) != nil &&
            host.rangeOfCharacter(from: .letters) != nil
        guard TwinMacNativePing.validatedPublicIP(host) != nil || domainName
        else { return nil }
        var reviewed: [String: Any] = [
            "type": type, "tag": "proxy",
            "server": host, "server_port": port
        ]
        if protocolCode == "socks5" {
            if let version = outbound["version"] as? String {
                guard version == "5" else { return nil }
            }
            reviewed["version"] = "5"
            let username = outbound["username"] as? String
            let password = outbound["password"] as? String
            guard (username == nil) == (password == nil) else { return nil }
            if let name = username, let pass = password {
                guard !name.isEmpty, !pass.isEmpty,
                      name.utf8.count <= 512, pass.utf8.count <= 2048
                else { return nil }
                reviewed["username"] = name
                reviewed["password"] = pass
            }
        } else if protocolCode == "snell" {
            guard let version = outbound["version"] as? Int,
                  [4, 6].contains(version),
                  let psk = outbound["psk"] as? String,
                  !psk.isEmpty, psk.utf8.count <= 255,
                  version == 4 || psk.utf8.count >= 12 else { return nil }
            reviewed["version"] = version
            reviewed["psk"] = psk
            if let userkey = outbound["userkey"] as? String {
                guard userkey.utf8.count <= 512 else { return nil }
                reviewed["userkey"] = userkey
            }
            if let reuse = outbound["reuse"] as? Bool {
                reviewed["reuse"] = reuse
            }
            if version == 4 {
                if let obfs = outbound["obfs_mode"] as? String {
                    guard ["none", "http"].contains(obfs) else { return nil }
                    reviewed["obfs_mode"] = obfs
                }
                if let obfsHost = outbound["obfs_host"] as? String {
                    guard !obfsHost.isEmpty, obfsHost.utf8.count <= 255,
                          !obfsHost.contains("\n"), !obfsHost.contains("\r")
                    else { return nil }
                    reviewed["obfs_host"] = obfsHost
                }
            } else if let mode = outbound["mode"] as? String {
                guard ["default", "unshaped", "unsafe-raw"].contains(mode)
                else { return nil }
                reviewed["mode"] = mode
            }
        } else if protocolCode == "naive" {
            guard let user = outbound["username"] as? String,
                  let password = outbound["password"] as? String,
                  !user.isEmpty, !password.isEmpty,
                  user.utf8.count <= 1024, password.utf8.count <= 4096,
                  let tls = outbound["tls"] as? [String: Any],
                  let checkedTLS = safeOutboundTLS(tls, server: host),
                  let sni = checkedTLS["server_name"] as? String,
                  let authority = checkedTLS["certificate"] as? [String],
                  !authority.isEmpty,
                  // The panel's Naive managed-CA or custom trust model
                  // delivers PEM, never 'insecure' or a local path.
                  (outbound["insecure_concurrency"] == nil ||
                   (outbound["insecure_concurrency"] as? Int) == 0),
                  outbound["extra_headers"] == nil else { return nil }
            reviewed["username"] = user
            reviewed["password"] = password
            // Naive TLS supports only server_name, certificate,
            // certificate_path and ECH. Do not send the general sing-box
            // tls.enabled field or trust-bypass flags to this outbound.
            reviewed["tls"] = [
                "server_name": sni, "certificate": authority
            ]
            reviewed["insecure_concurrency"] = 0
            for key in ["quic", "udp_over_tcp"] {
                if let flag = outbound[key] as? Bool {
                    if flag { reviewed[key] = true }
                } else if outbound[key] != nil { return nil }
            }
            // The server emits quic_congestion_control='bbr' even when
            // network is TCP and 'quic' is absent. Validate the known
            // value, but only forward it to sing-box for a QUIC profile.
            if let cc = outbound["quic_congestion_control"] as? String {
                guard ["bbr", "bbr2", "cubic", "reno"].contains(cc)
                else { return nil }
                if outbound["quic"] as? Bool == true {
                    reviewed["quic_congestion_control"] = cc
                }
            } else if outbound["quic_congestion_control"] != nil { return nil }
        } else {
            guard let password = outbound["password"] as? String,
                  !password.isEmpty, password.utf8.count <= 4096,
                  let tls = outbound["tls"] as? [String: Any],
                  let checkedTLS = safeOutboundTLS(tls, server: host)
            else { return nil }
            reviewed["password"] = password
            reviewed["tls"] = checkedTLS
            if protocolCode == "tuic" {
                guard let uuid = outbound["uuid"] as? String,
                      UUID(uuidString: uuid) != nil else { return nil }
                reviewed["uuid"] = uuid
                if let cc = outbound["congestion_control"] as? String {
                    guard ["cubic", "bbr", "new_reno"].contains(cc)
                    else { return nil }
                    reviewed["congestion_control"] = cc
                }
                if let udpMode = outbound["udp_relay_mode"] as? String {
                    guard ["native", "quic"].contains(udpMode),
                          outbound["udp_over_stream"] == nil else { return nil }
                    reviewed["udp_relay_mode"] = udpMode
                }
                if let uos = outbound["udp_over_stream"] as? Bool {
                    reviewed["udp_over_stream"] = uos
                }
            } else if protocolCode == "anytls" {
                for key in ["idle_session_check_interval",
                            "idle_session_timeout"] {
                    if let value = outbound[key] as? String {
                        guard value.range(
                            of: "^[1-9][0-9]{0,3}(s|m|h)$",
                            options: .regularExpression) != nil
                        else { return nil }
                        reviewed[key] = value
                    }
                }
                if let idle = outbound["min_idle_session"] as? Int {
                    guard (0...100).contains(idle) else { return nil }
                    reviewed["min_idle_session"] = idle
                }
            }
        }
        let config: [String: Any] = [
            "log": ["level": "error"],
            "inbounds": [[
                "type": "mixed", "tag": "local-proxy",
                "listen": "127.0.0.1", "listen_port": 17089
            ]],
            "outbounds": [reviewed],
            "route": ["final": "proxy"]
        ]
        return try? JSONSerialization.data(withJSONObject: config)
    }

    private func reviewedShadowTLSProxyConfig(_ item: [String: Any])
        -> Data? {
        var source: Any? = item["config"] ??
            item["singbox_outbound"] ?? item["outbound"]
        if let raw = source as? String, raw.utf8.count <= 131072 {
            source = try? JSONSerialization.jsonObject(with: Data(raw.utf8))
        }
        guard let structure = source as? [String: Any],
              let rows = structure["outbounds"] as? [[String: Any]],
              rows.count == 2,
              let ss = rows.first(where: { $0["type"] as? String == "shadowsocks" }),
              let transport = rows.first(where: { $0["type"] as? String == "shadowtls" }),
              let tag = transport["tag"] as? String, !tag.isEmpty,
              let ssTag = ss["tag"] as? String, !ssTag.isEmpty,
              tag != ssTag,
              ss["detour"] as? String == tag,
              (structure["route"] as? [String: Any])?["final"] as? String == ssTag,
              let method = ss["method"] as? String,
              ["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305",
               "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
               "2022-blake3-chacha20-poly1305"].contains(method),
              let ssPassword = ss["password"] as? String,
              !ssPassword.isEmpty, ssPassword.utf8.count <= 4096,
              ss["server"] == nil, ss["server_port"] == nil,
              ss["plugin"] == nil, ss["tls"] == nil,
              Set(ss.keys).isSubset(of: [
                  "type", "tag", "detour", "method", "password"
              ]),
              Set(transport.keys).isSubset(of: [
                  "type", "tag", "version", "server", "server_port",
                  "password", "tls"
              ]),
              transport["version"] as? Int == 3,
              let host = transport["server"] as? String,
              let port = transport["server_port"] as? Int,
              (1...65535).contains(port),
              let transportPassword = transport["password"] as? String,
              !transportPassword.isEmpty,
              transportPassword.utf8.count <= 4096,
              let tls = transport["tls"] as? [String: Any],
              let checkedTLS = safeOutboundTLS(tls, server: host),
              host.utf8.count <= 255, host.utf8.count >= 3,
              !host.contains("/"), !host.contains(" "),
              !host.contains("@"), !host.contains("%"),
              safeProxyRemoteHost(host)
        else { return nil }

        let reviewed: [String: Any] = [
            "log": ["level": "error"],
            "inbounds": [[
                "type": "mixed", "tag": "local-proxy",
                "listen": "127.0.0.1", "listen_port": 17089
            ]],
            "outbounds": [
                [
                    "type": "shadowsocks", "tag": "proxy",
                    "method": method, "password": ssPassword,
                    "detour": "shadowtls-transport"
                ],
                [
                    "type": "shadowtls", "tag": "shadowtls-transport",
                    "version": 3, "server": host, "server_port": port,
                    "password": transportPassword, "tls": checkedTLS
                ]
            ],
            "route": ["final": "proxy"]
        ]
        return try? JSONSerialization.data(withJSONObject: reviewed)
    }

    private func safeProxyRemoteHost(_ host: String) -> Bool {
        let domainName = host.range(
            of: "^[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)+$",
            options: .regularExpression) != nil &&
            host.rangeOfCharacter(from: .letters) != nil
        return TwinMacNativePing.validatedPublicIP(host) != nil || domainName
    }

    private func safeOutboundTLS(_ tls: [String: Any],
                                 server: String) -> [String: Any]? {
        guard tls["enabled"] as? Bool == true,
              tls["insecure"] as? Bool != true,
              tls["disable_sni"] as? Bool != true,
              tls["utls"] == nil, tls["reality"] == nil,
              tls["certificate_path"] == nil,
              tls["client_key"] == nil,
              tls["client_key_path"] == nil else { return nil }
        let sni = (tls["server_name"] as? String) ?? server
        guard !sni.isEmpty, sni.utf8.count <= 255,
              !sni.contains("/"), !sni.contains(" ") else { return nil }
        var checked: [String: Any] = [
            "enabled": true, "server_name": sni
        ]
        if let alpn = tls["alpn"] as? [String] {
            guard alpn.count <= 8, alpn.allSatisfy({
                !$0.isEmpty && $0.utf8.count <= 48
            }) else { return nil }
            checked["alpn"] = alpn
        }
        if let ca = tls["certificate"] {
            let entries: [String]
            if let text = ca as? String { entries = [text] }
            else if let list = ca as? [String] { entries = list }
            else { return nil }
            guard !entries.isEmpty, entries.count <= 8,
                  entries.allSatisfy({
                      $0.utf8.count <= 16384 &&
                      $0.contains("-----BEGIN CERTIFICATE-----") &&
                      $0.contains("-----END CERTIFICATE-----") &&
                      !$0.contains("PRIVATE KEY")
                  }) else { return nil }
            checked["certificate"] = entries
        }
        if let pins = tls["certificate_public_key_sha256"] as? [String] {
            guard !pins.isEmpty, pins.count <= 8,
                  pins.allSatisfy({
                      Data(base64Encoded: $0)?.count == 32
                  }) else { return nil }
            checked["certificate_public_key_sha256"] = pins
        } else if tls["certificate_public_key_sha256"] != nil {
            return nil
        }
        return checked
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
