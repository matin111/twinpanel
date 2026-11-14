#!/usr/bin/env python3
"""Reproducible native Android WireGuard integration for generated Flutter app.

Flutter project scaffolds are intentionally generated in CI. This script
installs reviewed Kotlin source into that scaffold and updates Gradle/manifest.
It aborts if generated template changes, instead of silently shipping a
broken or unprotected VPN.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
NATIVE = ROOT / "native" / "android"


def only_once(source: str, old: str, new: str, filename: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Unexpected Flutter Android scaffold in {filename}: {old[:80]}")
    return source.replace(old, new, 1)


def patch_gradle() -> None:
    filename = ANDROID / "app" / "build.gradle.kts"
    current = filename.read_text(encoding="utf-8")
    if "com.wireguard.android:tunnel:1.0.20260102" in current:
        return
    current = only_once(
        current,
        "targetCompatibility = JavaVersion.VERSION_17",
        "targetCompatibility = JavaVersion.VERSION_17\n"
        "        isCoreLibraryDesugaringEnabled = true",
        str(filename),
    )
    current += (
        "\n// Pinned WireGuard native tunnel implementation; distinct from Cisco/OpenConnect.\n"
        "dependencies {\n"
        '    implementation("com.wireguard.android:tunnel:1.0.20260102")\n'
        '    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")\n'
        "}\n"
    )
    filename.write_text(current, encoding="utf-8")


def patch_manifest() -> None:
    filename = ANDROID / "app" / "src" / "main" / "AndroidManifest.xml"
    current = filename.read_text(encoding="utf-8")
    if ("com.wireguard.android.backend.GoBackend$VpnService" in current and
            'android:name=".OpenConnectVpnService"' in current):
        return
    if '<manifest xmlns:android="http://schemas.android.com/apk/res/android">' not in current:
        raise RuntimeError("Unrecognized AndroidManifest.xml")
    if 'android.permission.INTERNET' not in current:
        current = only_once(
            current,
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <uses-permission android:name="android.permission.INTERNET" />',
            str(filename),
        )
    match = re.search(r"<application\b[^>]*>", current, flags=re.DOTALL)
    if match is None:
        raise RuntimeError("Missing Android application manifest element")
    # Prevent automatic restoration of old preferences/session/policy after
    # the user explicitly uninstalls the previous app for a clean reinstall.
    # Normal Android updates remain non-destructive.
    application = match.group(0)
    if "android:allowBackup" not in application:
        secured = application[:-1] + (
            ' android:allowBackup="false" android:fullBackupContent="false">'
        )
        current = current[:match.start()] + secured + current[match.end():]
        match = re.search(r"<application\b[^>]*>", current, flags=re.DOTALL)
        if match is None:
            raise RuntimeError("Unable to set Android backup policy")
    service = (
        '\n        <!-- The actual WireGuard GoBackend VpnService. '
        'No fake local TUN service. -->\n'
        '        <service android:name="com.wireguard.android.backend.GoBackend$VpnService"\n'
        '            android:exported="false"\n'
        '            android:permission="android.permission.BIND_VPN_SERVICE">\n'
        '            <intent-filter>\n'
        '                <action android:name="android.net.VpnService" />\n'
        '            </intent-filter>\n'
        '        </service>\n'
    )
    if "com.wireguard.android.backend.GoBackend$VpnService" in current:
        service = ""
    if 'android:name=".OpenConnectVpnService"' not in current:
        service += (
        '\n        <!-- Reserved Cisco / OpenConnect VpnService. The engine is '
        'not advertised until a real native transport is bundled. -->\n'
        '        <service android:name=".OpenConnectVpnService"\n'
        '            android:exported="false"\n'
        '            android:permission="android.permission.BIND_VPN_SERVICE">\n'
        '            <intent-filter>\n'
        '                <action android:name="android.net.VpnService" />\n'
        '            </intent-filter>\n'
        '        </service>\n'
    )
    current = current[:match.end()] + service + current[match.end():]
    filename.write_text(current, encoding="utf-8")


def install_native_sources() -> None:
    package = ANDROID / "app" / "src" / "main" / "kotlin" / "com" / "twinpanel" / "twinconnect"
    if not package.is_dir():
        raise RuntimeError(
            "Flutter Android scaffolds missing; run "
            "'flutter create --platforms=android,ios,macos,windows "
            "--org com.twinpanel --project-name twinconnect .' first"
        )
    for filename in ("MainActivity.kt", "WireGuardRuntime.kt", "OpenConnectVpnService.kt"):
        src = NATIVE / "kotlin" / "com" / "twinpanel" / "twinconnect" / filename
        if not src.is_file():
            raise RuntimeError(f"Missing tracked native source: {src}")
        shutil.copy2(src, package / filename)


def main() -> None:
    install_native_sources()
    patch_gradle()
    patch_manifest()
    print("Verified Android WireGuard JNI integration installed; Cisco not activated.")


if __name__ == "__main__":
    main()
