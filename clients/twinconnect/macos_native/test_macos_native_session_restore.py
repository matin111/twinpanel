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


if __name__ == "__main__":
    unittest.main()
