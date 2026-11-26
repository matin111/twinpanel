#!/usr/bin/env python3
"""Read-only production-copy validation for a parallel, attributable ShadowTLS listener.

Never installs the staged config, starts/stops a service, writes a customer
credential, changes routes, or turns on delivery. The temp file contains
ephemeral staging secrets and is removed immediately after sing-box check.
"""
from __future__ import annotations

import argparse
import base64
import copy
import importlib.util
import json
import secrets
import subprocess
import tempfile
from pathlib import Path


def load_stager():
    path = Path(__file__).resolve().parents[1] / "app/services/shadowtls_2022_identity_v1.py"
    spec = importlib.util.spec_from_file_location("tp_shadowtls_identity_pure", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("PURE_STAGER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def port_listening(port: int) -> bool:
    proc = subprocess.run(
        ["ss", "-H", "-ltn"], capture_output=True, text=True, timeout=7, check=False
    )
    if proc.returncode:
        raise RuntimeError("LOCAL_PORT_AUDIT_UNAVAILABLE")
    for line in proc.stdout.splitlines():
        columns = line.split()
        if len(columns) > 3:
            local_addr = columns[3]
            if local_addr.rsplit(":", 1)[-1] == str(port):
                return True
    return False


def validate_copy(config: Path, binary: Path, candidate_port: int) -> dict:
    if config.is_symlink() or not config.is_file():
        raise RuntimeError("CONFIG_PATH_INVALID")
    if not binary.is_file() or not binary.stat().st_mode & 0o111:
        raise RuntimeError("SINGBOX_BINARY_UNAVAILABLE")
    if type(candidate_port) is not int or not 1024 <= candidate_port <= 65535:
        raise RuntimeError("CANDIDATE_PORT_INVALID")
    if port_listening(candidate_port):
        raise RuntimeError("CANDIDATE_PORT_IN_USE")

    original = json.loads(config.read_text(encoding="utf-8"))
    untouched = copy.deepcopy(original)
    stager = load_stager()
    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    private_seed = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    staged = stager.stage_parallel_identity_inbounds(
        original, listen_port=candidate_port,
        server_key=key, derivation_secret=private_seed,
    )
    inbounds = untouched.get("inbounds") or []
    if original != untouched or staged.get("inbounds", [])[:len(inbounds)] != inbounds:
        raise RuntimeError("LEGACY_INBOUNDS_CHANGED")
    modern = [row for row in staged.get("inbounds", [])
              if isinstance(row, dict) and row.get("tag") == stager.NEW_INNER_TAG]
    if len(modern) != 1 or not modern[0].get("users"):
        raise RuntimeError("AUTHENTICATED_INNER_NOT_STAGED")
    usernames = [str(item.get("name") or "") for item in modern[0]["users"]]
    if len(usernames) != len(set(usernames)):
        raise RuntimeError("DUPLICATE_AUTHENTICATED_USER")

    with tempfile.TemporaryDirectory(prefix="twinpanel-shadowtls-dryrun-") as folder:
        destination = Path(folder) / "staged-config.json"
        destination.write_text(json.dumps(staged, ensure_ascii=False), encoding="utf-8")
        destination.chmod(0o600)
        checked = subprocess.run(
            [str(binary), "check", "-c", str(destination)],
            capture_output=True, text=True, timeout=40, check=False,
        )
        if checked.returncode:
            # Never print stdout/stderr: they can contain customer or node secrets.
            raise RuntimeError("PARALLEL_SINGBOX_CONFIG_CHECK_FAILED")
    return {
        "ok": True,
        "mode": "DRY_RUN_ONLY",
        "installed": False,
        "service_restarted": False,
        "delivery_enabled": False,
        "legacy_inbounds_preserved": True,
        "original_inbound_count": len(inbounds),
        "parallel_authenticated_users": len(usernames),
        "candidate_port": candidate_port,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/twinpanel/sing-box/config.json")
    parser.add_argument("--singbox-bin", default="/usr/local/bin/twinpanel-sing-box")
    parser.add_argument("--candidate-port", type=int, required=True)
    args = parser.parse_args()
    try:
        report = validate_copy(
            Path(args.config), Path(args.singbox_bin), args.candidate_port
        )
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "mode": "DRY_RUN_ONLY", "reason": str(error)}))
        raise SystemExit(1)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
