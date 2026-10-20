from __future__ import annotations

import base64
import shlex

from .models import NodeType
from .mother_access import get_or_create_l2tp_psk
from .routers import provision


MARKER = "TWINPANEL_L2TP_PPP_CONVERGENCE_V111"
TELEMETRY_MARKER = "TWINPANEL_L2TP_QUOTA_TELEMETRY_V113"
TELEMETRY_UP_HOOK = "/etc/ppp/ip-up.d/twinpanel-l2tp-telemetry"
TELEMETRY_DOWN_HOOK = "/etc/ppp/ip-down.d/twinpanel-l2tp-telemetry"

_applied = False
_previous_existing_ok = None
_previous_install_l2tp = None
_previous_provision_protocols = None


_TELEMETRY_UP_SCRIPT = f'''#!/bin/sh
# {TELEMETRY_MARKER}
# Record only authenticated TwinPanel L2TP PPP sessions. Never block PPP.
set +e

IFACE="${{1:-${{IFNAME:-}}}}"
LOCAL_IP="${{4:-${{IPLOCAL:-}}}}"
REMOTE_IP="${{5:-${{IPREMOTE:-}}}}"
PEER="${{PEERNAME:-}}"

case "$IFACE" in
  ppp[0-9]*) ;;
  *) exit 0 ;;
esac

[ "$LOCAL_IP" = "10.94.0.1" ] || exit 0
case "$REMOTE_IP" in
  10.94.0.*) ;;
  *) exit 0 ;;
esac

case "$PEER" in
  ""|*[!A-Za-z0-9_.@-]*) exit 0 ;;
esac

DIR=/run/twinpanel/l2tp-sessions
umask 077
mkdir -p "$DIR" >/dev/null 2>&1 || exit 0

STARTED="$(date +%s 2>/dev/null || printf '0')"
PID_VALUE="${{PPPD_PID:-$$}}"
TMP="$DIR/.${{IFACE}}.${{PID_VALUE}}.tmp"

{{
  printf 'identity=%s\n' "$PEER"
  printf 'interface=%s\n' "$IFACE"
  printf 'remote_ip=%s\n' "$REMOTE_IP"
  printf 'started_epoch=%s\n' "$STARTED"
  printf 'pppd_pid=%s\n' "$PID_VALUE"
}} > "$TMP" 2>/dev/null || exit 0

mv -f "$TMP" "$DIR/$IFACE" >/dev/null 2>&1 || true
exit 0
'''


_TELEMETRY_DOWN_SCRIPT = f'''#!/bin/sh
# {TELEMETRY_MARKER}
# Remove only the marker belonging to this pppd instance. Never block PPP.
set +e

IFACE="${{1:-${{IFNAME:-}}}}"
case "$IFACE" in
  ppp[0-9]*) ;;
  *) exit 0 ;;
esac

FILE="/run/twinpanel/l2tp-sessions/$IFACE"
[ -f "$FILE" ] || exit 0

CURRENT_PID="${{PPPD_PID:-}}"
if [ -n "$CURRENT_PID" ]; then
  SAVED_PID="$(sed -n 's/^pppd_pid=//p' "$FILE" 2>/dev/null | head -1)"
  [ -z "$SAVED_PID" ] || [ "$SAVED_PID" = "$CURRENT_PID" ] || exit 0
fi

rm -f "$FILE" >/dev/null 2>&1 || true
exit 0
'''


async def _ensure_l2tp_telemetry_hooks(conn) -> None:
    await provision.cmd(
        conn,
        "mkdir -p /etc/ppp/ip-up.d /etc/ppp/ip-down.d",
    )

    for path, content in (
        (TELEMETRY_UP_HOOK, _TELEMETRY_UP_SCRIPT),
        (TELEMETRY_DOWN_HOOK, _TELEMETRY_DOWN_SCRIPT),
    ):
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        await provision.cmd(
            conn,
            (
                f"printf '%s' {shlex.quote(encoded)} | base64 -d > "
                f"{shlex.quote(path)} && chmod 755 {shlex.quote(path)}"
            ),
        )


