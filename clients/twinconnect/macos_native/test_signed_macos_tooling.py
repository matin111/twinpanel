#!/usr/bin/env python3
"""Offline tests for signing preparation. Dummy Team IDs, no Apple secrets."""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parent / "prepare_signed_macos_candidate.py"
TEAM = "ABCDEFGHIJ"
GROUP = TEAM + ".com.twinpanel.twinconnect.shared"


class SignedMacTestCandidate(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "client"
        self.native = self.root / "macos_native"
        self.runner = self.root / "macos" / "Runner"
        self.native.mkdir(parents=True)
        self.runner.mkdir(parents=True)
        shutil.copy2(SCRIPT, self.native / SCRIPT.name)
        project = self.root / "macos" / "Runner.xcodeproj" / "project.pbxproj"
        project.parent.mkdir(parents=True)
        project.write_text("PacketTunnel and Libbox.framework exist", encoding="utf-8")
        framework_info = self.native / "build/libbox/Libbox.xcframework/Info.plist"
        framework_info.parent.mkdir(parents=True)
        framework_info.write_bytes(plistlib.dumps({"AvailableLibraries": []}))
        for file in (
            self.runner / "Release.entitlements",
            self.runner / "DebugProfile.entitlements",
            self.native / "PacketTunnel.entitlements",
        ):
            file.write_bytes(plistlib.dumps({"com.apple.security.app-sandbox": True}))
        (self.runner / "Info.plist").write_bytes(
            plistlib.dumps({"CFBundleName": "twinconnect"})
        )
        (self.native / "PacketTunnel-Info.plist").write_bytes(
            plistlib.dumps({"TwinConnectProtocolBackendLinked": False})
        )

    def execute(self, team: str = "", enable: str = "") -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["TWINCONNECT_APPLE_TEAM_ID"] = team
        env["TWINCONNECT_ENABLE_SIGNED_LIBBOX_TEST"] = enable
        return subprocess.run(
            [sys.executable, str(self.native / SCRIPT.name)],
            env=env, capture_output=True, text=True, check=False,
        )

    @staticmethod
    def read(path: Path) -> dict:
        with path.open("rb") as handle:
            return plistlib.load(handle)

    def test_rejects_no_opt_in_even_when_team_is_set(self) -> None:
        output = self.execute(team=TEAM)
        self.assertNotEqual(output.returncode, 0)
        self.assertIn("SIGNED_TEST_NOT_AUTHORIZED", output.stderr)
        info = self.read(self.native / "PacketTunnel-Info.plist")
        self.assertIs(info["TwinConnectProtocolBackendLinked"], False)

    def test_rejects_malformed_team(self) -> None:
        output = self.execute(team="NOT-A-TEAM", enable="YES")
        self.assertNotEqual(output.returncode, 0)
        self.assertIn("SIGNED_TEST_NOT_AUTHORIZED", output.stderr)

    def test_rejects_missing_framework(self) -> None:
        (self.native / "build/libbox/Libbox.xcframework/Info.plist").unlink()
        output = self.execute(team=TEAM, enable="YES")
        self.assertNotEqual(output.returncode, 0)
        self.assertIn("SIGNED_TEST_MISSING_XCODE_OR_LIBBOX_FRAMEWORK", output.stderr)

    def test_explicit_opt_in_sets_both_keychain_and_ne_entitlements(self) -> None:
        output = self.execute(team=TEAM, enable="YES")
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn("SIGNED_LIBBOX_TEST_CONFIGURED", output.stdout)
        for file in (
            self.runner / "Release.entitlements",
            self.runner / "DebugProfile.entitlements",
            self.native / "PacketTunnel.entitlements",
        ):
            entitlement = self.read(file)
            self.assertEqual(
                entitlement["com.apple.developer.networking.networkextension"],
                ["packet-tunnel-provider"],
            )
            self.assertEqual(entitlement["keychain-access-groups"], [GROUP])
            self.assertIs(entitlement["com.apple.security.network.client"], True)
        self.assertEqual(
            self.read(self.runner / "Info.plist")["TwinConnectKeychainAccessGroup"],
            GROUP,
        )
        self.assertIs(
            self.read(self.native / "PacketTunnel-Info.plist")[
                "TwinConnectProtocolBackendLinked"
            ],
            True,
        )
        again = self.execute(team=TEAM, enable="YES")
        self.assertEqual(again.returncode, 0, again.stderr)


if __name__ == "__main__":
    unittest.main()
