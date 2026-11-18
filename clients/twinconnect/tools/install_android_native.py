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
        awg_aar = NATIVE / "amneziawg-core" / "tunnel-release.aar"
        if awg_aar.is_file() and 'libs/amneziawg-tunnel.aar' not in current:
            raise RuntimeError(
                "Android scaffold already patched without AWG; regenerate "
                "the Flutter Android scaffold before staging the AWG AAR"
            )
        return
    current = only_once(
        current,
        "targetCompatibility = JavaVersion.VERSION_17",
        "targetCompatibility = JavaVersion.VERSION_17\n"
        "        isCoreLibraryDesugaringEnabled = true",
        str(filename),
    )
    # OpenVPN's embedded process must be extracted from the APK at install time.
    # The 2.x Flutter plugin manages the OpenVPN VpnService independently.
    current = only_once(
        current,
        "android {",
        "android {\n    packaging {\n        jniLibs {\n            useLegacyPackaging = true\n        }\n    }",
        str(filename),
    )
    current += (
        "\n// Pinned WireGuard native tunnel implementation; distinct from Cisco/OpenConnect.\n"
        "dependencies {\n"
        '    implementation("com.wireguard.android:tunnel:1.0.20260102")\n'
        '    implementation("androidx.core:core:1.15.0")\n'
        '    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")\n'
        "}\n"
    )
    # R8 minification in release APKs must not rename JNI-visible fields or
    # callback methods.  The C library looks up asyncLock, libctx and other
    # class members by their original Java names (not by compile-time symbols).
    current += (
        "\n// Preserve the OpenConnect Java/JNI ABI in optimized release APKs.\n"
        "android {\n"
        "    buildTypes {\n"
        '        getByName("release") {\n'
        '            isMinifyEnabled = true\n'
        '            isShrinkResources = true\n'
        '            proguardFiles("proguard-rules.pro")\n'
        "        }\n"
        "    }\n"
        "}\n"
    )
    # The AWG build script stages an isolated libawg-go.so with its own
    # ELF SONAME. Bundle it only when the verified AAR is available.
    awg_aar = NATIVE / "amneziawg-core" / "tunnel-release.aar"
    if awg_aar.is_file():
        import zipfile
        with zipfile.ZipFile(awg_aar) as archive:
            names = set(archive.namelist())
            if "classes.jar" not in names or not any(
                name.endswith("/libawg-go.so") for name in names
            ) or any(name.endswith("/libwg-go.so") for name in names):
                raise RuntimeError("AWG AAR is not JNI-isolated")
        target = ANDROID / "app" / "libs"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(awg_aar, target / "amneziawg-tunnel.aar")
        current += (
            '\n// Independent AmneziaWG userspace engine.\n'
            'dependencies { implementation(files("libs/amneziawg-tunnel.aar")) }\n'
        )
    filename.write_text(current, encoding="utf-8")
    rules = ANDROID / "app" / "proguard-rules.pro"
    with rules.open("a", encoding="utf-8") as out:
        out.write(
            "\n# JNI ABI used by pinned libopenconnect.so. Never rename these.\n"
            "-keep class org.infradead.libopenconnect.** { *; }\n"
            "-keep class com.axevpn.flutter.openconnect.NativeOpenConnectSession { *; }\n"
            "-keep class com.axevpn.flutter.openconnect.NativeOpenConnectSession$* { *; }\n"
            "-keep class org.amnezia.awg.** { *; }\n"
            # MainActivity loads this class by its literal name via reflection.
            # R8 otherwise removes or renames it in release APKs, causing
            # AWG_NATIVE_ENGINE_UNAVAILABLE even when the AAR is present.
            "-keep class com.twinpanel.twinconnect.AmneziaWgRuntime { *; }\n"
            # SharedTunVpnService invokes the pinned wireguard-go JNI methods
            # reflectively. Release R8 must preserve these exact native names.
            "-keep class com.wireguard.android.backend.GoBackend { *; }\n"
            "-keep class com.twinpanel.twinconnect.SharedTunVpnService { *; }\n"

        )