async def _l2tp_support_files_ready(conn) -> bool:
    """Validate the managed files xl2tpd/pppd need for a real client call.

    A listening xl2tpd socket is not complete health. Production proved that
    xl2tpd can accept a call and then pppd exits immediately when its referenced
    options file is absent. V113 also requires the fail-open PPP telemetry hooks
    used to synchronize real L2TP sessions with the quota ledger.
    """

    result = await provision.cmd(
        conn,
        f"""
set +e
if \
  test -s /etc/ipsec.conf \
  && test -s /etc/ipsec.secrets \
  && test -s /etc/xl2tpd/xl2tpd.conf \
  && test -s /etc/ppp/options.xl2tpd \
  && test -f /etc/ppp/chap-secrets \
  && grep -Fq 'pppoptfile = /etc/ppp/options.xl2tpd' /etc/xl2tpd/xl2tpd.conf \
  && grep -Fq 'require-mschap-v2' /etc/ppp/options.xl2tpd \
  && test -x {shlex.quote(TELEMETRY_UP_HOOK)} \
  && test -x {shlex.quote(TELEMETRY_DOWN_HOOK)} \
  && grep -Fq {shlex.quote(TELEMETRY_MARKER)} {shlex.quote(TELEMETRY_UP_HOOK)} \
  && grep -Fq {shlex.quote(TELEMETRY_MARKER)} {shlex.quote(TELEMETRY_DOWN_HOOK)}
then
  printf 'ready'
else
  printf 'missing'
fi
""",
        check=False,
    )

    return str(result or "").strip() == "ready"


async def _l2tp_runtime_ready(conn, settings) -> bool:
    if not await provision.active(
        conn,
        "strongswan-starter",
        "strongswan",
    ):
        return False

    if not await provision.active(conn, "xl2tpd"):
        return False

    for port in (500, 4500, 1701):
        if not await provision.listener(conn, port, "udp"):
            return False

    return await _l2tp_support_files_ready(conn)


async def _existing_ok_v111(conn, protocol: str, settings):
    if str(protocol or "").strip().lower() == "l2tp":
        return await _l2tp_runtime_ready(conn, settings)

    if _previous_existing_ok is None:
        raise RuntimeError("L2TP V111 existing_ok chain is not initialized")

    return await _previous_existing_ok(
        conn,
        protocol,
        settings,
    )


async def _install_l2tp_v111(conn, psk: str):
    if _previous_install_l2tp is None:
        raise RuntimeError("L2TP V111 installer chain is not initialized")

    ok, error, returned_psk = await _previous_install_l2tp(
        conn,
        psk,
    )

    if ok:
        await _ensure_l2tp_telemetry_hooks(conn)

    if ok and not await _l2tp_support_files_ready(conn):
        return (
            False,
            "L2TP support files or telemetry hooks are incomplete after install",
            returned_psk,
        )

    return ok, error, returned_psk


async def _provision_protocols_v111(
    conn,
    settings,
    db,
    node,
    repair=False,
):
    # Legacy repair used service+UDP/1701 as its complete L2TP health gate.
    # If xl2tpd was listening while /etc/ppp/options.xl2tpd was absent, repair
    # skipped install_l2tp and only refreshed the PSK. V113 extends the same
    # convergence rule to the PPP telemetry hooks: a node that can connect but
    # cannot report real sessions is not considered completely repaired.
    if (
        bool(repair)
        and bool(getattr(settings, "install_l2tp", False))
        and getattr(node, "node_type", None) == NodeType.EXIT
        and not await _l2tp_runtime_ready(conn, settings)
    ):
        psk = get_or_create_l2tp_psk(db)
        ok, error, _ = await provision.install_l2tp(
            conn,
            psk,
        )

        if not ok:
            raise RuntimeError(
                error
                or "L2TP managed runtime convergence failed"
            )

    if _previous_provision_protocols is None:
        raise RuntimeError("L2TP V111 provision chain is not initialized")

    return await _previous_provision_protocols(
        conn,
        settings,
        db,
        node,
        repair,
    )


def apply_l2tp_ppp_convergence_v111() -> None:
    global _applied
    global _previous_existing_ok
    global _previous_install_l2tp
    global _previous_provision_protocols

    if _applied:
        return

    # Capture at apply-time, not import-time. self_hosted_runtime applies the
    # existing OpenVPN V101/V102 provisioning wrapper before V87 invokes this
    # hook. Apply-time chaining preserves that already-installed behavior
    # instead of replacing it with a stale import-time base function.
    _previous_existing_ok = provision.existing_ok
    _previous_install_l2tp = provision.install_l2tp
    _previous_provision_protocols = provision.provision_protocols

    provision.existing_ok = _existing_ok_v111
    provision.install_l2tp = _install_l2tp_v111
    provision.provision_protocols = _provision_protocols_v111

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "health=services,listeners,managed_files,quota_hooks "
        "repair=preflight_safe wrapper_chain=preserved "
        "quota_telemetry=v113",
        flush=True,
    )
