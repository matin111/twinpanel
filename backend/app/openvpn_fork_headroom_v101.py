from __future__ import annotations

import asyncio
import base64

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
_OPENVPN_CONFIG = "/etc/openvpn/server/twinpanel.conf"
_OPENVPN_HOOK_DIR = "/etc/openvpn/twinpanel-hooks"
_OPENVPN_HOOK_PATH = _OPENVPN_HOOK_DIR + "/client-connect"
_OPENVPN_LEGACY_HOOK_PATH = (
    "/usr/local/sbin/twinpanel-openvpn-client-connect"
)
_OPENVPN_CLIENT_CONNECT_SCRIPT = (
    "#!/bin/sh\n"
    "set -eu\n"
    "CN=\"${common_name:-}\"\n"
    "case \"$CN\" in\n"
    "  \"\"|*[!A-Za-z0-9_.@-]*) exit 1 ;;\n"
    "esac\n"
    "test ! -e \"/etc/openvpn/twinpanel-disabled/$CN\"\n"
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


async def ensure_openvpn_client_connect_exec_v102(
    conn,
) -> dict:
    """Converge the client-connect hook onto an executable managed path.

    Production showed that ``/usr/local/sbin`` may legitimately be mode 0700.
    The OpenVPN daemon drops privileges to ``nobody`` before running the
    client-connect hook, so a 0755 script below that non-traversable parent
    still fails with EACCES and OpenVPN returns AUTH_FAILED after successful
    TLS/certificate verification.

    Do not relax permissions on the global ``/usr/local/sbin`` directory.
    Instead keep the hook in a dedicated root-owned 0755 directory below
    ``/etc/openvpn`` and rewrite only TwinPanel's managed OpenVPN config.
    """

    encoded = base64.b64encode(
        _OPENVPN_CLIENT_CONNECT_SCRIPT.encode()
    ).decode()

    script = f"""
set -eu

SERVICE={_OPENVPN_SERVICE!r}
CONFIG={_OPENVPN_CONFIG!r}
HOOK_DIR={_OPENVPN_HOOK_DIR!r}
HOOK={_OPENVPN_HOOK_PATH!r}
LEGACY_HOOK={_OPENVPN_LEGACY_HOOK_PATH!r}
SCRIPT_B64={encoded!r}

install -d -o root -g root -m 0755 "$HOOK_DIR"
HOOK_TMP=$(mktemp "$HOOK_DIR/.client-connect.XXXXXX")
CFG_TMP=$(mktemp /etc/openvpn/server/.twinpanel.conf.XXXXXX)
trap 'rm -f "$HOOK_TMP" "$CFG_TMP"' EXIT

printf '%s' "$SCRIPT_B64" | base64 -d > "$HOOK_TMP"
chmod 0755 "$HOOK_TMP"

HOOK_CHANGED=0
if [ ! -f "$HOOK" ] || ! cmp -s "$HOOK_TMP" "$HOOK"; then
    install -o root -g root -m 0755 "$HOOK_TMP" "$HOOK"
    HOOK_CHANGED=1
fi

test -f "$CONFIG"

awk -v hook="$HOOK" '
BEGIN {{ changed = 0 }}
$1 == "client-connect" && changed == 0 {{
    print "client-connect " hook
    changed = 1
    next
}}
{{ print }}
END {{ if (changed == 0) exit 42 }}
' "$CONFIG" > "$CFG_TMP"

CONFIG_CHANGED=0
if ! cmp -s "$CFG_TMP" "$CONFIG"; then
    install -o root -g root -m 0644 "$CFG_TMP" "$CONFIG"
    CONFIG_CHANGED=1
fi

EXEC_PROBE=unavailable
if command -v runuser >/dev/null 2>&1; then
    if runuser -u nobody -- \
        env common_name=tp_v102_exec_probe "$HOOK"; then
        EXEC_PROBE=ok
    else
        EXEC_PROBE=failed
    fi
fi

if [ "$EXEC_PROBE" = "failed" ]; then
    echo "client-connect hook is not executable as nobody" >&2
    exit 43
fi

CHANGED=0
if [ "$HOOK_CHANGED" = "1" ] || [ "$CONFIG_CHANGED" = "1" ]; then
    CHANGED=1
fi

RESTARTED=0
if [ "$CHANGED" = "1" ] && systemctl is-active --quiet "$SERVICE"; then
    systemctl restart "$SERVICE"
    RESTARTED=1
fi

STATE=$(systemctl is-active "$SERVICE" 2>/dev/null || true)
CONFIG_HOOK=$(awk '$1 == "client-connect" {{ print $2; exit }}' "$CONFIG")

printf 'changed=%s\n' "$CHANGED"
printf 'hook_changed=%s\n' "$HOOK_CHANGED"
printf 'config_changed=%s\n' "$CONFIG_CHANGED"
printf 'restarted=%s\n' "$RESTARTED"
printf 'state=%s\n' "$STATE"
printf 'exec_probe=%s\n' "$EXEC_PROBE"
printf 'config_hook=%s\n' "$CONFIG_HOOK"
printf 'legacy_hook=%s\n' "$LEGACY_HOOK"
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

    if values.get("state") != "active":
        raise RuntimeError(
            "OpenVPN service is not active after client-connect convergence"
        )

    if values.get("config_hook") != _OPENVPN_HOOK_PATH:
        raise RuntimeError(
            "OpenVPN client-connect config did not converge to managed hook"
        )

    if values.get("exec_probe") == "failed":
        raise RuntimeError(
            "OpenVPN client-connect hook is not executable as nobody"
        )

    return {
        "ok": True,
        "hook": _OPENVPN_HOOK_PATH,
        "changed": values.get("changed") == "1",
        "hook_changed": values.get("hook_changed") == "1",
        "config_changed": values.get("config_changed") == "1",
        "restarted": values.get("restarted") == "1",
        "exec_probe": values.get("exec_probe") or None,
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
        hook_exec = await ensure_openvpn_client_connect_exec_v102(
            conn,
        )

        # Either convergence may restart the managed instance. Give the
        # listener a short bounded settle window before the existing probe.
        if headroom.get("restarted") or hook_exec.get("restarted"):
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
        openvpn_result["client_connect_exec"] = hook_exec
        openvpn_result["health"] = health

        if not health.get("ok"):
            openvpn_result["ok"] = False
            openvpn_result["error"] = (
                "OpenVPN service/listener failed after runtime convergence"
            )
            if "openvpn" not in failed:
                failed.append("openvpn")

    except Exception as exc:
        openvpn_result["ok"] = False
        openvpn_result["error"] = (
            "OpenVPN runtime convergence failed: "
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
