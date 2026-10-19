from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# This module deliberately keeps the Exit password/private key out of argv,
# environment variables, logs and generated shell command strings. Secrets are
# sent to a short-lived Python helper on the Iran management node over the
# already-authenticated SSH channel's stdin. The helper passes passwords to
# sshpass through an inherited anonymous file descriptor and sends target shell
# scripts to OpenSSH over stdin.

_HELPER_TIMEOUT_SECONDS = 45
_CONTROL_PERSIST_SECONDS = 75
_HOSTKEY_DIR = Path(
    os.environ.get(
        "TWINPANEL_EXIT_HOSTKEY_DIR",
        "/var/lib/vpnshop/node-hostkeys",
    )
)


class NativeBootstrapError(RuntimeError):
    def __init__(self, stage: str, detail: str):
        self.stage = str(stage or "unknown")
        self.detail = str(detail or "unknown_error")[:1800]
        super().__init__(f"{self.stage}={self.detail}")


@dataclass(slots=True)
class NativeSSHResult:
    stdout: str
    stderr: str
    exit_status: int


_IRAN_HELPER_SOURCE = r'''
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys

CONTROL_PERSIST = 75
TOKEN_RE = re.compile(r"^[a-f0-9]{16,64}$")


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.flush()


def decode_text(value):
    if not value:
        return ""
    return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")


def encode_text(value):
    return base64.b64encode((value or "").encode("utf-8")).decode("ascii")


def safe_detail(text, password=""):
    value = str(text or "").strip()
    if password:
        value = value.replace(password, "***")
    return value[-1600:] or "unknown_error"


def target_args(payload):
    host = str(payload.get("host") or "").strip()
    user = str(payload.get("username") or "root").strip() or "root"
    port = int(payload.get("port") or 22)
    if not host or not (1 <= port <= 65535):
        raise ValueError("invalid_target")
    return host, user, port


def workspace(payload):
    token = str(payload.get("token") or "")
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("invalid_token")
    root = os.path.join("/run/twinpanel-bootstrap", token)
    os.makedirs(root, mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def base_ssh_args(payload, root, strict):
    host, user, port = target_args(payload)
    known_hosts = os.path.join(root, "known_hosts")
    ctl = os.path.join(root, "ctl")
    return [
        "-T",
        "-p", str(port),
        "-l", user,
        "-o", "ConnectTimeout=10",
        "-o", "ConnectionAttempts=1",
        "-o", "ServerAliveInterval=10",
        "-o", "ServerAliveCountMax=2",
        "-o", "LogLevel=ERROR",
        "-o", f"StrictHostKeyChecking={strict}",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "UpdateHostKeys=no",
        "-o", "HashKnownHosts=no",
        "-o", f"ControlPath={ctl}",
        host,
    ]


def tcp_preflight(host, port):
    sock = socket.create_connection((host, port), timeout=7)
    try:
        sock.settimeout(None)
    finally:
        sock.close()


def run_process(argv, *, input_bytes=None, pass_fds=(), timeout=30):
    try:
        return subprocess.run(
            argv,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=tuple(pass_fds),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("process_timeout") from exc


def classify_ssh_error(stderr, default_stage):
    text = (stderr or "").lower()
    if "host key verification failed" in text or "remote host identification has changed" in text:
        return "exit_host_key"
    if "permission denied" in text or "authentication failed" in text:
        return "exit_auth"
    if (
        "connection timed out" in text
        or "connection refused" in text
        or "no route to host" in text
        or "network is unreachable" in text
        or "connection reset" in text
    ):
        return "iran_to_exit_tcp"
    return default_stage


def write_known_hosts(root, payload):
    path = os.path.join(root, "known_hosts")
    pinned = decode_text(payload.get("known_hosts_b64"))
    if pinned:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(pinned)
        os.chmod(path, 0o600)
        return "yes"
    with open(path, "a", encoding="utf-8"):
        pass
    os.chmod(path, 0o600)
    return "accept-new"


def read_known_hosts(root):
    path = os.path.join(root, "known_hosts")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def control_check(payload, root):
    host, user, port = target_args(payload)
    ctl = os.path.join(root, "ctl")
    return run_process(
        [
            "ssh", "-S", ctl, "-O", "check",
            "-p", str(port), "-l", user, host,
        ],
        timeout=8,
    )


def open_password(payload, root):
    host, _user, port = target_args(payload)
    password = str(payload.get("password") or "")
    if not password:
        raise NativeError("exit_auth", "password_missing")

    if shutil.which("ssh") is None:
        raise NativeError("iran_dependency", "openssh_client_missing")
    if shutil.which("sshpass") is None:
        raise NativeError("iran_dependency", "sshpass_missing")

    try:
        tcp_preflight(host, port)
    except Exception as exc:
        raise NativeError("iran_to_exit_tcp", safe_detail(exc, password)) from exc

    strict = write_known_hosts(root, payload)
    argv = [
        "sshpass",
        "-d", "3",
        "ssh",
        "-M", "-N", "-f",
        "-o", "ControlMaster=yes",
        "-o", f"ControlPersist={CONTROL_PERSIST}",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no",
        "-o", "NumberOfPasswordPrompts=1",
    ] + base_ssh_args(payload, root, strict)

    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, (password + "\n").encode("utf-8"))
        os.close(write_fd)
        write_fd = -1
        if read_fd != 3:
            os.dup2(read_fd, 3)
            os.close(read_fd)
            read_fd = 3
        proc = run_process(argv, pass_fds=(read_fd,), timeout=22)
    finally:
        if write_fd >= 0:
            try:
                os.close(write_fd)
            except OSError:
                pass
        if read_fd >= 0:
            try:
                os.close(read_fd)
            except OSError:
                pass

    stderr = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        stage = classify_ssh_error(stderr, "exit_auth")
        raise NativeError(stage, safe_detail(stderr, password))

    check = control_check(payload, root)
    if check.returncode != 0:
        stderr = check.stderr.decode("utf-8", "replace")
        raise NativeError("exit_auth", safe_detail(stderr, password))

    return read_known_hosts(root)


def open_key(payload, root):
    host, _user, port = target_args(payload)
    private_key = decode_text(payload.get("private_key_b64"))
    if not private_key:
        raise NativeError("exit_auth", "private_key_missing")
    if shutil.which("ssh") is None:
        raise NativeError("iran_dependency", "openssh_client_missing")

    try:
        tcp_preflight(host, port)
    except Exception as exc:
        raise NativeError("iran_to_exit_tcp", safe_detail(exc)) from exc

    strict = write_known_hosts(root, payload)
    key_path = os.path.join(root, "exit.key")
    with open(key_path, "w", encoding="utf-8") as fh:
        fh.write(private_key)
    os.chmod(key_path, 0o600)

    try:
        argv = [
            "ssh",
            "-M", "-N", "-f",
            "-i", key_path,
            "-o", "ControlMaster=yes",
            "-o", f"ControlPersist={CONTROL_PERSIST}",
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
        ] + base_ssh_args(payload, root, strict)
        proc = run_process(argv, timeout=22)
    finally:
        try:
            with open(key_path, "r+b") as fh:
                size = os.fstat(fh.fileno()).st_size
                if size:
                    fh.write(b"\0" * size)
                    fh.flush()
                    os.fsync(fh.fileno())
        except OSError:
            pass
        try:
            os.unlink(key_path)
        except OSError:
            pass

    stderr = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        stage = classify_ssh_error(stderr, "exit_auth")
        raise NativeError(stage, safe_detail(stderr))

    check = control_check(payload, root)
    if check.returncode != 0:
        stderr = check.stderr.decode("utf-8", "replace")
        raise NativeError("exit_auth", safe_detail(stderr))

    return read_known_hosts(root)


def run_target(payload, root):
    host, user, port = target_args(payload)
    ctl = os.path.join(root, "ctl")
    command = decode_text(payload.get("command_b64"))
    if not command:
        command = ":"

    check = control_check(payload, root)
    if check.returncode != 0:
        raise NativeError(
            "exit_transport",
            safe_detail(check.stderr.decode("utf-8", "replace")),
        )

    argv = [
        "ssh",
        "-T",
        "-S", ctl,
        "-o", "ControlMaster=no",
        "-o", f"ControlPath={ctl}",
        "-p", str(port),
        "-l", user,
        host,
        "bash", "-s",
    ]
    proc = run_process(argv, input_bytes=command.encode("utf-8"), timeout=1200)
    return {
        "ok": True,
        "rc": int(proc.returncode),
        "stdout_b64": encode_text(proc.stdout.decode("utf-8", "replace")),
        "stderr_b64": encode_text(proc.stderr.decode("utf-8", "replace")),
    }


def close_target(payload, root):
    host, user, port = target_args(payload)
    ctl = os.path.join(root, "ctl")
    if os.path.exists(ctl):
        run_process(
            [
                "ssh", "-S", ctl, "-O", "exit",
                "-p", str(port), "-l", user, host,
            ],
            timeout=8,
        )
    shutil.rmtree(root, ignore_errors=True)
    return {"ok": True}


class NativeError(Exception):
    def __init__(self, stage, detail):
        self.stage = stage
        self.detail = detail
        super().__init__(detail)


try:
    raw = sys.stdin.buffer.read()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    op = str(payload.get("op") or "")
    root = workspace(payload)

    if op == "open_password":
        known_hosts = open_password(payload, root)
        emit({"ok": True, "known_hosts_b64": encode_text(known_hosts)})
    elif op == "open_key":
        known_hosts = open_key(payload, root)
        emit({"ok": True, "known_hosts_b64": encode_text(known_hosts)})
    elif op == "run":
        emit(run_target(payload, root))
    elif op == "close":
        emit(close_target(payload, root))
    else:
        raise NativeError("iran_helper", "unsupported_operation")
except NativeError as exc:
    emit({"ok": False, "stage": exc.stage, "detail": safe_detail(exc.detail)})
except Exception as exc:
    emit({"ok": False, "stage": "iran_helper", "detail": safe_detail(exc)})
'''

