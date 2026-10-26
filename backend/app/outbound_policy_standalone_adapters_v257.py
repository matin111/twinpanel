from __future__ import annotations

from typing import Any

AMNEZIAWG_POLICY = {
    "source_cidr": "10.254.0.0/16",
    "table": 10950,
    "priority": 10950,
}

STANDALONE_POLICY_SPECS: dict[str, dict[str, Any]] = {
    "mieru": {
        "adapter_kind": "standalone-socks",
        "inbound_tag": "twinpanel-mieru-policy-in",
        "listen_port": 19083,
    },
    "trusttunnel": {
        "adapter_kind": "standalone-socks",
        "inbound_tag": "twinpanel-trusttunnel-policy-in",
        "listen_port": 19084,
    },
    "sudoku": {
        "adapter_kind": "standalone-tproxy",
        "inbound_tag": "twinpanel-sudoku-policy-in",
        "listen_port": 19085,
    },
}

STANDALONE_POLICY_PROTOCOLS = frozenset({*STANDALONE_POLICY_SPECS, "amneziawg"})
RECONCILE_PATH = "/usr/local/lib/twinpanel/outbound-policy-standalone-v257"

# Runs on the managed node as root. Mieru and TrustTunnel use their native
# SOCKS5 upstream support. Sudoku has no server-side upstream proxy setting, so
# its services are isolated behind one dedicated UID and transparently sent
# into a Sing-box TProxy inbound. A systemd generator applies the UID to both
# the bootstrap service and future per-subscription services at daemon-reload,
# before those new services start.
STANDALONE_RECONCILE_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations

import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

STATE = pathlib.Path("/etc/twinpanel/sing-box/outbound-policy.json")
BASE = pathlib.Path("/etc/twinpanel/standalone")
MIERU_PORT = 19083
TRUST_PORT = 19084
SUDOKU_PORT = 19085
SUDOKU_USER = "twinpanel-sudoku"
MARK = "0x52a/0xfff"
TABLE = "10960"
PRIORITY = "10960"
CHAIN = "TP_SUDOKU_EGRESS"
GENERATOR = pathlib.Path("/usr/lib/systemd/system-generators/twinpanel-sudoku-outbound-policy")
MIERU_BASELINE = BASE / "mieru" / "policy-base-egress.json"
TRUST_BASELINE = BASE / "trusttunnel" / "policy-base-forward.txt"


def run(argv, *, check=True, capture=False):
    p = subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        check=False,
    )
    if check and p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip()
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(argv)}: {detail[-600:]}")
    return p


def load_state():
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return value if isinstance(value, dict) else {}


def policy_mode(doc, protocol):
    policies = doc.get("policies") if isinstance(doc.get("policies"), dict) else {}
    item = policies.get(protocol) if isinstance(policies, dict) else None
    value = str(item.get("mode") or "inherit").strip().lower() if isinstance(item, dict) else "inherit"
    return value if value in {"inherit", "direct", "outbound", "block"} else "inherit"


