from __future__ import annotations

import asyncio
import base64
import json

from . import xray_modern_runtime
from .models import Node, NodeType
from .routers import provision
from .xray_modern_runtime import _ensure_modern_xray


_original_provision_protocols = provision.provision_protocols
_original_state_generator_script = (
    xray_modern_runtime._state_generator_script
)
_runtime_applied = False
_reality_parser_compat_applied = False


def _apply_reality_key_parser_compat() -> None:
    """
    Make the remote Xray state generator accept both historical and current
    `xray x25519` labels.

    Older Xray builds printed labels such as:
      * Private key
      * Public key

    Current builds print:
      * PrivateKey
      * Password (PublicKey)
      * Hash32

    The V2 state generator already understands `Password`, but its previous
    normalization preserved parentheses. That turned `Password (PublicKey)`
    into `password(publickey)`, so the generated public key was discarded and
    provisioning failed with `REALITY key generation/derivation failed`.

    We patch the generated remote script rather than modifying secrets or
    generating keys on the controller. The private/public key material stays on
    the Exit node exactly as before.
    """

    global _reality_parser_compat_applied

    if _reality_parser_compat_applied:
        return

    old_normalizer = (
        '        key = key.strip().lower().replace(" ", "").replace("_", "")'
    )
    new_normalizer = '''        key = "".join(
            ch
            for ch in key.strip().lower()
            if ch.isalnum()
        )'''

    old_public_labels = (
        '        elif key in {"password", "publickey", "public"}:'
    )
    new_public_labels = '''        elif key in {
            "password",
            "passwordpublickey",
            "publickey",
            "public",
        }:'''

    def _state_generator_script_compat(domain: str) -> str:
        script = _original_state_generator_script(domain)

        if old_normalizer not in script:
            raise RuntimeError(
                "Xray REALITY compatibility patch: "
                "state key normalizer signature changed"
            )

        if old_public_labels not in script:
            raise RuntimeError(
                "Xray REALITY compatibility patch: "
                "public-key label signature changed"
            )

        script = script.replace(
            old_normalizer,
            new_normalizer,
            1,
        )
        script = script.replace(
            old_public_labels,
            new_public_labels,
            1,
        )

        return script

    xray_modern_runtime._state_generator_script = (
        _state_generator_script_compat
    )

    _reality_parser_compat_applied = True


async def _listener_line(
    conn,
    port: int,
) -> str:
    return (
        await provision.cmd(
            conn,
            (
                "ss -H -lntp 2>/dev/null "
                f"| awk '$4 ~ /:{int(port)}$/ {{print}}' "
                "| head -1"
            ),
            check=False,
        )
    ).strip()