def patch_manifest() -> None:
    filename = ANDROID / "app" / "src" / "main" / "AndroidManifest.xml"
    current = filename.read_text(encoding="utf-8")
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
    if 'android.permission.ACCESS_NETWORK_STATE' not in current:
        current = only_once(
            current,
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />',
            str(filename),
        )
    # SharedTunVpnService starts foreground immediately after VPN approval.
    for permission in (
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
    ):
        if f'android:name="{permission}"' not in current:
            current = only_once(
                current,
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
                f'    <uses-permission android:name="{permission}" />',
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
    service += (
        '\n        <service android:name=".AndroidTrafficGuardService"\n'
        '            android:exported="false"\n'
        '            android:foregroundServiceType="specialUse"\n'
        '            android:permission="android.permission.BIND_VPN_SERVICE">\n'
        '            <intent-filter>\n'
        '                <action android:name="android.net.VpnService" />\n'
        '            </intent-filter>\n'
        '            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"\n'
        '                android:value="vpn" />\n'
        '        </service>\n'
    )
    # WireGuard now transfers an actual TUN FD to libwg-go through this owner.
    service += (
        '\n        <service android:name=".SharedTunVpnService"\n'
        '            android:exported="false"\n'
        '            android:foregroundServiceType="specialUse"\n'
        '            android:permission="android.permission.BIND_VPN_SERVICE">\n'
        '            <intent-filter>\n'
        '                <action android:name="android.net.VpnService" />\n'
        '            </intent-filter>\n'
        '            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"\n'
        '                android:value="vpn" />\n'
        '        </service>\n'
    )
    # Register the official AmneziaWG VPN service only when its native AAR
    # is bundled. Never alias it to the ordinary WireGuard VpnService.
    awg_aar = NATIVE / "amneziawg-core" / "tunnel-release.aar"
    if awg_aar.is_file() and 'org.amnezia.awg.backend.GoBackend$VpnService' not in current:
        service += (
            '\n        <service android:name="org.amnezia.awg.backend.GoBackend$VpnService"\n'
            '            android:exported="false"\n'
            '            android:permission="android.permission.BIND_VPN_SERVICE">\n'
            '            <intent-filter>\n'
            '                <action android:name="android.net.VpnService" />\n'
            '            </intent-filter>\n'
            '        </service>\n'
        )
    # Avoid duplicating the stock WireGuard service on a repeated install.
    if "com.wireguard.android.backend.GoBackend$VpnService" in current:
        start = service.find("        <!-- The actual WireGuard GoBackend VpnService.")
        end = service.find("        </service>", start)
        if start >= 0 and end >= 0:
            service = service[:start] + service[end + len("        </service>"):]
    # A partially patched scaffold may already contain this service.
    # Never append a duplicate service declaration.
    if 'android:name=".AndroidTrafficGuardService"' in current:
        start = service.find('        <service android:name=".AndroidTrafficGuardService"')
        end = service.find('        </service>', start)
        if start >= 0 and end >= 0:
            service = service[:start] + service[end + len('        </service>'):]

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
    if 'android:name="com.axevpn.flutter.openconnect.AxeOpenConnectVpnService"' not in current:
        service += (
            '\n        <!-- Independent pinned Cisco CSTP/TLS VpnService -->\n'
            '        <service android:name="com.axevpn.flutter.openconnect.AxeOpenConnectVpnService"\n'
            '            android:exported="false"\n'
            '            android:foregroundServiceType="specialUse"\n'
            '            android:permission="android.permission.BIND_VPN_SERVICE">\n'
            '            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"\n'
            '                android:value="vpn" />\n'
            '        </service>\n'
        )
    for permission in (
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
    ):
        if f'android:name="{permission}"' not in current:
            current = current.replace(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
                f'    <uses-permission android:name="{permission}" />', 1,
            )
            match = re.search(r"<application\b[^>]*>", current, flags=re.DOTALL)
            if match is None:
                raise RuntimeError("Missing Android application")
    current = current[:match.end()] + service + current[match.end():]
    filename.write_text(current, encoding="utf-8")


def stage_mieru_executables() -> None:
    """Bundle pinned Android PIE Mieru executables, not a working VPN bridge."""
    source = NATIVE / "mieru-jni"
    destination = ANDROID / "app" / "src" / "main" / "jniLibs"
    for abi in ("arm64-v8a", "armeabi-v7a", "x86_64"):
        binary = source / abi / "libmieru.so"
        if not binary.is_file() or binary.stat().st_size == 0:
            raise RuntimeError(f"Missing Mieru Android executable for {abi}")
        target = destination / abi
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, target / "libmieru.so")


