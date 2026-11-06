#!/usr/bin/env python3
"""Remove only the retired VLESS gRPC REALITY inbound from an Xray node.

Usage: sudo python3 remove_v2ray_grpc_inbound.py --check
       sudo python3 remove_v2ray_grpc_inbound.py --apply

Does not delete users from other listeners, rotate REALITY keys, touch ports
other than the retired gRPC listener or modify other protocols. Apply triggers
one validated Xray restart only if a gRPC inbound actually exists.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path("/usr/local/etc/xray")
CONFIG = ROOT / "config.json"
STATE = ROOT / "twinpanel-modern-state.json"
RETIRED_TAG = "vless-grpc-reality"
REQUIRED_TAGS = {"vless-xhttp-reality"}
COMPANION_TAGS = {"vless-ws-tls", "vless-tcp-tls", "vless-tcp-reality"}


def _validate_file(path: Path) -> None:
    subprocess.run(
        ["/usr/local/bin/xray", "run", "-test", "-config", str(path)],
        check=True, capture_output=True, text=True, timeout=25,
    )


def _clone_permissions(path: Path, metadata: os.stat_result) -> None:
    """Keep Xray's original file owner/group and access mode after atomic swap."""
    os.chown(path, metadata.st_uid, metadata.st_gid)
    os.chmod(path, stat.S_IMODE(metadata.st_mode))


def run(*, apply: bool) -> dict[str, object]:
    lock_path = Path("/run/lock/twinpanel-xray-grpc-remove.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config_bytes = CONFIG.read_bytes()
        config_stat = CONFIG.stat()
        config = json.loads(config_bytes)
        inbounds = config.get("inbounds", [])
        if not isinstance(inbounds, list):
            raise RuntimeError("Invalid Xray inbound list")
        tags = {x.get("tag") for x in inbounds if isinstance(x, dict)}
        retired = [x for x in inbounds if isinstance(x, dict) and x.get("tag") == RETIRED_TAG]
        if not retired:
            return {"changed": False, "retired": 0}
        if len(retired) != 1 or not REQUIRED_TAGS.issubset(tags) or not tags.intersection(COMPANION_TAGS):
            raise RuntimeError("gRPC removal refused: unsafe or incomplete V2Ray node")
        new_config = dict(config)
        new_config["inbounds"] = [
            x for x in inbounds
            if not isinstance(x, dict) or x.get("tag") != RETIRED_TAG
        ]
        # Every non-gRPC inbound stays structurally untouched, including its users.
        assert new_config["inbounds"] == [x for x in inbounds if x not in retired]
        stage_config = None
        stage_state = None
        backup_config = None
        backup_state = None
        state = None
        state_stat = None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix="tp-no-grpc-", suffix=".json",
                dir=str(ROOT), delete=False,
            ) as handle:
                stage_config = Path(handle.name)
                json.dump(new_config, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.chmod(stage_config, 0o600)
            _validate_file(stage_config)
            result = {"changed": True, "retired": 1, "retained_inbounds": len(new_config["inbounds"])}
            if not apply:
                return dict(result, dry_run=True)
            if subprocess.run(
                ["systemctl", "is-active", "--quiet", "xray"], check=False,
                timeout=10,
            ).returncode != 0:
                raise RuntimeError("Xray is not active; refusing production restart")
            if STATE.exists():
                state_stat = STATE.stat()
                state = json.loads(STATE.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    raise RuntimeError("Invalid Xray state")
                state.pop("short_id_grpc", None)
                state.pop("grpc_service", None)
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", prefix="tp-no-grpc-state-",
                    suffix=".json", dir=str(ROOT), delete=False,
                ) as handle:
                    stage_state = Path(handle.name)
                    json.dump(state, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                os.chmod(stage_state, 0o600)
                _clone_permissions(stage_state, state_stat)
            # Fail closed if an agent changed the live config during staging.
            if CONFIG.read_bytes() != config_bytes:
                raise RuntimeError("Xray config changed during cleanup staging")
            backup_config = ROOT / ("config.json.before-no-grpc-" + stamp)
            shutil.copy2(CONFIG, backup_config)
            os.chmod(backup_config, 0o600)
            if stage_state is not None:
                backup_state = ROOT / ("twinpanel-modern-state.json.before-no-grpc-" + stamp)
                shutil.copy2(STATE, backup_state)
                os.chmod(backup_state, 0o600)
            _clone_permissions(stage_config, config_stat)
            os.replace(stage_config, CONFIG)
            stage_config = None
            if stage_state is not None:
                os.replace(stage_state, STATE)
                stage_state = None
            subprocess.run(["systemctl", "restart", "xray"], check=True, timeout=25)
            subprocess.run(["systemctl", "is-active", "--quiet", "xray"], check=True, timeout=12)
            _validate_file(CONFIG)
            verify = json.loads(CONFIG.read_text(encoding="utf-8"))
            assert not any(x.get("tag") == RETIRED_TAG for x in verify["inbounds"])
            assert REQUIRED_TAGS.issubset({x.get("tag") for x in verify["inbounds"]})
            return dict(result, applied=True)
        except Exception:
            if backup_config is not None and backup_config.exists():
                shutil.copy2(backup_config, CONFIG)
                _clone_permissions(CONFIG, config_stat)
                if backup_state is not None and backup_state.exists():
                    shutil.copy2(backup_state, STATE)
                    _clone_permissions(STATE, state_stat)
                subprocess.run(["systemctl", "restart", "xray"], timeout=25, check=False)
            raise
        finally:
            if stage_config is not None:
                stage_config.unlink(missing_ok=True)
            if stage_state is not None:
                stage_state.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--check", action="store_true")
    choices.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply), sort_keys=True))
