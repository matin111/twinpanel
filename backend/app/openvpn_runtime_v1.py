from __future__ import annotations

import asyncio
import base64
import shlex
from typing import Any


# TWINPANEL_OPENVPN_RUNTIME_V1
#
# OpenVPN drops privileges to nobody/nogroup. A client-connect hook placed below
# a root-only directory (for example /usr/local/sbin mode 0700) exists and is
# executable as root, but OpenVPN cannot traverse the parent directory. OpenVPN
# then reports AUTH_FAILED after a successful certificate/TLS handshake because
# the external client-connect program could not be executed.
#
# Keep the compatibility repair additive: existing provisioning remains the
# source of the OpenVPN server config/PKI, while this layer moves only the hook
# to a runtime-readable directory and makes Repair verify it as the real
# OpenVPN runtime user before treating the protocol as healthy.

HOOK_DIR = "/etc/openvpn/twinpanel-hooks"
HOOK_PATH = f"{HOOK_DIR}/client-connect"
DISABLED_DIR = "/etc/openvpn/twinpanel-disabled"
SERVER_CONFIG = "/etc/openvpn/server/twinpanel.conf"
_RUNTIME_MARKER = "_twinpanel_openvpn_runtime_v1_installed"

_CONNECT_SCRIPT = """#!/bin/sh
set -eu
CN="${common_name:-}"
case "$CN" in
  ""|*[!A-Za-z0-9_.@-]*) exit 1 ;;
esac
test ! -e "/etc/openvpn/twinpanel-disabled/$CN"
"""


def _remote_install_command() -> str:
    encoded = base64.b64encode(_CONNECT_SCRIPT.encode()).decode()
    hook = shlex.quote(HOOK_PATH)
    hook_dir = shlex.quote(HOOK_DIR)
    disabled = shlex.quote(DISABLED_DIR)
    config = shlex.quote(SERVER_CONFIG)
    encoded_q = shlex.quote(encoded)

    return f"""set -eu
mkdir -p {hook_dir} {disabled}
chmod 0755 {hook_dir} {disabled}
printf '%s' {encoded_q} | base64 -d > {hook}
chmod 0755 {hook}
if grep -Eq '^[[:space:]]*client-connect[[:space:]]+' {config}; then
  sed -i 's#^[[:space:]]*client-connect[[:space:]].*#client-connect {HOOK_PATH}#' {config}
else
  printf '\nclient-connect {HOOK_PATH}\n' >> {config}
fi
"""


async def _runtime_hook_ok(provision: Any, conn: Any) -> bool:
    probe = await provision.cmd(
        conn,
        f"""set +e
HOOK={shlex.quote(HOOK_PATH)}
CONF={shlex.quote(SERVER_CONFIG)}
ACTUAL=$(awk '$1 == "client-connect" {{print $2; exit}}' "$CONF" 2>/dev/null)
[ "$ACTUAL" = "$HOOK" ] || exit 21
[ -x "$HOOK" ] || exit 22
command -v runuser >/dev/null 2>&1 || exit 23
runuser -u nobody -- env common_name=twinpanel-health "$HOOK" >/dev/null 2>&1 || exit 24
echo TWINPANEL_OPENVPN_HOOK_OK
""",
        check=False,
    )
    return "TWINPANEL_OPENVPN_HOOK_OK" in str(probe or "")


async def _install_runtime_hook(
    provision: Any,
    conn: Any,
    port: int,
    transport: str,
) -> None:
    await provision.cmd(conn, _remote_install_command())
    await provision.cmd(
        conn,
        "systemctl restart openvpn-server@twinpanel.service",
    )
    await asyncio.sleep(1)

    if not await provision.active(conn, "openvpn-server@twinpanel"):
        raise RuntimeError(
            "OpenVPN service is not active after client-connect hook repair"
        )

    if not await provision.listener(conn, int(port), str(transport)):
        raise RuntimeError(
            "OpenVPN listener is not active after client-connect hook repair"
        )

    if not await _runtime_hook_ok(provision, conn):
        raise RuntimeError(
            "OpenVPN client-connect hook is not executable by runtime user nobody"
        )


def install_openvpn_runtime_hooks(provision: Any) -> None:
    """Install idempotent provisioning/repair guards around the legacy router."""

    if bool(getattr(provision, _RUNTIME_MARKER, False)):
        return

    original_install_openvpn = provision.install_openvpn
    original_existing_ok = provision.existing_ok

    async def install_openvpn_runtime_safe(
        conn: Any,
        port: int,
        transport: str,
    ):
        ok, error = await original_install_openvpn(
            conn,
            port,
            transport,
        )

        if not ok:
            return ok, error

        await _install_runtime_hook(
            provision,
            conn,
            int(port),
            str(transport),
        )

        return True, None

    async def existing_ok_runtime_safe(
        conn: Any,
        protocol: str,
        settings: Any,
    ) -> bool:
        base_ok = await original_existing_ok(
            conn,
            protocol,
            settings,
        )

        if str(protocol).lower() != "openvpn":
            return bool(base_ok)

        if not base_ok:
            return False

        if await _runtime_hook_ok(provision, conn):
            return True

        # Repair mode previously skipped OpenVPN whenever service+listener were
        # up, which left a broken client-connect hook untouched. Repair the hook
        # in place before reporting the protocol healthy. If this fails, raise
        # the real error instead of falling through to a misleading port-in-use
        # preflight failure.
        await _install_runtime_hook(
            provision,
            conn,
            int(settings.openvpn_port),
            str(settings.openvpn_transport),
        )

        return True

    provision.install_openvpn = install_openvpn_runtime_safe
    provision.existing_ok = existing_ok_runtime_safe
    setattr(provision, _RUNTIME_MARKER, True)
