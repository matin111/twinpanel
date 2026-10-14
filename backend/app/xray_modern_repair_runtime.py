from __future__ import annotations

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


async def _reconcile_existing_legacy_xray(
    conn,
    settings,
    node: Node,
) -> bool:
    """
    Upgrade an already-running TwinPanel legacy Xray node to the modern
    multi-profile runtime before the generic repair flow performs its port
    preflight.

    Why this is needed:
      * modern existing_ok() correctly returns False when XHTTP/gRPC listeners
        are missing;
      * the legacy repair flow then preflights the base Xray port;
      * that port is already owned by the healthy legacy xray process, so the
        repair aborts before the modern installer can run.

    Only an existing listener owned by xray is reconciled here. Empty ports and
    collisions owned by other processes are intentionally left to the original
    repair flow so its normal validation/error handling remains authoritative.
    """

    if not bool(getattr(settings, "install_v2ray", False)):
        return False

    if node.node_type != NodeType.EXIT:
        return False

    if await provision.existing_ok(
        conn,
        "v2ray",
        settings,
    ):
        return False

    base_port = int(settings.xray_port)
    occupied = await _listener_line(
        conn,
        base_port,
    )

    if not occupied:
        return False

    if "xray" not in occupied.lower():
        return False

    # _ensure_modern_xray is transactional around the active config: it writes
    # and tests a temporary config, backs up the current config, restarts Xray,
    # verifies all required listeners and restores the backup if verification
    # fails. Existing VLESS clients are merged into every modern VLESS inbound.
    await _ensure_modern_xray(
        conn,
        base_port,
        node,
        bootstrap_done=True,
    )

    return True


async def _provision_protocols_with_xray_reconcile(
    conn,
    settings,
    db,
    node: Node,
    repair: bool = False,
):
    modern_reconciled = False

    if repair:
        modern_reconciled = (
            await _reconcile_existing_legacy_xray(
                conn,
                settings,
                node,
            )
        )

    result = await _original_provision_protocols(
        conn,
        settings,
        db,
        node,
        repair=repair,
    )

    if modern_reconciled:
        try:
            results = result[0]
            v2ray = results.get("v2ray")
            if isinstance(v2ray, dict):
                v2ray["modern_reconciled"] = True
        except (IndexError, TypeError, AttributeError):
            pass

    return result


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
        "TWINPANEL_XRAY_MODERN_REPAIR_RUNTIME_V2_ACTIVE "
        "legacy_xray_reconcile_before_repair_preflight=1 "
        "reality_key_parser_compat=1",
        flush=True,
    )