def install_native_sources() -> None:
    package = ANDROID / "app" / "src" / "main" / "kotlin" / "com" / "twinpanel" / "twinconnect"
    if not package.is_dir():
        raise RuntimeError(
            "Flutter Android scaffolds missing; run "
            "'flutter create --platforms=android,ios,macos,windows "
            "--org com.twinpanel --project-name twinconnect .' first"
        )
    for filename in ("MainActivity.kt", "WireGuardRuntime.kt", "OpenConnectVpnService.kt", "AndroidTrafficGuardService.kt", "VpnTunnelOwnership.kt", "TunPacketGate.kt", "SharedTunVpnService.kt"):
        src = NATIVE / "kotlin" / "com" / "twinpanel" / "twinconnect" / filename
        if not src.is_file():
            raise RuntimeError(f"Missing tracked native source: {src}")
        shutil.copy2(src, package / filename)
    # This source imports the official AWG AAR. Never compile it without
    # the matching verified native dependency.
    awg_aar = NATIVE / "amneziawg-core" / "tunnel-release.aar"
    awg_runtime = NATIVE / "kotlin" / "com" / "twinpanel" / "twinconnect" / "AmneziaWgRuntime.kt"
    if awg_aar.is_file():
        if not awg_runtime.is_file():
            raise RuntimeError("AWG AAR supplied without its native runtime")
        shutil.copy2(awg_runtime, package / "AmneziaWgRuntime.kt")
    else:
        (package / "AmneziaWgRuntime.kt").unlink(missing_ok=True)
    java_package = (ANDROID / "app" / "src" / "main" / "java" /
                    "com" / "axevpn" / "flutter" / "openconnect")
    java_source = NATIVE / "java" / "com" / "axevpn" / "flutter" / "openconnect"
    java_package.mkdir(parents=True, exist_ok=True)
    for filename in ("AxeOpenConnectVpnService.java", "OpenConnectFlutterPlugin.java",
                     "NativeOpenConnectSession.java"):
        src = java_source / filename
        if not src.is_file():
            raise RuntimeError(f"Missing Cisco native source: {src}")
        shutil.copy2(src, java_package / filename)

    # The JNI Java ABI is pinned to the same upstream revision as the built SO.
    upstream_abi = NATIVE / "java" / "org" / "infradead" / "libopenconnect" / "LibOpenConnect.java"
    if not upstream_abi.is_file():
        raise RuntimeError("Missing pinned libopenconnect JNI Java binding")
    target_abi = (ANDROID / "app" / "src" / "main" / "java" /
                  "org" / "infradead" / "libopenconnect")
    target_abi.mkdir(parents=True, exist_ok=True)
    shutil.copy2(upstream_abi, target_abi / "LibOpenConnect.java")


def install_launcher_icon() -> None:
    """Install the supplied TwinConnect artwork into Android launcher resources."""
    from PIL import Image

    source = NATIVE / "branding" / "twinconnect.webp"
    if not source.is_file():
        raise RuntimeError(f"Missing TwinConnect artwork: {source}")
    res = ANDROID / "app" / "src" / "main" / "res"
    with Image.open(source) as original:
        image = original.convert("RGBA")
        for density, pixels in (
            ("mdpi", 48), ("hdpi", 72), ("xhdpi", 96),
            ("xxhdpi", 144), ("xxxhdpi", 192),
        ):
            target = res / f"mipmap-{density}"
            target.mkdir(parents=True, exist_ok=True)
            image.resize((pixels, pixels), Image.Resampling.LANCZOS).save(
                target / "ic_launcher.png", format="PNG"
            )


def main() -> None:
    install_native_sources()
    # Mieru has no Android TUN bridge and is hidden from the app.
    # Do not package its unused native executables into release APKs.
    install_launcher_icon()
    patch_gradle()
    patch_manifest()
    print("Installed WireGuard JNI and independent pinned Cisco CSTP/TLS VpnService.")


if __name__ == "__main__":
    main()