def _health_probe_script(base_port: int) -> str:
    """Return a remote probe that exposes health only, never REALITY secrets."""

    return f'''
import json
import re
import subprocess
from pathlib import Path

base_port = {int(base_port)}
binary = Path("/usr/local/bin/xray")
config = Path("/usr/local/etc/xray/config.json")
state_path = Path("/usr/local/etc/xray/twinpanel-modern-state.json")


def run(args):
    try:
        return subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=20,
        )
    except Exception as exc:
        return None


service_result = run(["systemctl", "is-active", "xray.service"])
service_active = bool(
    service_result
    and service_result.returncode == 0
    and service_result.stdout.strip() == "active"
)

ss_result = run(["ss", "-H", "-lntp"])
ss_output = ss_result.stdout if ss_result else ""


def listening(port):
    return bool(
        re.search(
            rf":{{int(port)}}(?:\\s|$)",
            ss_output,
        )
    )


ports = {{
    "legacy": base_port,
    "xhttp_reality": base_port + 1,
    "grpc_reality": base_port + 2,
    "websocket_tls": base_port + 3,
    "httpupgrade_tls": base_port + 4,
}}
listeners = {{
    key: listening(port)
    for key, port in ports.items()
}}

state = {{}}
state_error = ""
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        state_error = "invalid modern state: " + str(exc)[:240]

config_test_ok = False
config_test_error = ""
if binary.is_file() and config.is_file():
    tested = run([
        str(binary),
        "run",
        "-test",
        "-config",
        str(config),
    ])
    if tested:
        config_test_ok = tested.returncode == 0
        if not config_test_ok:
            config_test_error = tested.stdout.strip()[-500:]

private_key_present = bool(
    str(state.get("reality_private_key") or "").strip()
)
public_key_present = bool(
    str(state.get("reality_password") or "").strip()
)
short_xhttp_present = bool(
    str(state.get("short_id_xhttp") or "").strip()
)
short_grpc_present = bool(
    str(state.get("short_id_grpc") or "").strip()
)

tls_enabled = bool(state.get("tls_enabled"))

missing = []
checks = {{
    "service": service_active,
    "binary": binary.is_file(),
    "config": config.is_file(),
    "config_test": config_test_ok,
    "state": state_path.is_file() and not state_error,
    "legacy_listener": listeners["legacy"],
    "xhttp_listener": listeners["xhttp_reality"],
    "grpc_listener": listeners["grpc_reality"],
    "private_key": private_key_present,
    "public_key": public_key_present,
    "short_id_xhttp": short_xhttp_present,
    "short_id_grpc": short_grpc_present,
}}

for key, value in checks.items():
    if not value:
        missing.append(key)

if tls_enabled:
    if not listeners["websocket_tls"]:
        missing.append("websocket_tls_listener")
    if not listeners["httpupgrade_tls"]:
        missing.append("httpupgrade_tls_listener")

error = state_error or config_test_error
if not error and missing:
    error = "missing health checks: " + ", ".join(missing)

print(json.dumps({{
    "ok": not missing,
    "service_active": service_active,
    "binary_present": binary.is_file(),
    "config_present": config.is_file(),
    "config_test_ok": config_test_ok,
    "state_present": state_path.is_file(),
    "state_version": state.get("version"),
    "listeners": listeners,
    "ports": ports,
    "reality_private_key_present": private_key_present,
    "reality_public_key_present": public_key_present,
    "short_id_xhttp_present": short_xhttp_present,
    "short_id_grpc_present": short_grpc_present,
    "tls_enabled": tls_enabled,
    "tls_domain_configured": bool(str(state.get("tls_domain") or "").strip()),
    "missing": missing,
    "error": error or None,
}}, ensure_ascii=False))
'''


async def _modern_health_snapshot(
    conn,
    base_port: int,
) -> dict:
    script = _health_probe_script(base_port)
    encoded = base64.b64encode(script.encode()).decode()

    try:
        raw = await provision.cmd(
            conn,
            f"printf '%s' '{encoded}' | base64 -d | python3",
            timeout=60,
            check=False,
        )
        payload = json.loads(raw.strip().splitlines()[-1])
        if not isinstance(payload, dict):
            raise ValueError("health result is not an object")
        return payload
    except Exception as exc:
        return {
            "ok": False,
            "service_active": False,
            "listeners": {},
            "missing": ["health_probe"],
            "error": "Xray health probe failed: " + str(exc)[:600],
        }


async def _ensure_with_retry(
    conn,
    base_port: int,
    node: Node,
    *,
    bootstrap_done: bool,
    attempts: int = 2,
) -> tuple[bool, str | None]:
    last_error: str | None = None

    for attempt in range(max(1, int(attempts))):
        if attempt:
            await asyncio.sleep(1.5)

        try:
            await _ensure_modern_xray(
                conn,
                base_port,
                node,
                bootstrap_done=bootstrap_done,
            )
            return True, None
        except Exception as exc:
            last_error = str(exc)[:1400]

    return False, last_error or "Xray Modern repair failed"


async def _reconcile_existing_legacy_xray(
    conn,
    settings,
    node: Node,
) -> tuple[bool, str | None]:
    """
    Upgrade an already-running TwinPanel legacy Xray node to the modern
    multi-profile runtime before the generic repair flow performs its port
    preflight.

    The operation is self-healing: transactional Modern reconciliation is
    retried once. A failure is returned to the caller instead of escaping as an
    unhandled FastAPI 500, so the normal repair flow can finish and the panel
    receives a structured per-protocol result.
    """

    if not bool(getattr(settings, "install_v2ray", False)):
        return False, None

    if node.node_type != NodeType.EXIT:
        return False, None

    if await provision.existing_ok(
        conn,
        "v2ray",
        settings,
    ):
        return False, None

    base_port = int(settings.xray_port)
    occupied = await _listener_line(
        conn,
        base_port,
    )

    if not occupied:
        return False, None

    if "xray" not in occupied.lower():
        return False, None

    return await _ensure_with_retry(
        conn,
        base_port,
        node,
        bootstrap_done=True,
        attempts=2,
    )


