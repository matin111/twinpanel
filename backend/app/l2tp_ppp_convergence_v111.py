from __future__ import annotations

from .models import NodeType
from .mother_access import get_or_create_l2tp_psk
from .routers import provision


MARKER = "TWINPANEL_L2TP_PPP_CONVERGENCE_V111"

_applied = False
_previous_existing_ok = None
_previous_install_l2tp = None
_previous_provision_protocols = None


async def _l2tp_support_files_ready(conn) -> bool:
    """Validate the managed files xl2tpd/pppd need for a real client call.

    A listening xl2tpd socket is not complete health. Production proved that
    xl2tpd can accept a call and then pppd exits immediately when its referenced
    options file is absent. This check never prints PSK or CHAP material.
    """

    result = await provision.cmd(
        conn,
        r"""
set +e
if \
  test -s /etc/ipsec.conf \
  && test -s /etc/ipsec.secrets \
  && test -s /etc/xl2tpd/xl2tpd.conf \
  && test -s /etc/ppp/options.xl2tpd \
  && test -f /etc/ppp/chap-secrets \
  && grep -Fq 'pppoptfile = /etc/ppp/options.xl2tpd' /etc/xl2tpd/xl2tpd.conf \
  && grep -Fq 'require-mschap-v2' /etc/ppp/options.xl2tpd
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

    if ok and not await _l2tp_support_files_ready(conn):
        return (
            False,
            "L2TP support files are incomplete after install",
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
    # skipped install_l2tp and only refreshed the PSK. Making existing_ok stricter
    # by itself is also insufficient because the legacy repair branch then hits
    # preflight and rejects the legitimately occupied 500/4500/1701 sockets.
    # Converge the managed L2TP files first, without port preflight, then allow
    # the previously-installed wrapper chain to continue normally.
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
        "health=services,listeners,managed_files "
        "repair=preflight_safe wrapper_chain=preserved",
        flush=True,
    )
