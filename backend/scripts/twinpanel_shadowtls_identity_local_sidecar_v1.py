#!/usr/bin/env python3
"""Additive, loopback-only ShadowTLS SS2022 identity canary.

The live sing-box process, its config, the legacy ShadowTLS public port,
client delivery and the central quota ledger are NEVER modified here.

Operator --apply creates a separate root-readable config and systemd unit,
with independent 2022 server key and node-only HMAC derivation seed.
This is a bounded live canary, NOT permission to bill or expose users.
"""
from __future__ import annotations

import argparse
import base64
import copy
import importlib.util
import json
import os
import secrets
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path("/etc/twinpanel/sing-box/shadowtls-identity-canary")
LIVE = Path("/etc/twinpanel/sing-box/config.json")
BINARY = Path("/usr/local/bin/twinpanel-sing-box")
UNIT = Path("/etc/systemd/system/twinpanel-shadowtls-identity-canary.service")
PORT = 19448
API_PORT = 19096


def stager():
    path = Path(__file__).resolve().parents[1] / "app/services/shadowtls_2022_identity_v1.py"
    spec = importlib.util.spec_from_file_location("shadowtls_identity_staging_pure", path)
    if not spec or not spec.loader:
        raise RuntimeError("SHADOWTLS_STAGER_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(args: list[str], *, timeout: int = 15, check: bool = True):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=check)


def port_occupied(port: int) -> bool:
    result = run(["ss", "-H", "-ltn"], timeout=4)
    return any(
        len(columns := row.split()) > 3
        and columns[3].rsplit(":", 1)[-1] == str(port)
        for row in result.stdout.splitlines()
    )


def write_private(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists() or path.is_symlink():
        raise RuntimeError("PRIVATE_FILE_ALREADY_EXISTS")
    tmp = path.with_name(path.name + ".pending-" + secrets.token_hex(5))
    try:
        descriptor = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        path.chmod(0o600)
    finally:
        tmp.unlink(missing_ok=True)


def make_config(live: dict, secrets_state: dict) -> tuple[dict, int]:
    m = stager()
    staged = m.stage_parallel_identity_inbounds(
        live, listen_port=PORT,
        server_key=secrets_state["server_key"],
        derivation_secret=secrets_state["derivation_secret"],
    )
    original = live["inbounds"]
    if staged["inbounds"][:len(original)] != original:
        raise RuntimeError("LEGACY_INBOUNDS_NOT_PRESERVED")
    new = staged["inbounds"][len(original):]
    if len(new) != 2:
        raise RuntimeError("PARALLEL_INBOUND_CARDINALITY_INVALID")
    outer = next(x for x in new if x.get("tag") == m.NEW_OUTER_TAG)
    inner = next(x for x in new if x.get("tag") == m.NEW_INNER_TAG)
    outer["listen"] = "127.0.0.1"
    if inner.get("listen") != "127.0.0.1" or outer.get("listen_port") != PORT:
        raise RuntimeError("LOOPBACK_ONLY_CONTRACT_FAILED")
    if not inner.get("users"):
        raise RuntimeError("NO_AUTHENTICATED_CLIENTS")
    original_outbounds = copy.deepcopy(live.get("outbounds") or [])
    original_route = copy.deepcopy(live.get("route") or {"final":"direct"})
    if not original_outbounds:
        raise RuntimeError("NODE_OUTBOUNDS_MISSING")
    config = {
        "log": {"level":"info"},
        "inbounds": [outer, inner],
        "outbounds": original_outbounds,
        "route": original_route,
        "services": [{
            "type": "api",
            "tag": "twinpanel-accounting-api",
            "listen": "127.0.0.1",
            "listen_port": API_PORT,
            "secret": secrets_state["api_secret"],
        }],
    }
    # No public ingress: callers must be on this same machine.
    return config, len(inner["users"])


UNIT_CONTENT = """[Unit]
Description=TwinPanel ShadowTLS SS2022 per-user identity loopback canary
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
ExecStart=/usr/local/bin/twinpanel-sing-box run -c /etc/twinpanel/sing-box/shadowtls-identity-canary/config.json
Restart=on-failure
RestartSec=3
LimitNOFILE=32768
CPUQuota=75%%
MemoryMax=512M
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=multi-user.target
""".replace("75%%","75%")


def create(*, apply: bool) -> dict:
    if not LIVE.is_file() or LIVE.is_symlink():
        raise RuntimeError("LIVE_CONFIG_INVALID")
    if not BINARY.is_file():
        raise RuntimeError("SINGBOX_BINARY_MISSING")
    if port_occupied(PORT) or port_occupied(API_PORT):
        raise RuntimeError("CANARY_PORT_IN_USE")
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    saved_state = ROOT / "identity_state.json"
    if ROOT.exists() and any(ROOT.iterdir()):
        # The existing canary must be explicitly managed, not silently
        # replaced with fresh keys that invalidate test-client identities.
        raise RuntimeError("CANARY_ALREADY_INSTALLED")
    state = {
        "server_key": base64.b64encode(secrets.token_bytes(16)).decode(),
        "derivation_secret": base64.b64encode(secrets.token_bytes(32)).decode(),
        "api_secret": secrets.token_hex(24),
        "delivery_enabled": False,
        "public_listener": False,
        "accounting_enabled": False,
        "version": 1,
    }
    config, users = make_config(live, state)
    with tempfile.TemporaryDirectory(prefix="twinpanel-shadowtls-loopback-") as folder:
        path = Path(folder) / "canary.json"
        path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)
        checked = run([str(BINARY), "check", "-c", str(path)], timeout=35, check=False)
        if checked.returncode:
            raise RuntimeError("SIDECAR_CONFIG_CHECK_FAILED")
    if not apply:
        return {"ok": True, "check_only": True, "users": users,
                "delivery_enabled": False, "public_listener": False}
    if UNIT.exists():
        raise RuntimeError("SIDECAR_SYSTEMD_UNIT_ALREADY_EXISTS")
    installed = []
    try:
        write_private(saved_state, json.dumps(state))
        installed.append(saved_state)
        config_file = ROOT / "config.json"
        write_private(config_file, json.dumps(config, ensure_ascii=False))
        installed.append(config_file)
        write_private(UNIT, UNIT_CONTENT)
        installed.append(UNIT)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", "--now", UNIT.stem], timeout=25)
        # Wait for an actual API socket and successful service state.
        service = run(["systemctl", "is-active", UNIT.stem], check=False)
        if service.stdout.strip() != "active":
            raise RuntimeError("SIDECAR_SYSTEMD_NOT_ACTIVE")
        if not port_occupied(PORT) or not port_occupied(API_PORT):
            raise RuntimeError("SIDECAR_SOCKETS_UNAVAILABLE")
    except Exception:
        subprocess.run(["systemctl","stop",UNIT.stem],capture_output=True,timeout=8,check=False)
        subprocess.run(["systemctl","disable",UNIT.stem],capture_output=True,timeout=8,check=False)
        for path in installed:
            path.unlink(missing_ok=True)
        if ROOT.exists() and not any(ROOT.iterdir()):
            ROOT.rmdir()
        subprocess.run(["systemctl","daemon-reload"],capture_output=True,timeout=8,check=False)
        raise
    return {"ok": True, "installed": True, "users": users,
            "port": PORT, "api_port": API_PORT,
            "delivery_enabled": False, "public_listener": False,
            "existing_vpn_services_restarted": False}


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = create(apply=args.apply)
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}))
        raise SystemExit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