_HELPER_B64 = base64.b64encode(_IRAN_HELPER_SOURCE.encode("utf-8")).decode("ascii")
_HELPER_COMMAND = (
    "python3 -c "
    + shlex.quote(
        "import base64;exec(base64.b64decode(" + repr(_HELPER_B64) + "))"
    )
)


def _hostkey_path(host: str, port: int) -> Path:
    digest = hashlib.sha256(f"{host}\0{int(port)}".encode("utf-8")).hexdigest()
    return _HOSTKEY_DIR / f"{digest}.known_hosts"


def _load_pinned_hostkey(host: str, port: int) -> str:
    path = _hostkey_path(host, port)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _store_pinned_hostkey(host: str, port: int, content: str) -> None:
    value = str(content or "").strip()
    if not value:
        raise NativeBootstrapError("exit_host_key", "known_hosts_empty_after_auth")
    _HOSTKEY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(_HOSTKEY_DIR, 0o700)
    except OSError:
        pass
    path = _hostkey_path(host, port)
    if path.exists():
        # Never silently replace a previously pinned Exit host key.
        current = path.read_text(encoding="utf-8").strip()
        if current and current != value:
            raise NativeBootstrapError("exit_host_key", "pinned_host_key_changed")
        return
    tmp = path.with_suffix(".tmp")
    tmp.write_text(value + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _decode_b64_text(value: str | None) -> str:
    if not value:
        return ""
    return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")


async def _helper_call(iran_conn, payload: dict[str, Any]) -> dict[str, Any]:
    # Payload (which may include an Exit password/private key/command script) is
    # intentionally sent only through stdin. It is never interpolated into the
    # remote command and therefore never appears in ps output.
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    try:
        result = await asyncio.wait_for(
            iran_conn.run(
                _HELPER_COMMAND,
                input=body,
                check=False,
            ),
            timeout=_HELPER_TIMEOUT_SECONDS
            if payload.get("op") != "run"
            else 1230,
        )
    except asyncio.TimeoutError as exc:
        raise NativeBootstrapError("iran_helper", "helper_timeout") from exc
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        raise NativeBootstrapError(
            "iran_ssh",
            str(exc).strip() or exc.__class__.__name__,
        ) from exc

    stdout = str(result.stdout or "").strip()
    stderr = str(result.stderr or "").strip()
    if int(result.exit_status or 0) != 0 and not stdout:
        raise NativeBootstrapError("iran_helper", stderr or "helper_failed")
    try:
        decoded = json.loads(stdout)
    except Exception as exc:
        raise NativeBootstrapError(
            "iran_helper",
            (stderr or stdout or "helper_invalid_response")[-1600:],
        ) from exc
    if not decoded.get("ok"):
        raise NativeBootstrapError(
            str(decoded.get("stage") or "iran_helper"),
            str(decoded.get("detail") or "unknown_error"),
        )
    return decoded


async def ensure_iran_native_ssh_dependencies(iran_conn) -> None:
    probe = await iran_conn.run(
        "command -v python3 >/dev/null 2>&1 && "
        "command -v ssh >/dev/null 2>&1 && "
        "command -v sshpass >/dev/null 2>&1",
        check=False,
    )
    if int(probe.exit_status or 0) == 0:
        return

    install = await iran_conn.run(
        "export DEBIAN_FRONTEND=noninteractive; "
        "for n in 1 2 3; do "
        "apt-get -o DPkg::Lock::Timeout=120 update -qq >/dev/null 2>&1 && break; "
        "[ $n -eq 3 ] && exit 71; sleep 2; done; "
        "apt-get -o DPkg::Lock::Timeout=120 install -y -qq "
        "python3 openssh-client sshpass >/dev/null 2>&1",
        check=False,
    )
    if int(install.exit_status or 0) != 0:
        raise NativeBootstrapError(
            "iran_dependency",
            "openssh_client_or_sshpass_install_failed",
        )


class NativeIranExitConnection:
    """Run Exit commands through native OpenSSH executing on one Iran node."""

    def __init__(
        self,
        iran_conn,
        *,
        host: str,
        port: int,
        username: str,
        token: str,
    ) -> None:
        self._iran_conn = iran_conn
        self.host = str(host)
        self.port = int(port)
        self.username = str(username or "root")
        self.token = token
        self._closed = False

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
        await ensure_iran_native_ssh_dependencies(iran_conn)
        token = secrets.token_hex(12)
        pinned = _load_pinned_hostkey(host, port)
        response = await _helper_call(
            iran_conn,
            {
                "op": "open_password",
                "token": token,
                "host": str(host),
                "port": int(port),
                "username": str(username or "root"),
                "password": str(password),
                "known_hosts_b64": base64.b64encode(pinned.encode()).decode("ascii")
                if pinned
                else "",
            },
        )
        known_hosts = _decode_b64_text(response.get("known_hosts_b64"))
        _store_pinned_hostkey(host, port, known_hosts)
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
        await ensure_iran_native_ssh_dependencies(iran_conn)
        token = secrets.token_hex(12)
        pinned = _load_pinned_hostkey(host, port)
        response = await _helper_call(
            iran_conn,
            {
                "op": "open_key",
                "token": token,
                "host": str(host),
                "port": int(port),
                "username": str(username or "root"),
                "private_key_b64": base64.b64encode(private_key.encode()).decode("ascii"),
                "known_hosts_b64": base64.b64encode(pinned.encode()).decode("ascii")
                if pinned
                else "",
            },
        )
        known_hosts = _decode_b64_text(response.get("known_hosts_b64"))
        _store_pinned_hostkey(host, port, known_hosts)
        return cls(
            iran_conn,
            host=host,
            port=port,
            username=username,
            token=token,
        )

    async def run(self, command: str, check: bool = False, **_kwargs) -> NativeSSHResult:
        if self._closed:
            raise NativeBootstrapError("exit_transport", "connection_closed")
        response = await _helper_call(
            self._iran_conn,
            {
                "op": "run",
                "token": self.token,
                "host": self.host,
                "port": self.port,
                "username": self.username,
                "command_b64": base64.b64encode(str(command).encode()).decode("ascii"),
            },
        )
        result = NativeSSHResult(
            stdout=_decode_b64_text(response.get("stdout_b64")),
            stderr=_decode_b64_text(response.get("stderr_b64")),
            exit_status=int(response.get("rc") or 0),
        )
        if check and result.exit_status != 0:
            raise RuntimeError(
                (result.stderr or result.stdout or f"command_exit_{result.exit_status}")[-1800:]
            )
        return result

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        try:
            await _helper_call(
                self._iran_conn,
                {
                    "op": "close",
                    "token": self.token,
                    "host": self.host,
                    "port": self.port,
                    "username": self.username,
                },
            )
        except BaseException:
            # ControlPersist is bounded, so a failed cleanup cannot leave a
            # permanent master. Still close the parent Iran connection below.
            pass
        try:
            self._iran_conn.close()
            await self._iran_conn.wait_closed()
        except BaseException:
            pass
