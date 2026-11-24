"""Ensure macOS V2Ray rejects only real entitlement failures."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("TwinConnectMacOSNativeDirectory.swift").read_text()


class V2RayAuthorizationDiagnostics(unittest.TestCase):
    def test_network_or_session_errors_are_preserved(self):
        start = SOURCE.index('func prepareLocalSingBox(')
        end = SOURCE.index('self.request(self.endpoint(panel, "v1/central-app/session/servers")', start)
        section = SOURCE[start:end]
        self.assertIn('case .failure(let error):', section)
        self.assertIn('completion(.failure(error))', section)
        self.assertIn('"PROTOCOL_CATALOG_INVALID"', section)

    def test_entitlement_and_provisioning_are_distinct(self):
        start = SOURCE.index('func prepareLocalSingBox(')
        end = SOURCE.index('self.request(self.endpoint(panel, "v1/central-app/session/servers")', start)
        section = SOURCE[start:end]
        self.assertIn('let allowed = matching[0]["selected"] as? Bool', section)
        self.assertIn('let configured = matching[0]["config_record_present"] as? Bool', section)
        self.assertIn('guard allowed else', section)
        self.assertIn('"PROTOCOL_NOT_SELECTED"', section)
        self.assertIn('guard configured else', section)
        self.assertIn('"PROTOCOL_CONFIG_MISSING"', section)
        self.assertNotIn('"PROTOCOL_NOT_ALLOWED"', section)

    def test_profile_server_errors_are_not_relabelled_as_denied(self):
        start = SOURCE.index('func prepareLocalSingBox(')
        section = SOURCE[start:SOURCE.index('// L2TP/IPsec manual credentials:', start)]
        self.assertIn('case .failure(let error):', section)
        self.assertIn('"PROFILE_RESPONSE_INVALID"', section)
        self.assertNotIn('"PROFILE_UNAVAILABLE"', section)
        index = SOURCE[SOURCE.index('func loadXrayInboundIndex('):start]
        self.assertIn('case .failure(let error):', index)
        self.assertIn('"XRAY_PROFILE_RESPONSE_INVALID"', index)

    def test_no_profile_requests_without_real_auth(self):
        self.assertIn('guard allowed else', SOURCE)
        self.assertIn('guard configured else', SOURCE)
        self.assertIn('payload: ["protocol": protocolCode]', SOURCE)

if __name__ == "__main__":
    unittest.main()