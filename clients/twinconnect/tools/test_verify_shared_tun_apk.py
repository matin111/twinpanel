"""Regression fixtures for the final, merged Android VPN manifest."""

import unittest

from verify_shared_tun_apk import manifest_services, verify


SHARED = '''
E: manifest (line=2)
  E: application (line=15)
    E: service (line=18)
      A: android:name(0x01010003)="com.twinpanel.twinconnect.SharedTunVpnService" (Raw: ".SharedTunVpnService")
      A: android:exported(0x01010010)=(type 0x12)0xffffffff
      A: android:permission(0x01010006)="android.permission.BIND_VPN_SERVICE"
      E: intent-filter (line=22)
        E: action (line=23)
          A: android:name(0x01010003)="android.net.VpnService"
    E: service (line=28)
      A: android:name(0x01010003)="com.twinpanel.twinconnect.AndroidTrafficGuardService"
      A: android:exported(0x01010010)=(type 0x12)0x0
'''

SECOND = '''
    E: service (line=29)
      A: android:name(0x01010003)="com.github.tfox.flutter_vless.xray.service.XrayVPNService"
      A: android:permission(0x01010006)="android.permission.BIND_VPN_SERVICE"
      E: intent-filter (line=30)
        E: action (line=31)
          A: android:name(0x01010003)="android.net.VpnService"
'''


class VerifyAndroidVpnManifestTests(unittest.TestCase):
    def test_single_owner_accepted(self) -> None:
        verify(SHARED)

    def test_second_core_advertised_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "got 2"):
            verify(SHARED + SECOND)

    def test_hidden_owner_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not exported"):
            verify(SHARED.replace("0xffffffff", "0x0"))

    def test_unprotected_owner_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "lacks android.permission"):
            verify(SHARED.replace("android.permission.BIND_VPN_SERVICE", "android.permission.INTERNET"))

    def test_action_not_mistaken_for_service_name(self) -> None:
        services = manifest_services(SHARED)
        self.assertEqual(services[0]["name"], "com.twinpanel.twinconnect.SharedTunVpnService")
        self.assertEqual(len(services), 2)


if __name__ == "__main__":
    unittest.main()
