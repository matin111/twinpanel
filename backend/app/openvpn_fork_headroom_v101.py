from __future__ import annotations

import asyncio

from .models import NodeType
from .routers import provision


_OPENVPN_SERVICE = "openvpn-server@twinpanel.service"
_OPENVPN_DROPIN_DIR = (
    "/etc/systemd/system/"
    "openvpn-server@twinpanel.service.d"
)
_OPENVPN_DROPIN_PATH = (
    _OPENVPN_DROPIN_DIR
    + "/10-twinpanel-fork-headroom.conf"
)


async def ensure_openvpn_fork_headroom_v101(
    conn,
) -> dict:
    """Remove the vendor UID-global RLIMIT_NPROC cap for TwinPanel OpenVPN.

    Ubuntu/Debian's OpenVPN template can ship with LimitNPROC=10. TwinPanel's
    OpenVPN worker drops to the shared ``nobody`` UID, which may also be used
    by Xray. RLIMIT_NPROC is enforced for the real UID (and counts Linux
    tasks/threads), so a client-connect hook can fail to fork with EAGAIN even
    while the OpenVPN service and listener look healthy.

    Keep systemd's per-service TasksMax/cgroup protection intact and override
    only the inappropriate UID-global process limit for this one managed
    OpenVPN instance.
    """

    script = f"""
set -eu

SERVICE={_OPENVPN_SERVICE!r}
DROPIN_DIR={_OPENVPN_DROPIN_DIR!r}
DROPIN={_OPENVPN_DROPIN_PATH!r}

install -d -m 0755 "$DROPIN_DIR"
TMP=$(mktemp "$DROPIN_DIR/.fork-headroom.XXXXXX")
trap 'rm -f "$TMP"' EXIT

cat > "$TMP" <<'EOF'
[Service]
LimitNPROC=infinity
EOF

CHANGED=0
if [ ! -f "$DROPIN" ] || ! cmp -s "$TMP" "$DROPIN"; then
    install -o root -g root -m 0644 "$TMP" "$DROPIN"
    CHANGED=1
fi

systemctl daemon-reload

RESTARTED=0
if [ "$CHANGED" = "1" ] && systemctl is-active --quiet "$SERVICE"; then
    systemctl restart "$SERVICE"
    RESTARTED=1
fi

LIMIT=$(systemctl show "$SERVICE" -p LimitNPROC --value 2>/dev/null || true)
SOFT=$(systemctl show "$SERVICE" -p LimitNPROCSoft --value 2>/dev/null || true)
STATE=$(systemctl is-active "$SERVICE" 2>/dev/null || true)

printf 'changed=%s\n' "$CHANGED"
printf 'restarted=%s\n' "$RESTARTED"
printf 'limit=%s\n' "$LIMIT"
printf 'soft=%s\n' "$SOFT"
printf 'state=%s\n' "$STATE"
"""

    output = await provision.cmd(
        conn,
        script,
        timeout=60,
    )

    values: dict[str, str] = {}
    for line in str(output or "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()

    state = values.get("state", "")
    if state != "active":
        raise RuntimeError(
            "OpenVPN service is not active after fork-headroom convergence"
        )

    return {
        "ok": True,
        "dropin": _OPENVPN_DROPIN_PATH,
        "changed": values.get("changed") == "1",
        "restarted": values.get("restarted") == "1",
        "limit_nproc": values.get("limit") or None,
        "limit_nproc_soft": values.get("soft") or None,
    }


_original_provision_protocols = provision.provision_protocols
_applied = False


async def _provision_protocols_v101(
    conn,
    p,
    db,
    node,
    repair=False,
):
    results, failed, secrets_out = await _original_provision_protocols(
        conn,
        p,
        db,
        node,
        repair,
    )

    openvpn_result = results.get("openvpn")

    should_converge = (
        bool(getattr(p, "install_openvpn", False))
        and node.node_type == NodeType.EXIT
        and str(getattr(node, "agent_url", "") or "")
        != "local://core"
        and isinstance(openvpn_result, dict)
        and bool(openvpn_result.get("ok"))
    )

    if not should_converge:
        return results, failed, secrets_out

    try:
        headroom = await ensure_openvpn_fork_headroom_v101(
            conn,
        )

        # A changed drop-in restarts the instance. Give the listener a short,
        # bounded settle window before the existing live-health probe.
        if headroom.get("restarted"):
            await asyncio.sleep(1)

        stored = provision._protocol_settings_from_db(
            db,
            node.id,
        )
        health = await provision._protocol_live_health(
            conn,
            "openvpn",
            stored.get("openvpn"),
        )

        provision._save_live_health(
            db,
            node,
            "openvpn",
            health,
        )
        db.commit()

        openvpn_result["fork_headroom"] = headroom
        openvpn_result["health"] = health

        if not health.get("ok"):
            openvpn_result["ok"] = False
            openvpn_result["error"] = (
                "OpenVPN service/listener failed after "
                "fork-headroom convergence"
            )
            if "openvpn" not in failed:
                failed.append("openvpn")

    except Exception as exc:
        openvpn_result["ok"] = False
        openvpn_result["error"] = (
            "OpenVPN fork-headroom convergence failed: "
            + str(exc)[:700]
        )
        provision.save_config(
            db,
            node.id,
            "openvpn",
            port=getattr(p, "openvpn_port", None),
            transport=getattr(p, "openvpn_transport", "udp"),
            service="openvpn-server@twinpanel",
            ok=False,
            error=openvpn_result["error"],
        )
        node.enable_openvpn = False
        db.commit()

        if "openvpn" not in failed:
            failed.append("openvpn")

    return results, failed, secrets_out


def apply_openvpn_fork_headroom_v101() -> None:
    global _applied

    if _applied:
        return

    provision.provision_protocols = _provision_protocols_v101
    _applied = True