def atomic_text(path, text, mode=0o600):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            h.write(text)
            h.flush()
            os.fsync(h.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def configure_mieru(mode):
    if shutil.which("mita") is None:
        return
    status = run(["mita", "status"], check=False, capture=True)
    if status.returncode != 0 and "RUNNING" not in (status.stdout or "").upper():
        return
    live = run(["mita", "describe", "config"], capture=True)
    try:
        doc = json.loads(live.stdout or "{}")
    except Exception as exc:
        raise RuntimeError("Mieru live config is not valid JSON") from exc
    if not isinstance(doc, dict):
        raise RuntimeError("Mieru live config is not an object")

    changed = False
    if mode == "inherit":
        if MIERU_BASELINE.exists():
            saved = json.loads(MIERU_BASELINE.read_text(encoding="utf-8"))
            if bool(saved.get("present")):
                doc["egress"] = saved.get("value")
            else:
                doc.pop("egress", None)
            changed = True
    else:
        if not MIERU_BASELINE.exists():
            atomic_json(MIERU_BASELINE, {"present": "egress" in doc, "value": doc.get("egress")})
        managed = {
            "proxies": [{
                "name": "twinpanel-outbound-policy",
                "protocol": "SOCKS5_PROXY_PROTOCOL",
                "host": "127.0.0.1",
                "port": MIERU_PORT,
            }],
            "rules": [{
                "ipRanges": ["*"],
                "domainNames": ["*"],
                "action": "PROXY",
                "proxyNames": ["twinpanel-outbound-policy"],
            }],
        }
        if doc.get("egress") != managed:
            doc["egress"] = managed
            changed = True

    if changed:
        target = BASE / "mieru" / "policy-live.json"
        atomic_json(target, doc)
        run(["mita", "stop"], check=False)
        result = run(["mita", "replace", "config", str(target)], check=False, capture=True)
        if result.returncode != 0:
            run(["mita", "start"], check=False)
            raise RuntimeError("Mieru policy config replace failed: " + (result.stderr or "")[-500:])
        run(["mita", "start"])
        verify = run(["mita", "status"], capture=True)
        if "RUNNING" not in (verify.stdout or "").upper():
            raise RuntimeError("Mieru did not return to RUNNING after policy reconcile")


FORWARD_RE = re.compile(r"(?ms)^\[forward_protocol(?:\.socks5)?\]\n.*?(?=^\[|\Z)")


def configure_trusttunnel(mode):
    vpn = BASE / "trusttunnel" / "vpn.toml"
    if not vpn.exists():
        return
    text = vpn.read_text(encoding="utf-8")
    match = FORWARD_RE.search(text)
    if match is None:
        raise RuntimeError("TrustTunnel forward_protocol block is missing")
    if mode == "inherit":
        if not TRUST_BASELINE.exists():
            return
        replacement = TRUST_BASELINE.read_text(encoding="utf-8")
    else:
        if not TRUST_BASELINE.exists():
            atomic_text(TRUST_BASELINE, match.group(0))
        replacement = (
            "[forward_protocol.socks5]\n"
            f'address = "127.0.0.1:{TRUST_PORT}"\n'
            "extended_auth = false\n\n"
        )
    updated = text[:match.start()] + replacement + text[match.end():]
    if updated != text:
        atomic_text(vpn, updated)
        run(["systemctl", "restart", "twinpanel-trusttunnel.service"])
        run(["systemctl", "is-active", "--quiet", "twinpanel-trusttunnel.service"])


def sudoku_generator_text():
    # Generator output is recreated on every systemctl daemon-reload. Therefore
    # disabling the policy removes the drop-ins automatically without editing
    # TwinPanel's canonical unit files.
    return r'''#!/usr/bin/env python3
import glob, json, os, pathlib, sys
state = pathlib.Path("/etc/twinpanel/sing-box/outbound-policy.json")
try:
    doc = json.loads(state.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
policies = doc.get("policies") if isinstance(doc, dict) else {}
item = policies.get("sudoku") if isinstance(policies, dict) else None
mode = str(item.get("mode") or "inherit").strip().lower() if isinstance(item, dict) else "inherit"
if mode == "inherit":
    raise SystemExit(0)
out = pathlib.Path(sys.argv[1])
for path in glob.glob("/etc/systemd/system/twinpanel-sudoku*.service"):
    name = os.path.basename(path)
    dropin = out / (name + ".d") / "90-twinpanel-outbound-policy.conf"
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text(
        "[Service]\n"
        "User=twinpanel-sudoku\n"
        "AmbientCapabilities=CAP_NET_BIND_SERVICE\n"
        "CapabilityBoundingSet=CAP_NET_BIND_SERVICE\n"
        "ExecStartPre=+/bin/chown -R twinpanel-sudoku:twinpanel-sudoku /etc/twinpanel/standalone/sudoku\n",
        encoding="utf-8",
    )
'''


def ensure_sudoku_user():
    if run(["id", "-u", SUDOKU_USER], check=False).returncode != 0:
        run(["useradd", "--system", "--home", "/nonexistent", "--shell", "/usr/sbin/nologin", SUDOKU_USER])
    return run(["id", "-u", SUDOKU_USER], capture=True).stdout.strip()


def install_sudoku_generator():
    atomic_text(GENERATOR, sudoku_generator_text(), 0o755)


def active_sudoku_units():
    result = run(
        ["systemctl", "list-units", "--type=service", "--state=active", "--no-legend", "--plain", "twinpanel-sudoku*.service"],
        check=False,
        capture=True,
    )
    units = []
    for line in (result.stdout or "").splitlines():
        name = line.split(None, 1)[0].strip() if line.strip() else ""
        if name.startswith("twinpanel-sudoku") and name.endswith(".service"):
            units.append(name)
    return sorted(set(units))


def restart_active_sudoku_units():
    for unit in active_sudoku_units():
        run(["systemctl", "restart", unit])
        run(["systemctl", "is-active", "--quiet", unit])


def sudoku_listener_ports():
    paths = [str(BASE / "sudoku" / "server.config.json")]
    paths.extend(glob.glob(str(BASE / "sudoku" / "subscriptions" / "*" / "server.config.json")))
    output = set()
    for path in paths:
        try:
            value = int(json.loads(pathlib.Path(path).read_text(encoding="utf-8")).get("local_port"))
        except Exception:
            continue
        if 1 <= value <= 65535:
            output.add(value)
    return sorted(output)


def ipt(*args, check=True):
    return run(["iptables", "-w", "10", *args], check=check)


def clear_sudoku(uid):
    if uid:
        while ipt("-t", "mangle", "-C", "OUTPUT", "-m", "owner", "--uid-owner", uid, "-j", CHAIN, check=False).returncode == 0:
            ipt("-t", "mangle", "-D", "OUTPUT", "-m", "owner", "--uid-owner", uid, "-j", CHAIN)
    for proto in ("tcp", "udp"):
        rest = (
            "PREROUTING", "-m", "mark", "--mark", MARK, "-p", proto,
            "-j", "TPROXY", "--on-ip", "127.0.0.1", "--on-port",
            str(SUDOKU_PORT), "--tproxy-mark", MARK,
        )
        while ipt("-t", "mangle", "-C", *rest, check=False).returncode == 0:
            ipt("-t", "mangle", "-D", *rest)
    ipt("-t", "mangle", "-F", CHAIN, check=False)
    ipt("-t", "mangle", "-X", CHAIN, check=False)
    while run(["ip", "-4", "rule", "del", "priority", PRIORITY], check=False).returncode == 0:
        pass
    run(["ip", "-4", "route", "flush", "table", TABLE], check=False)


def configure_sudoku(mode):
    install_sudoku_generator()
    uid_probe = run(["id", "-u", SUDOKU_USER], check=False, capture=True)
    uid = (uid_probe.stdout or "").strip() if uid_probe.returncode == 0 else ""
    clear_sudoku(uid)

    if mode == "inherit":
        run(["systemctl", "daemon-reload"])
        restart_active_sudoku_units()
        return

    uid = ensure_sudoku_user()
    run(["systemctl", "daemon-reload"])
    restart_active_sudoku_units()

    ipt("-t", "mangle", "-N", CHAIN, check=False)
    ipt("-t", "mangle", "-A", CHAIN, "-d", "127.0.0.0/8", "-j", "RETURN")
    ipt("-t", "mangle", "-A", CHAIN, "-d", "169.254.0.0/16", "-j", "RETURN")
    for port in sudoku_listener_ports():
        ipt("-t", "mangle", "-A", CHAIN, "-p", "tcp", "--sport", str(port), "-j", "RETURN")
    ipt("-t", "mangle", "-A", CHAIN, "-j", "MARK", "--set-xmark", MARK)
    ipt("-t", "mangle", "-A", "OUTPUT", "-m", "owner", "--uid-owner", uid, "-j", CHAIN)
    run(["ip", "-4", "route", "replace", "local", "0.0.0.0/0", "dev", "lo", "table", TABLE])
    run(["ip", "-4", "rule", "add", "priority", PRIORITY, "fwmark", MARK, "lookup", TABLE])
    for proto in ("tcp", "udp"):
        ipt(
            "-t", "mangle", "-A", "PREROUTING", "-m", "mark", "--mark", MARK,
            "-p", proto, "-j", "TPROXY", "--on-ip", "127.0.0.1",
            "--on-port", str(SUDOKU_PORT), "--tproxy-mark", MARK,
        )


def main():
    doc = load_state()
    mieru_mode = policy_mode(doc, "mieru")
    trust_mode = policy_mode(doc, "trusttunnel")
    sudoku_mode = policy_mode(doc, "sudoku")

    # Baseline files are intentionally kept until every adapter reconciles.
    # If a later adapter fails, the caller restores the previous policy state
    # and invokes this helper again; the preserved baselines make that rollback
    # lossless. Only after the whole reconcile succeeds may inherit cleanup
    # remove the snapshots.
    configure_mieru(mieru_mode)
    configure_trusttunnel(trust_mode)
    configure_sudoku(sudoku_mode)

    if mieru_mode == "inherit":
        MIERU_BASELINE.unlink(missing_ok=True)
    if trust_mode == "inherit":
        TRUST_BASELINE.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"standalone_policy_reconcile_failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
'''


def managed_inbounds(state: dict[str, Any]) -> list[dict[str, Any]]:
    policies = state.get("policies") if isinstance(state.get("policies"), dict) else {}
    rows: list[dict[str, Any]] = []
    for key, spec in STANDALONE_POLICY_SPECS.items():
        raw = policies.get(key) if isinstance(policies, dict) else None
        mode = str(raw.get("mode") or "inherit") if isinstance(raw, dict) else "inherit"
        if mode == "inherit":
            continue
        if spec["adapter_kind"] == "standalone-socks":
            rows.append({
                "type": "socks",
                "tag": spec["inbound_tag"],
                "listen": "127.0.0.1",
                "listen_port": int(spec["listen_port"]),
            })
        else:
            rows.append({
                "type": "tproxy",
                "tag": spec["inbound_tag"],
                "listen": "127.0.0.1",
                "listen_port": int(spec["listen_port"]),
            })
    return rows


__all__ = [
    "AMNEZIAWG_POLICY",
    "RECONCILE_PATH",
    "STANDALONE_POLICY_PROTOCOLS",
    "STANDALONE_POLICY_SPECS",
    "STANDALONE_RECONCILE_SCRIPT",
    "managed_inbounds",
]
