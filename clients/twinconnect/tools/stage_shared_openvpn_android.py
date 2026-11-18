#!/usr/bin/env python3
"""Build the pinned GPL ics-openvpn source against TwinConnect's one TUN.

The published OpenVPN Flutter AAR creates an independent Android VpnService.
Download its *exact* pinned library commit, patch the Builder at source level,
then let Gradle compile this source module in place of the published AAR.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


REV = "ccd61bc39bcb5b03281615ce669d2109557f6bd1"
ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / ".twinconnect-build" / "openvpn_library"
SOURCE = CHECKOUT / "vpnLib/src/main/java/de/blinkt/openvpn/core/OpenVPNService.java"
MANIFEST = CHECKOUT / "vpnLib/src/main/AndroidManifest.xml"


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError("Pinned OpenVPN source changed; refusing an independent VPN owner")
    return source.replace(old, new, 1)


def main() -> None:
    if not (CHECKOUT / ".git").is_dir():
        CHECKOUT.mkdir(parents=True, exist_ok=True)
        run("git", "-C", str(CHECKOUT), "init", "-q")
        run("git", "-C", str(CHECKOUT), "fetch", "--depth=1", "--quiet",
            "https://github.com/nizwar/openvpn_library.git", REV)
        run("git", "-C", str(CHECKOUT), "checkout", "--quiet", "--detach", "FETCH_HEAD")
    if run("git", "-C", str(CHECKOUT), "rev-parse", "HEAD") != REV:
        raise RuntimeError("OpenVPN source SHA differs from plugin 2.0.0 pin")
    content = SOURCE.read_text()
    if "TWINCONNECT_SHARED_TUN_OPENVPN" not in content:
        content = replace_once(
            content,
            "        Builder builder = new Builder();",
            "        // TWINCONNECT_SHARED_TUN_OPENVPN: ask the owner for a Builder.\n"
            "        Builder builder;\n"
            "        try {\n"
            '            builder = (Builder) Class.forName("com.twinpanel.twinconnect.SharedTunVpnService")\n'
            '                .getMethod("newExternalTunBuilder", String.class)\n'
            '                .invoke(null, "openvpn");\n'
            "        } catch (Exception e) {\n"
            "            VpnStatus.logError(R.string.tun_open_error);\n"
            "            return null;\n"
            "        }",
        )
        content = replace_once(
            content,
            '        mLastTunCfg = getTunConfigString();',
            '        // Capture IPv4 and IPv6 even on IPv4-only OpenVPN profiles.\n'
            '        // The extra IPv6 interface address is a discard route when the core\n'
            '        // does not negotiate IPv6; traffic must not bypass the guard.\n'
            '        builder.addAddress("fd00:253:253::1", 128);\n'
            '        builder.addRoute("0.0.0.0", 0);\n'
            '        builder.addRoute("::", 0);\n'
            '        mLastTunCfg = getTunConfigString();',
        )
        content = replace_once(
            content,
            "            if (tun == null)\n"
            '                throw new NullPointerException("Android establish() method returned null (Really broken network configuration?)");\n'
            "            return tun;",
            "            if (tun == null)\n"
            '                throw new NullPointerException("Android establish() method returned null (Really broken network configuration?)");\n'
            "            try {\n"
            '                Class.forName("com.twinpanel.twinconnect.SharedTunVpnService")\n'
            '                    .getMethod("externalTunEstablished", String.class, ParcelFileDescriptor.class)\n'
            '                    .invoke(null, "openvpn", tun);\n'
            "            } catch (Exception e) {\n"
            "                tun.close();\n"
            "                throw e;\n"
            "            }\n"
            "            return tun;",
        )
        content = replace_once(
            content,
            "        mOpenVPNThread = null;\n        if (!mStarting) {",
            "        mOpenVPNThread = null;\n"
            "        releaseTwinConnectTunnel();\n"
            "        if (!mStarting) {",
        )
        content = replace_once(
            content,
            "    public void endVpnService() {",
            "    private void releaseTwinConnectTunnel() {\n"
            "        try {\n"
            '            Class.forName("com.twinpanel.twinconnect.SharedTunVpnService")\n'
            '                .getMethod("externalTunReleased", String.class)\n'
            '                .invoke(null, "openvpn");\n'
            "        } catch (Exception ignored) { }\n"
            "    }\n\n"
            "    public void endVpnService() {",
        )
        content = replace_once(
            content,
            "        VpnStatus.flushLog();\n    }",
            "        VpnStatus.flushLog();\n"
            "        releaseTwinConnectTunnel();\n"
            "    }",
        )
        SOURCE.write_text(content)

    xml = MANIFEST.read_text()
    if "TWINCONNECT_SHARED_TUN_OPENVPN" not in xml:
        xml = replace_once(
            xml,
            '            <intent-filter>\n                <action android:name="android.net.VpnService" />\n'
            '            </intent-filter>',
            '            <!-- TWINCONNECT_SHARED_TUN_OPENVPN: only the host app advertises a VPN. -->',
        )
        MANIFEST.write_text(xml)
    if ("TWINCONNECT_SHARED_TUN_OPENVPN" not in SOURCE.read_text() or
            "TWINCONNECT_SHARED_TUN_OPENVPN" not in MANIFEST.read_text()):
        raise RuntimeError("OpenVPN independent VpnService patch did not apply")
    print("TwinConnect OpenVPN source pinned, patched, and ready for Gradle")


if __name__ == "__main__":
    main()
