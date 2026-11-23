#!/usr/bin/env python3
"""Read-only root-attested protocol of the ACTIVE sing-box TUN process.

No credentials, hosts, ports, UUIDs, or config contents reach stdout.
Invoked only by the restricted tun-admin status sudo command.
"""
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT = Path("/Library/PrivilegedHelperTools/TwinConnectTUN")
ALLOWED = {
    "vless": "v2ray", "hysteria2": "hysteria2", "tuic": "tuic",
    "anytls": "anytls", "socks": "socks5", "snell": "snell",
    "naive": "naive", "shadowtls": "shadowtls",
}


def current_protocol(root=ROOT, ps_output=None):
    if os.geteuid() != 0:
        return None
    profiles = list(root.glob("active-*.json"))
    if len(profiles) != 1:
        return None
    path = profiles[0]
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            return None
        if not 0 < info.st_size <= 262144:
            return None
        if ps_output is None:
            running = subprocess.run(
                ["/bin/ps", "-ww", "-axo", "command="],
                capture_output=True, text=True, timeout=5, check=True).stdout
        else:
            running = ps_output
        exact_command = f"{root}/sing-box run -c {path}"
        if not any(line.strip() == exact_command for line in running.splitlines()):
            return None
        profile = json.loads(path.read_text(encoding="utf-8"))
        inbounds = profile.get("inbounds")
        if not isinstance(inbounds, list) or len(inbounds) != 1:
            return None
        if inbounds[0].get("type") != "tun":
            return None
        outbounds = profile.get("outbounds")
        if not isinstance(outbounds, list):
            return None
        tagged = [row for row in outbounds
                  if isinstance(row, dict) and row.get("tag") == "proxy"]
        if len(tagged) != 1:
            return None
        return ALLOWED.get(tagged[0].get("type"))
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return None


def main():
    code = current_protocol()
    if code is not None:
        print("TUN_PROTOCOL=" + code)


if __name__ == "__main__":
    main()