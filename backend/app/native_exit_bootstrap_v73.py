from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import shlex
from typing import Any

from . import native_exit_bootstrap_v72 as v72


# ============================================================
# TWINPANEL NATIVE EXIT BOOTSTRAP V73 FAILURE CLEANUP
#
# V72 fixed the V71 transport root cause by moving the nested Exit SSH client
# onto the Iran management node. This hardening layer closes one remaining
# lifecycle gap: V72 creates /run/twinpanel-bootstrap/<token> before an open
# attempt, but an authentication/TCP/host-key failure can return before a
# NativeIranExitConnection object exists and therefore before wait_closed() can
# remove the workspace. If the native ControlMaster started just before a later
# controller-side error, it could also live until ControlPersist expired.
#
# V73 keeps the V72 transport and routing exactly as-is, but owns the token at
# the caller boundary and performs deterministic best-effort cleanup on *every*
# failed open path. The cleanup command itself is constant; host/user/port/token
# are sent over the authenticated Iran SSH channel via stdin, never interpolated
# into a command line.
# ============================================================


_CLEANUP_SOURCE = r'''
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

TOKEN_RE = re.compile(r"^[a-f0-9]{16,64}$")


def safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def master_pid(payload, root):
    ctl = os.path.join(root, "ctl")
    if not os.path.exists(ctl):
        return None

    host = str(payload.get("host") or "").strip()
    user = str(payload.get("username") or "root").strip() or "root"
    port = safe_int(payload.get("port"), 22)

    try:
        check = subprocess.run(
            [
                "ssh", "-S", ctl, "-O", "check",
                "-p", str(port), "-l", user, host,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except Exception:
        return None

    text = (
        check.stdout.decode("utf-8", "replace")
        + "\n"
        + check.stderr.decode("utf-8", "replace")
    )
    match = re.search(r"Master running \(pid=(\d+)\)", text)
    return int(match.group(1)) if match else None


def pid_matches_control(pid, ctl):
    if not pid or pid <= 1:
        return False
    try:
        raw = open(f"/proc/{pid}/cmdline", "rb").read()
    except OSError:
        return False
    cmdline = raw.replace(b"\0", b" ").decode("utf-8", "replace")
    return "ssh" in cmdline and ctl in cmdline


def stop_master(payload, root):
    ctl = os.path.join(root, "ctl")
    if not os.path.exists(ctl):
        return

    host = str(payload.get("host") or "").strip()
    user = str(payload.get("username") or "root").strip() or "root"
    port = safe_int(payload.get("port"), 22)
    pid = master_pid(payload, root)

    try:
        subprocess.run(
            [
                "ssh", "-S", ctl, "-O", "exit",
                "-p", str(port), "-l", user, host,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception:
        pass

    if pid:
        for _ in range(10):
            if not os.path.exists(f"/proc/{pid}"):
                return
            time.sleep(0.05)

        if pid_matches_control(pid, ctl):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                return

            for _ in range(10):
                if not os.path.exists(f"/proc/{pid}"):
                    return
                time.sleep(0.05)

            if pid_matches_control(pid, ctl):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


def main():
    raw = sys.stdin.buffer.read()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    token = str(payload.get("token") or "")
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("invalid_token")

    root = os.path.join("/run/twinpanel-bootstrap", token)
    stop_master(payload, root)
    shutil.rmtree(root, ignore_errors=True)
    sys.stdout.write('{"ok":true}')
    sys.stdout.flush()


try:
    main()
except Exception:
    # Cleanup is deliberately best-effort and must never leak target secrets in
    # stderr. The caller treats a non-zero exit as cleanup failure only.
    sys.stdout.write('{"ok":false}')
    sys.stdout.flush()
    raise SystemExit(1)
'''

_CLEANUP_B64 = base64.b64encode(_CLEANUP_SOURCE.encode("utf-8")).decode("ascii")
_CLEANUP_COMMAND = (
    "python3 -c "
    + shlex.quote(
        "import base64;exec(base64.b64decode(" + repr(_CLEANUP_B64) + "))"
    )
)


async def _cleanup_failed_open(
    iran_conn,
    *,
    token: str,
    host: str,
    port: int,
    username: str,
) -> None:
    payload: dict[str, Any] = {
        "token": str(token),
        "host": str(host),
        "port": int(port),
        "username": str(username or "root"),
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    try:
        await asyncio.wait_for(
            iran_conn.run(
                _CLEANUP_COMMAND,
                input=body,
                check=False,
            ),
            timeout=12,
        )
    except BaseException:
        # If the Iran management connection itself is gone, V72's native master
        # remains bounded by ControlPersist=75. Nothing sensitive is logged.
        pass


class NativeIranExitConnection(v72.NativeIranExitConnection):
    """V72 native OpenSSH transport with deterministic failed-open cleanup."""

    @classmethod
    async def open_with_password(
        cls,
        iran_conn,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> "NativeIranExitConnection":
        await v72.ensure_iran_native_ssh_dependencies(iran_conn)
        token = secrets.token_hex(12)
        pinned = v72._load_pinned_hostkey(host, port)

        try:
            response = await v72._helper_call(
                iran_conn,
                {
                    "op": "open_password",
                    "token": token,
                    "host": str(host),
                    "port": int(port),
                    "username": str(username or "root"),
                    "password": str(password),
                    "known_hosts_b64": (
                        base64.b64encode(pinned.encode()).decode("ascii")
                        if pinned
                        else ""
                    ),
                },
            )
            known_hosts = v72._decode_b64_text(response.get("known_hosts_b64"))
            v72._store_pinned_hostkey(host, port, known_hosts)
        except BaseException:
            await _cleanup_failed_open(
                iran_conn,
                token=token,
                host=host,
                port=port,
                username=username,
            )
            raise

        return cls(
            iran_conn,
            host=host,
            port=port,
            username=username,
            token=token,
        )

    @classmethod
    async def open_with_private_key(
        cls,
        iran_conn,
        *,
        host: str,
        port: int,
        username: str,
        private_key: str,
    ) -> "NativeIranExitConnection":
        await v72.ensure_iran_native_ssh_dependencies(iran_conn)
        token = secrets.token_hex(12)
        pinned = v72._load_pinned_hostkey(host, port)

        try:
            response = await v72._helper_call(
                iran_conn,
                {
                    "op": "open_key",
                    "token": token,
                    "host": str(host),
                    "port": int(port),
                    "username": str(username or "root"),
                    "private_key_b64": base64.b64encode(
                        str(private_key).encode()
                    ).decode("ascii"),
                    "known_hosts_b64": (
                        base64.b64encode(pinned.encode()).decode("ascii")
                        if pinned
                        else ""
                    ),
                },
            )
            known_hosts = v72._decode_b64_text(response.get("known_hosts_b64"))
            v72._store_pinned_hostkey(host, port, known_hosts)
        except BaseException:
            await _cleanup_failed_open(
                iran_conn,
                token=token,
                host=host,
                port=port,
                username=username,
            )
            raise

        return cls(
            iran_conn,
            host=host,
            port=port,
            username=username,
            token=token,
        )
