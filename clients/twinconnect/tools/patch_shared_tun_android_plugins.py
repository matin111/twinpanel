#!/usr/bin/env python3
"""Pin the bundled Android Flutter VPN cores to TwinConnect's sole VpnService.

pub packages are downloaded by `flutter pub get`, so this script runs AFTER
pub get and BEFORE Gradle. Abort on source drift; never silently ship a
different package version with independent VpnService.establish() calls.
"""

from __future__ import annotations

import os
from pathlib import Path


BRIDGE = 'Class.forName("com.twinpanel.twinconnect.SharedTunVpnService")'


def replace_once(source: str, needle: str, replacement: str, path: Path) -> str:
    if source.count(needle) != 1:
        raise RuntimeError(f"Expected one pinned Android source anchor in {path.name}: {needle[:65]}")
    return source.replace(needle, replacement, 1)


def pub_package(name: str, version: str) -> Path:
    cache = Path(os.environ.get("PUB_CACHE", Path.home() / ".pub-cache"))
    matches = list((cache / "hosted" / "pub.dev").glob(f"{name}-{version}"))
    if len(matches) != 1:
        raise RuntimeError(f"Pinned Flutter dependency missing from pub cache: {name} {version}")
    return matches[0]


def patch_singbox(root: Path) -> None:
    source = root / "android/src/main/kotlin/com/qusadprod/sing_box/service/SingBoxVpnService.kt"
    code = source.read_text()
    if "TWINCONNECT_SHARED_TUN_SINGBOX" in code:
        return
    code = replace_once(
        code,
        "        val builder = Builder()\n",
        "        // TWINCONNECT_SHARED_TUN_SINGBOX: instantiate the Builder in the sole VPN owner.\n"
        f"        val builder = ({BRIDGE}\n"
        '            .getMethod("newExternalTunBuilder", String::class.java)\n'
        '            .invoke(null, "singbox") as VpnService.Builder)\n',
        source,
    )
    code = replace_once(
        code,
        '        val pfd = builder.establish() ?: error("android: the application is not prepared or is revoked")\n',
        '        val pfd = builder.establish() ?: error("android: the application is not prepared or is revoked")\n'
        f'        {BRIDGE}\n'
        '            .getMethod("externalTunEstablished", String::class.java, ParcelFileDescriptor::class.java)\n'
        '            .invoke(null, "singbox", pfd)\n',
        source,
    )
    code = replace_once(
        code,
        '    private fun closeTun() {\n        val fd = tunFd\n        tunFd = null\n        runCatching { fd?.close() }\n    }',
        '    private fun closeTun() {\n        val fd = tunFd\n        tunFd = null\n'
        '        runCatching { fd?.close() }\n'
        '        releaseTwinConnectTun()\n'
        '    }\n\n'
        '    private fun releaseTwinConnectTun() {\n'
        f'        runCatching {{ {BRIDGE}\n'
        '            .getMethod("externalTunReleased", String::class.java)\n'
        '            .invoke(null, "singbox") }\n'
        '    }',
        source,
    )
    code = replace_once(
        code,
        '                runCatching { fd?.close() }\n                DefaultNetworkMonitor.stop()',
        '                runCatching { fd?.close() }\n'
        '                releaseTwinConnectTun()\n'
        '                DefaultNetworkMonitor.stop()',
        source,
    )
    source.write_text(code)
    manifest = root / "android/src/main/AndroidManifest.xml"
    xml = manifest.read_text()
    xml = replace_once(
        xml,
        '            <intent-filter>\n                <action android:name="android.net.VpnService" />\n'
        '            </intent-filter>\n            <meta-data\n'
        '                android:name="android.net.VpnService.SUPPORTS_ALWAYS_ON"\n'
        '                android:value="true" />',
        '            <!-- TwinConnect SharedTunVpnService is the sole OS-discoverable VPN. -->',
        manifest,
    )
    manifest.write_text(xml)


def patch_xray(root: Path) -> None:
    source = root / ("android/src/main/kotlin/com/github/tfox/flutter_vless/"
                     "xray/service/XrayVPNService.kt")
    code = source.read_text()
    if "TWINCONNECT_SHARED_TUN_XRAY" in code:
        return
    code = replace_once(
        code,
        '        val builder = Builder().setSession(current.REMARK).setMtu(1500)',
        '        // TWINCONNECT_SHARED_TUN_XRAY: same Builder owner as the disconnected guard.\n'
        f'        val builder = ({BRIDGE}\n'
        '            .getMethod("newExternalTunBuilder", String::class.java)\n'
        '            .invoke(null, "xray") as VpnService.Builder)\n'
        '            .setSession(current.REMARK).setMtu(1500)',
        source,
    )
    code = replace_once(
        code,
        '        tun = builder.establish() ?: error("TUN establishment denied")\n'
        '        previous?.close()',
        '        tun = builder.establish() ?: error("TUN establishment denied")\n'
        f'        {BRIDGE}\n'
        '            .getMethod("externalTunEstablished", String::class.java, ParcelFileDescriptor::class.java)\n'
        '            .invoke(null, "xray", requireNotNull(tun))\n'
        '        previous?.close()',
        source,
    )
    code = replace_once(
        code,
        '            runCatching { tun?.close() }; tun = null\n'
        '            config = null;',
        '            runCatching { tun?.close() }; tun = null\n'
        f'            runCatching {{ {BRIDGE}\n'
        '                .getMethod("externalTunReleased", String::class.java)\n'
        '                .invoke(null, "xray") }\n'
        '            config = null;',
        source,
    )
    source.write_text(code)
    manifest = root / "android/src/main/AndroidManifest.xml"
    xml = manifest.read_text()
    # Static companion state cannot cross the plugin's former daemon process.
    # Run the plugin core in the *same process* as the shared TUN owner.
    xml = replace_once(
        xml,
        '            android:permission="android.permission.BIND_VPN_SERVICE"\n'
        '            android:process=":RunSoLibXrayDaemon">',
        '            android:permission="android.permission.BIND_VPN_SERVICE">',
        manifest,
    )
    xml = replace_once(
        xml,
        '            <intent-filter>\n                <action android:name="android.net.VpnService" />\n'
        '            </intent-filter>\n            <meta-data\n'
        '                android:name="android.net.VpnService.SUPPORTS_ALWAYS_ON"\n'
        '                android:value="true" />',
        '            <!-- Sole OS VPN registration: com.twinpanel.twinconnect.SharedTunVpnService. -->',
        manifest,
    )
    manifest.write_text(xml)


def main() -> None:
    patch_singbox(pub_package("sing_box", "1.0.0"))
    patch_xray(pub_package("flutter_vless_android", "1.1.7+1"))
    print("TwinConnect: sing-box and Xray Android cores use SharedTunVpnService")


if __name__ == "__main__":
    main()