async def _provision_protocols_with_xray_reconcile(
    conn,
    settings,
    db,
    node: Node,
    repair: bool = False,
):
    modern_reconciled = False
    reconcile_error: str | None = None
    was_v2ray_enabled = bool(getattr(node, "enable_v2ray", False))

    should_manage_modern = bool(
        node.node_type == NodeType.EXIT
        and getattr(settings, "install_v2ray", False)
    )

    if repair and should_manage_modern:
        (
            modern_reconciled,
            reconcile_error,
        ) = await _reconcile_existing_legacy_xray(
            conn,
            settings,
            node,
        )

    # The original protocol loop catches individual protocol installer errors.
    # Reconcile failures above are deliberately not re-raised, preventing raw
    # ASGI 500s and allowing every selected protocol to complete its repair.
    result = await _original_provision_protocols(
        conn,
        settings,
        db,
        node,
        repair=repair,
    )

    if not should_manage_modern:
        return result

    try:
        results, failed, secrets_out = result
    except Exception:
        return result

    if not isinstance(results, dict) or not isinstance(failed, list):
        return result

    base_port = int(settings.xray_port)
    health = await _modern_health_snapshot(
        conn,
        base_port,
    )

    auto_heal_attempted = False
    auto_heal_error: str | None = None

    # Even when the generic installer returned success, trust the live remote
    # state. If Modern listeners/state are incomplete, repair them automatically
    # from the controller using the saved SSH access and verify again.
    if not bool(health.get("ok")):
        auto_heal_attempted = True
        _, auto_heal_error = await _ensure_with_retry(
            conn,
            base_port,
            node,
            bootstrap_done=False,
            attempts=2,
        )
        health = await _modern_health_snapshot(
            conn,
            base_port,
        )

    v2ray = results.setdefault(
        "v2ray",
        {
            "ok": False,
            "port": base_port,
            "port_text": str(base_port),
            "transport": "tcp",
            "error": None,
        },
    )

    if isinstance(v2ray, dict):
        v2ray["modern_health"] = health
        v2ray["modern_reconciled"] = modern_reconciled
        v2ray["auto_heal_attempted"] = auto_heal_attempted

        if bool(health.get("ok")):
            v2ray["ok"] = True
            v2ray["error"] = None
            v2ray["modern_ready"] = True
            if "v2ray" in failed:
                failed.remove("v2ray")

            node.enable_v2ray = True
            provision.save_config(
                db,
                node.id,
                "v2ray",
                port=base_port,
                transport="tcp",
                service="xray",
                ok=True,
                error=None,
            )
        else:
            reasons = [
                value
                for value in (
                    reconcile_error,
                    auto_heal_error,
                    str(health.get("error") or "").strip() or None,
                )
                if value
            ]
            error = (
                "Xray Modern auto-repair could not reach healthy state: "
                + " | ".join(dict.fromkeys(reasons))
            )[:1800]

            v2ray["ok"] = False
            v2ray["modern_ready"] = False
            v2ray["error"] = error

            if "v2ray" not in failed:
                failed.append("v2ray")

            # A failed Modern migration must not silently disable an existing
            # working Legacy Xray selection. Keep the protocol selected while
            # its NodeProtocolConfig health is marked as error for the UI.
            node.enable_v2ray = was_v2ray_enabled
            provision.save_config(
                db,
                node.id,
                "v2ray",
                port=base_port,
                transport="tcp",
                service="xray",
                ok=False,
                error=error,
            )

    db.commit()

    return results, failed, secrets_out


def apply_xray_modern_repair_runtime() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    _apply_reality_key_parser_compat()

    provision.provision_protocols = (
        _provision_protocols_with_xray_reconcile
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_MODERN_REPAIR_RUNTIME_V3_ACTIVE "
        "legacy_xray_reconcile_before_repair_preflight=1 "
        "reality_key_parser_compat=1 "
        "self_heal_retry=1 health_verify=1 raw_500_guard=1",
        flush=True,
    )
