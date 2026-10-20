from __future__ import annotations

from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
MODULE = BACKEND / "app" / "l2tp_ppp_convergence_v111.py"
PROVISION = BACKEND / "app" / "routers" / "provision.py"
DESIRED = BACKEND / "app" / "protocol_dataplane_desired_state_v87.py"


def main() -> None:
    module = MODULE.read_text(encoding="utf-8")
    provision = PROVISION.read_text(encoding="utf-8")
    desired = DESIRED.read_text(encoding="utf-8")

    # Production failure contract: xl2tpd referenced this exact file and pppd
    # exited with code 2 because it was absent. Health must now include it.
    for token in (
        "TWINPANEL_L2TP_PPP_CONVERGENCE_V111",
        "test -s /etc/ppp/options.xl2tpd",
        "test -f /etc/ppp/chap-secrets",
        "pppoptfile = /etc/ppp/options.xl2tpd",
        "require-mschap-v2",
        "for port in (500, 4500, 1701):",
        "provision.existing_ok = _existing_ok_v111",
        "provision.install_l2tp = _install_l2tp_v111",
        "provision.provision_protocols = _provision_protocols_v111",
    ):
        assert token in module, token

    # Repair must converge a broken-but-listening runtime before delegating to
    # the legacy repair flow, otherwise preflight rejects the occupied sockets.
    wrapper = module.split("async def _provision_protocols_v111", 1)[1]
    assert "not await _l2tp_runtime_ready" in wrapper
    assert "psk = get_or_create_l2tp_psk(db)" in wrapper
    assert "ok, error, _ = await provision.install_l2tp(" in wrapper
    assert wrapper.index("await provision.install_l2tp(") < wrapper.index(
        "return await _original_provision_protocols("
    )

    # The canonical installer already owns these files and preserves CHAP
    # credentials with touch rather than truncating them.
    assert '"/etc/ppp/options.xl2tpd"' in provision
    assert "touch /etc/ppp/chap-secrets" in provision
    assert "> /etc/ppp/chap-secrets" not in provision

    # The convergence hook must be activated before V87 announces itself ready.
    assert "apply_l2tp_ppp_convergence_v111" in desired
    apply_body = desired.split(
        "def apply_protocol_dataplane_desired_state_v87()",
        1,
    )[1]
    assert apply_body.index("apply_l2tp_ppp_convergence_v111()") < apply_body.index(
        "tunnels._service_routes_for_exit = _service_routes_for_exit_v87"
    )

    print("L2TP_PPP_CONVERGENCE_V111_OK")


if __name__ == "__main__":
    main()
