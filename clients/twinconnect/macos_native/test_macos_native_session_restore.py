"""Offline regression contracts for native AppKit login and TUN error UX."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parent
DIRECTORY = SOURCE / "TwinConnectMacOSNativeDirectory.swift"
DASHBOARD = SOURCE / "TwinConnectMacOSNativeDashboard.swift"


class NativeSessionRestoreTests(unittest.TestCase):
    def test_keychain_not_password_or_userdefaults(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        self.assertIn("import Security", directory)
        for token in ("SecItemAdd", "SecItemCopyMatching", "SecItemUpdate",
                      "SecItemDelete", "kSecClassGenericPassword"):
            self.assertIn(token, directory)
        self.assertIn("refresh_token", directory)
        self.assertIn('payload: ["refresh_token": saved.token]', directory)
        self.assertNotIn('UserDefaults.standard.set(password', directory)
        self.assertNotIn("password: saved.", directory)

    def test_refresh_token_rotation_and_logout(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('v1/central-app/session/refresh', directory)
        self.assertIn('v1/central-app/session/brand', directory)
        self.assertIn("TwinMacNativeKeychain.save(next)", directory)
        self.assertIn("func clearSavedSession()", directory)
        self.assertIn("directory.clearSavedSession()", dashboard)
        self.assertIn("directory.restoreSavedSession", dashboard)
        self.assertIn("private var didAttemptSessionRestore = false", dashboard)

    def test_preflight_surfaces_safe_missing_profile_reason(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('"PROFILES_NOT_READY"', directory)
        self.assertIn('safeDetails.contains(candidate)', directory)
        self.assertIn('case .failure(let error):', dashboard)
        self.assertIn('TUN preflight blocked (', dashboard)
        self.assertIn('Hysteria2 is not entitled for this account.', dashboard)
        self.assertIn('no credentials included', dashboard)
        self.assertNotIn('profile or entitlement unavailable.', dashboard)

    def test_connect_button_is_primary_and_preflight_is_in_settings(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        home = dashboard.split("private func connectPage() -> NSView {", 1)[1].split(
            "private func networkMetric(", 1)[0]
        settings = dashboard.split("private func settingsPage() -> NSView {", 1)[1].split(
            "private func expiryText(", 1)[0]
        self.assertIn('"ϟ    Connect     ›"', home)
        self.assertIn('"ϟ    Disconnect     ›"', home)
        self.assertIn('action: #selector(requestVPNConnection(_:))', home)
        self.assertNotIn('Check TUN readiness', home)
        self.assertIn('"Check TUN readiness"', settings)
        self.assertIn('action: #selector(unavailableConnect(_:))', settings)
        handler = dashboard.split(
            "@objc private func requestVPNConnection(", 1
        )[1].split("@objc private func unavailableConnect(", 1)[0]
        self.assertNotIn("prepareUnroutedHysteria2TUN", handler)
        self.assertIn("prepareLocalSingBox(", handler)
        self.assertIn("startVerifiedLocalProxy(\n                        profile, protocolCode: selectedProtocol)", handler)
        self.assertIn("Local proxy", handler)
        self.assertIn("stopVerifiedLocalProxy()", handler)
        self.assertNotIn("setGlobalProxy", handler)
        self.assertNotIn("startVPNTunnel", handler)
        self.assertIn('self.localProxyStatus = "Disconnected."', dashboard)

    def test_animation_and_real_traffic_metrics_are_proxy_scoped(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        hero = dashboard.split("private final class TwinNativeNetworkFabric", 1)[1].split(
            "class TwinConnectMacOSNativeDashboard", 1)[0]
        self.assertIn("private let halo = CAShapeLayer()", hero)
        self.assertIn("CABasicAnimation", hero)
        self.assertIn("CAKeyframeAnimation(keyPath: \"position\")", hero)
        self.assertIn('dot.add(travel, forKey: "movingNetworkDot")', hero)
        self.assertIn("private var travelDots = [CAShapeLayer]()", hero)
        self.assertIn("updateTravellingDots()", hero)
        self.assertNotIn("These are static AppKit paths", hero)
        self.assertIn("accessibilityDisplayShouldReduceMotion", hero)
        self.assertIn("fabric.proxyActive = localProxyActive", dashboard)
        self.assertIn('runLocalManager(["traffic"], root: root)', dashboard)
        self.assertIn("private func refreshTrafficMetrics()", dashboard)
        self.assertIn("Timer(timeInterval: 1.0, repeats: true)", dashboard)
        self.assertIn("private var recentTraffic =", dashboard)
        self.assertIn("now.timeIntervalSince($0.at) > 3.0", dashboard)
        self.assertIn("Double(down - baseline.download) / seconds", dashboard)
        self.assertIn("Double(up - baseline.upload) / seconds", dashboard)
        self.assertIn("downloadedTotalText?.stringValue", dashboard)
        self.assertIn("downloadSpeedText?.stringValue", dashboard)
        self.assertIn("private final class TwinNativeTrafficSparkline", dashboard)
        self.assertIn("downloadChart?.samples = self.downloadHistory", dashboard)
        self.assertIn("uploadChart?.samples = self.uploadHistory", dashboard)
        self.assertIn("self.downloadHistory.append(downRate)", dashboard)
        self.assertIn("self.uploadHistory.append(upRate)", dashboard)
        self.assertIn("self.downloadHistory.removeFirst()", dashboard)
        self.assertIn("self.uploadHistory.removeFirst()", dashboard)
        self.assertIn("if localProxyActive {", dashboard)
        self.assertIn("connect.setAccentGradient(", dashboard)
        self.assertIn("self.trafficPollBusy = false", dashboard)
        self.assertIn("localProxyGeneration == generation", dashboard)
        self.assertNotIn("Local SOCKS proxy active (not VPN)", dashboard)
        self.assertNotIn("subtitle: pingDetails(selected)", dashboard)
        self.assertIn('connectedProtocolTitle + " active"', dashboard)
        self.assertIn('"ϟ    Connect     ›"', dashboard)
        monitor = dashboard.split("private func refreshTrafficMetrics()", 1)[1].split(
            "private func runLocalManager(", 1)[0]
        self.assertNotIn("self.view = self.build()", monitor)

    def test_connected_protocol_label_matches_verified_engine_not_picker(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("private var verifiedProxyProtocol: String?", dashboard)
        self.assertIn("private var connectedProtocolTitle: String", dashboard)
        for code, label in [
            ("hysteria2", "Hysteria2"),
            ("tuic", "TUIC"),
            ("anytls", "AnyTLS"),
            ("socks5", "SOCKS5"),
            ("snell", "Snell"),
            ("naive", "Naive"),
            ("shadowtls", "ShadowTLS"),
            ("v2ray", "V2Ray"),
        ]:
            self.assertIn(f'case "{code}": return "{label}"', dashboard)
        self.assertIn('connectedProtocolTitle + " · Proxy"', dashboard)
        self.assertIn('connectedProtocolTitle + " active"', dashboard)
        self.assertIn('connectedProtocolTitle + " session"', dashboard)
        self.assertIn('self.verifiedProxyProtocol = outcome.0 ?', dashboard)
        self.assertIn('selectedProtocol : nil', dashboard)
        self.assertIn('self.verifiedProxyProtocol = nil', dashboard)
        self.assertIn('verifiedProxyProtocol = nil', dashboard)
        self.assertIn('"Proxy verified protocol: " + (verifiedProxyProtocol ?? "none")',
                      dashboard)
        self.assertIn('localProxyActive ? "ϟ    Disconnect', dashboard)
        self.assertNotIn('localProxyActive ? "Proxy" : "Disconnected"', dashboard)

    def test_entitled_singbox_protocols_bound_to_selected_server(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        for code in ('"hysteria2"', '"tuic"', '"anytls"',
                     '"socks5"', '"snell"', '"naive"', '"shadowtls"', '"v2ray"'):
            self.assertIn(code, dashboard)
        self.assertIn("func prepareLocalSingBox(", directory)
        self.assertIn('payload: ["protocol": protocolCode]', directory)
        self.assertIn('self.validEnvelope(response, session.namespace)', directory)
        self.assertIn('($0["selected"] as? Bool) == true', directory)
        self.assertIn('($0["config_record_present"] as? Bool) == true', directory)
        self.assertIn('($0["id"] as? String) == serverID', directory)
        self.assertIn('item["node_id"]', directory)
        self.assertIn('guard matches.count == 1', directory)
        self.assertIn('type == (protocolCode == "socks5" ? "socks" : protocolCode)', directory)
        self.assertIn('"listen": "127.0.0.1", "listen_port": 17089', directory)
        self.assertIn('"route": ["final": "proxy"]', directory)
        self.assertIn('outbound["detour"] == nil', directory)
        self.assertIn('outbound["dns"] == nil', directory)
        self.assertIn('tls["insecure"] as? Bool != true', directory)
        self.assertIn('TwinMacNativePing.validatedPublicIP(host)', directory)
        self.assertIn('domainName', directory)
        self.assertIn('UUID(uuidString: uuid)', directory)
        self.assertIn('reviewed["version"] = "5"', directory)
        self.assertIn('let version = outbound["version"] as? Int', directory)
        self.assertIn('safeOutboundTLS(tls, server: host)', directory)
        self.assertIn('"LOCAL_PROFILE_INVALID"', directory)
        self.assertIn('"SERVER_NOT_ALLOWED"', directory)
        self.assertIn('"PROTOCOL_NOT_ALLOWED"', directory)
        self.assertIn('"PROFILES_NOT_READY"', directory)

    def test_naive_and_shadowtls_are_strict_verified_local_only(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('"naive", "shadowtls"', directory)
        self.assertIn('protocolCode == "naive"', directory)
        self.assertIn('outbound["insecure_concurrency"]', directory)
        self.assertIn('outbound["extra_headers"] == nil', directory)
        self.assertIn('reviewed["insecure_concurrency"] = 0', directory)
        self.assertIn('reviewedShadowTLSProxyConfig(item)', directory)
        self.assertIn('rows.count == 2', directory)
        self.assertIn('ss["detour"] as? String == tag', directory)
        self.assertIn('"type": "shadowsocks", "tag": "proxy"', directory)
        self.assertIn('"type": "shadowtls", "tag": "shadowtls-transport"', directory)
        self.assertIn('"route": ["final": "proxy"]', directory)
        self.assertIn('safeProxyRemoteHost(host)', directory)
        self.assertIn('tls["insecure"] as? Bool != true', directory)
        self.assertIn('case "naive": return "Naive"', dashboard)
        self.assertIn('case "shadowtls": return "ShadowTLS"', dashboard)

    def test_xray_profiles_only_from_authorized_node_and_3_known_inbounds(self):
        directory = DIRECTORY.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('"naive", "shadowtls", "v2ray"', directory)
        self.assertIn('response["server_groups"]', directory)
        self.assertIn('reviewedXrayForServer(', directory)
        self.assertIn('groups.filter { group in', directory)
        self.assertIn('matching.count == 1', directory)
        for inbound in ("tcp_tls", "websocket_tls", "xhttp_reality"):
            self.assertIn('"' + inbound + '"', directory)
        self.assertIn('url.scheme == "vless"', directory)
        self.assertIn('UUID(uuidString: uuid)', directory)
        self.assertIn('let required = expected', directory)
        self.assertIn('let security = params["security"]', directory)
        self.assertIn('let transport = params["type"]', directory)
        self.assertIn('let sni = params["sni"]', directory)
        self.assertIn('queryItems.count <= 24', directory)
        self.assertIn('"protocol": "socks"', directory)
        self.assertIn('"listen": "127.0.0.1", "port": 17089', directory)
        self.assertIn('"protocol": "vless"', directory)
        self.assertIn('"network": transport', directory)
        self.assertIn('"publicKey": pub, "shortId": sid', directory)
        self.assertIn('safeProxyRemoteHost(host)', directory)
        self.assertIn('case "v2ray": return "V2Ray"', dashboard)

    def test_connect_reuses_existing_verified_process_control(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        handler = dashboard.split(
            "@objc private func requestVPNConnection(", 1
        )[1].split("/// An actual remote HTTPS request", 1)[0]
        self.assertIn('enabled.contains(selectedProtocol)', handler)
        self.assertIn('selectedProtocol && $0.configured', handler)
        self.assertIn('directory.prepareLocalSingBox(', handler)
        self.assertIn('startVerifiedLocalProxy(', handler)
        self.assertIn('profile, protocolCode: selectedProtocol', handler)
        self.assertIn('stopVerifiedLocalProxy()', handler)
        self.assertIn('self.startVerifiedLocalProxy(', handler)
        self.assertIn('self.localProxyActive = outcome.0', handler)
        self.assertNotIn('startVPNTunnel', handler)


if __name__ == "__main__":
    unittest.main()
