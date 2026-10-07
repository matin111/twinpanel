import base64
import json
import os
import shutil
import shlex
import signal
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


CLOCK_SKEW_SECONDS = 30
HISTORY_SECONDS = 7 * 24 * 3600

XRAY_BIN = "/usr/local/bin/xray"
XRAY_CONFIG_DEFAULT = (
    "/usr/local/etc/xray/config.json"
)
XRAY_API_DEFAULT = "127.0.0.1:10085"
XRAY_INBOUND_TAG_DEFAULT = "vless-in"


def _utc(value):
    value = str(value or "")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    result = datetime.fromisoformat(value)

    if result.tzinfo is None:
        raise ValueError("command time has no timezone")

    return result.astimezone(timezone.utc)


def _verify(cfg, command, node_id):
    if not isinstance(command, dict):
        raise ValueError("command is not an object")

    signature_b64 = command.get("signature")
    if not signature_b64:
        raise ValueError("missing signature")

    unsigned = dict(command)
    unsigned.pop("signature", None)

    if int(unsigned.get("version", 0)) != 1:
        raise ValueError("unsupported command version")

    if int(unsigned.get("node_id", 0)) != int(node_id):
        raise ValueError("wrong node_id")

    command_id = str(unsigned.get("command_id") or "")
    nonce = str(unsigned.get("nonce") or "")

    if not command_id:
        raise ValueError("missing command_id")

    if not nonce:
        raise ValueError("missing nonce")

    issued_at = _utc(unsigned.get("issued_at"))
    expires_at = _utc(unsigned.get("expires_at"))
    now = datetime.now(timezone.utc)

    if (
        issued_at > now
        and
        (issued_at - now).total_seconds()
        > CLOCK_SKEW_SECONDS
    ):
        raise ValueError("command issued in future")

    if now > expires_at:
        raise ValueError("command expired")

    if expires_at <= issued_at:
        raise ValueError("invalid command lifetime")

    public_raw = base64.b64decode(
        cfg["command_public_key_b64"],
        validate=True,
    )

    if len(public_raw) != 32:
        raise ValueError("invalid command public key")

    signature = base64.b64decode(
        signature_b64,
        validate=True,
    )

    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    Ed25519PublicKey.from_public_bytes(
        public_raw
    ).verify(
        signature,
        canonical,
    )

    return unsigned


def _ack(cfg, node_id, command_id, result, api_request):
    return api_request(
        cfg,
        "POST",
        (
            f"/v1/nodes/{node_id}"
            f"/quota/commands/{command_id}/ack"
        ),
        result,
    )


def _prune(state):
    results = state.setdefault(
        "command_results",
        {},
    )

    nonces = state.setdefault(
        "command_nonces",
        {},
    )

    cutoff = time.time() - HISTORY_SECONDS

    expired = [
        command_id
        for command_id, row in results.items()
        if float(row.get("handled_at", 0)) < cutoff
    ]

    for command_id in expired:
        row = results.pop(command_id, None) or {}
        nonce = row.get("nonce")

        if (
            nonce
            and nonces.get(nonce) == command_id
        ):
            nonces.pop(nonce, None)



def _xray_settings(cfg):
    config_path = Path(
        str(
            cfg.get(
                "xray_config_path",
                XRAY_CONFIG_DEFAULT,
            )
        )
    )

    api_server = str(
        cfg.get(
            "xray_api_server",
            XRAY_API_DEFAULT,
        )
    )

    inbound_tag = str(
        cfg.get(
            "xray_inbound_tag",
            XRAY_INBOUND_TAG_DEFAULT,
        )
    )

    return (
        config_path,
        api_server,
        inbound_tag,
    )


def _xray_device_identity(
    cfg,
    subscription_id,
):
    matches = []

    for device in cfg.get(
        "devices",
        [],
    ):
        if not isinstance(
            device,
            dict,
        ):
            continue

        protocol = str(
            device.get("protocol") or ""
        ).lower()

        if protocol not in (
            "xray",
            "v2ray",
        ):
            continue

        try:
            device_sub = int(
                device.get(
                    "subscription_id"
                )
            )
        except Exception:
            continue

        if (
            device_sub
            != int(subscription_id)
        ):
            continue

        matches.append(device)

    if len(matches) != 1:
        if str(unsigned.get("command_type","")) == "revoke_subscription":
            return {
                "identity": None,
                "already_absent": True,
            }

        raise ValueError(
            "xray device mapping "
            f"expected=1 found={len(matches)}"
        )

    email = str(
        matches[0].get("identity")
        or (
            f"mv-{int(subscription_id)}"
            "@moviline"
        )
    ).strip()

    if (
        not email
        or "\n" in email
        or "\r" in email
        or "\x00" in email
    ):
        raise ValueError(
            "invalid xray identity"
        )

    return email


def _load_xray_config(path):
    try:
        doc = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise RuntimeError(
            "cannot read xray config"
        ) from exc

    if not isinstance(doc, dict):
        raise RuntimeError(
            "xray config is not object"
        )

    return doc


def _atomic_xray_write(
    path,
    doc,
):
    raw = (
        json.dumps(
            doc,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )

    if not path.exists():
        raise RuntimeError(
            "xray config does not exist"
        )

    stat = path.stat()

    fd, tmp_name = tempfile.mkstemp(
        prefix=(
            "."
            + path.name
            + ".quota-"
        ),
        suffix=".json",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(
            tmp_name,
            stat.st_mode & 0o7777,
        )

        try:
            os.chown(
                tmp_name,
                stat.st_uid,
                stat.st_gid,
            )
        except PermissionError:
            pass

        test = subprocess.run(
            [
                XRAY_BIN,
                "run",
                "-test",
                "-config",
                tmp_name,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )

        if test.returncode != 0:
            message = (
                test.stderr.strip()
                or test.stdout.strip()
                or "unknown validation error"
            )

            raise RuntimeError(
                "xray config validation "
                f"failed: {message[:300]}"
            )

        backup = path.with_name(
            path.name
            + ".bak-quota-last"
        )

        shutil.copy2(
            path,
            backup,
        )

        os.replace(
            tmp_name,
            path,
        )

        tmp_name = None

    finally:
        if (
            tmp_name
            and os.path.exists(tmp_name)
        ):
            os.unlink(tmp_name)


def _remove_xray_persistent(
    cfg,
    email,
):
    (
        config_path,
        _,
        inbound_tag,
    ) = _xray_settings(cfg)

    doc = _load_xray_config(
        config_path
    )

    candidates = []

    for inbound in doc.get(
        "inbounds",
        [],
    ):
        if not isinstance(
            inbound,
            dict,
        ):
            continue

        if (
            inbound.get("protocol")
            != "vless"
        ):
            continue

        if (
            inbound.get("tag")
            != inbound_tag
        ):
            continue

        candidates.append(inbound)

    if len(candidates) != 1:
        raise RuntimeError(
            "vless inbound mapping "
            f"expected=1 found={len(candidates)}"
        )

    inbound = candidates[0]

    settings = inbound.setdefault(
        "settings",
        {},
    )

    clients = settings.setdefault(
        "clients",
        [],
    )

    if not isinstance(
        clients,
        list,
    ):
        raise RuntimeError(
            "xray clients is not list"
        )

    before = len(clients)

    clients[:] = [
        client
        for client in clients
        if not (
            isinstance(client, dict)
            and str(
                client.get("email") or ""
            )
            == email
        )
    ]

    removed = (
        before - len(clients)
    )

    if removed:
        _atomic_xray_write(
            config_path,
            doc,
        )

    return removed


def _remove_xray_runtime(
    cfg,
    email,
):
    (
        _,
        api_server,
        inbound_tag,
    ) = _xray_settings(cfg)

    proc = subprocess.run(
        [
            XRAY_BIN,
            "api",
            "rmu",
            f"--server={api_server}",
            f"-tag={inbound_tag}",
            email,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            "xray runtime remove failed: "
            + (
                proc.stderr.strip()
                or proc.stdout.strip()
                or (
                    "exit="
                    + str(
                        proc.returncode
                    )
                )
            )[:300]
        )

    return (
        proc.stdout.strip()
        or proc.stderr.strip()
    )


def _execute_xray_disconnect(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    payload = unsigned.get(
        "payload"
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "disconnect payload is not object"
        )

    try:
        subscription_id = int(
            payload.get(
                "subscription_id"
            )
        )
    except Exception as exc:
        raise ValueError(
            "invalid subscription_id"
        ) from exc

    if subscription_id <= 0:
        raise ValueError(
            "invalid subscription_id"
        )

    session_key = str(
        payload.get(
            "session_key"
        )
        or ""
    ).strip()

    if not session_key:
        raise ValueError(
            "missing session_key"
        )

    if len(session_key) > 160:
        raise ValueError(
            "session_key too long"
        )

    protocol = str(
        payload.get("protocol")
        or ""
    ).lower()

    if protocol not in (
        "xray",
        "v2ray",
    ):
        raise ValueError(
            "unsupported protocol"
        )

    reason = str(
        payload.get("reason")
        or "agent_disconnect"
    ).strip()

    # Stage 2 safety boundary:
    # only quota-exhaustion commands may
    # persistently revoke an Xray user.
    if reason != "quota_exhausted":
        raise ValueError(
            "unsupported disconnect reason"
        )

    email = _xray_device_identity(
        cfg,
        subscription_id,
    )

    removed_persistent = (
        _remove_xray_persistent(
            cfg,
            email,
        )
    )

    runtime_output = (
        _remove_xray_runtime(
            cfg,
            email,
        )
    )

    close_reply = api_request(
        cfg,
        "POST",
        (
            f"/v1/nodes/{node_id}"
            "/quota/sessions/close"
        ),
        {
            "session_key":
                session_key,
            "reason":
                reason,
        },
    )

    close_status = "unknown"

    if isinstance(
        close_reply,
        dict,
    ):
        close_status = str(
            close_reply.get(
                "status",
                "unknown",
            )
        )

    return {
        "status": "succeeded",
        "result_code":
            "xray_disconnect_ok",
        "result_message": (
            "xray quota revoke completed; "
            f"persistent_removed="
            f"{removed_persistent}; "
            f"session={close_status}; "
            f"runtime={runtime_output[:120]}"
        ),
    }



# =========================================================
# TWINPANEL_XRAY_SUBSCRIPTION_ENFORCEMENT_V1
# =========================================================

def _v3_xray_context(cfg):
    config_path = Path(
        str(
            cfg.get(
                "xray_config_path",
                XRAY_CONFIG_DEFAULT,
            )
        )
    )

    api_server = str(
        cfg.get(
            "xray_api_server",
            XRAY_API_DEFAULT,
        )
    )

    inbound_tag = str(
        cfg.get(
            "xray_inbound_tag",
            XRAY_INBOUND_TAG_DEFAULT,
        )
    )

    return (
        config_path,
        api_server,
        inbound_tag,
    )


def _v3_xray_document(cfg):
    (
        config_path,
        api_server,
        inbound_tag,
    ) = _v3_xray_context(cfg)

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        document = json.load(f)

    matches = [
        inbound
        for inbound
        in document.get(
            "inbounds",
            [],
        )
        if isinstance(inbound, dict)
        and inbound.get("tag")
            == inbound_tag
        and inbound.get("protocol")
            == "vless"
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "xray vless inbound is not unique"
        )

    return (
        config_path,
        api_server,
        inbound_tag,
        document,
        matches[0],
    )


def _v3_write_xray_document(
    cfg,
    document,
):
    (
        config_path,
        _,
        _,
    ) = _v3_xray_context(cfg)

    fd, temp_name = tempfile.mkstemp(
        prefix=(
            "."
            + config_path.name
            + ".enforcement-"
        ),
        suffix=".json",
        dir=str(config_path.parent),
    )

    os.close(fd)

    temp_path = Path(temp_name)

    try:
        with temp_path.open(
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                document,
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")

        if config_path.exists():
            stat_info = config_path.stat()

            os.chmod(
                temp_path,
                stat_info.st_mode & 0o777,
            )

            try:
                os.chown(
                    temp_path,
                    stat_info.st_uid,
                    stat_info.st_gid,
                )
            except PermissionError:
                pass

        proc = subprocess.run(
            [
                XRAY_BIN,
                "run",
                "-test",
                "-config",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                "xray config validation failed: "
                + (
                    proc.stderr.strip()
                    or proc.stdout.strip()
                    or str(proc.returncode)
                )[:400]
            )

        if config_path.exists():
            backup = Path(
                str(config_path)
                + ".bak-enforcement-last"
            )

            shutil.copy2(
                config_path,
                backup,
            )

        os.replace(
            temp_path,
            config_path,
        )

    finally:
        try:
            temp_path.unlink(
                missing_ok=True
            )
        except Exception:
            pass


def _v3_remove_xray_persistent(
    cfg,
    email,
):
    (
        _,
        _,
        _,
        document,
        inbound,
    ) = _v3_xray_document(cfg)

    clients = (
        inbound
        .setdefault(
            "settings",
            {},
        )
        .setdefault(
            "clients",
            [],
        )
    )

    matches = [
        client
        for client in clients
        if isinstance(client, dict)
        and client.get("email")
            == email
    ]

    if len(matches) > 1:
        raise RuntimeError(
            "duplicate xray email in config"
        )

    if not matches:
        return 0

    inbound["settings"]["clients"] = [
        client
        for client in clients
        if not (
            isinstance(client, dict)
            and client.get("email")
                == email
        )
    ]

    _v3_write_xray_document(
        cfg,
        document,
    )

    return 1


def _v3_add_xray_persistent(
    cfg,
    email,
    client_id,
):
    (
        _,
        _,
        _,
        document,
        inbound,
    ) = _v3_xray_document(cfg)

    clients = (
        inbound
        .setdefault(
            "settings",
            {},
        )
        .setdefault(
            "clients",
            [],
        )
    )

    matches = [
        client
        for client in clients
        if isinstance(client, dict)
        and client.get("email")
            == email
    ]

    if len(matches) > 1:
        raise RuntimeError(
            "duplicate xray email in config"
        )

    if matches:
        existing_id = str(
            matches[0].get("id")
            or ""
        )

        if existing_id != client_id:
            raise RuntimeError(
                "xray persistent UUID conflict"
            )

        return 0

    clients.append(
        {
            "id": client_id,
            "email": email,
        }
    )

    _v3_write_xray_document(
        cfg,
        document,
    )

    return 1


def _v3_runtime_remove(
    cfg,
    email,
):
    (
        _,
        api_server,
        inbound_tag,
    ) = _v3_xray_context(cfg)

    proc = subprocess.run(
        [
            XRAY_BIN,
            "api",
            "rmu",
            f"--server={api_server}",
            f"-tag={inbound_tag}",
            email,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            "xray runtime remove failed: "
            + (
                proc.stderr.strip()
                or proc.stdout.strip()
                or str(proc.returncode)
            )[:300]
        )

    return (
        proc.stdout.strip()
        or proc.stderr.strip()
    )


def _v3_runtime_restore(
    cfg,
    email,
    client_id,
):
    (
        _,
        api_server,
        _,
        _,
        inbound,
    ) = _v3_xray_document(cfg)

    # Always remove first.
    #
    # This makes restore safe even if:
    # - a previous ADU succeeded then agent crashed
    # - runtime contains an old UUID
    # - the same signed command is retried

    _v3_runtime_remove(
        cfg,
        email,
    )

    runtime_inbound = json.loads(
        json.dumps(inbound)
    )

    runtime_inbound.setdefault(
        "settings",
        {},
    )["clients"] = [
        {
            "id": client_id,
            "email": email,
        }
    ]

    fd, temp_name = tempfile.mkstemp(
        prefix=".xray-adu-",
        suffix=".json",
    )

    os.close(fd)

    temp_path = Path(temp_name)

    try:
        with temp_path.open(
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                {
                    "inbounds": [
                        runtime_inbound
                    ]
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")

        proc = subprocess.run(
            [
                XRAY_BIN,
                "api",
                "adu",
                f"--server={api_server}",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                "xray runtime restore failed: "
                + (
                    proc.stderr.strip()
                    or proc.stdout.strip()
                    or str(proc.returncode)
                )[:300]
            )

        return (
            proc.stdout.strip()
            or proc.stderr.strip()
        )

    finally:
        temp_path.unlink(
            missing_ok=True
        )


def _v3_subscription_payload(
    unsigned,
):
    payload = unsigned.get(
        "payload"
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "subscription payload is not object"
        )

    try:
        subscription_id = int(
            payload.get(
                "subscription_id"
            )
        )
    except Exception as exc:
        raise ValueError(
            "invalid subscription_id"
        ) from exc

    if subscription_id <= 0:
        raise ValueError(
            "invalid subscription_id"
        )

    protocol = str(
        payload.get("protocol")
        or ""
    ).lower()

    if protocol not in (
        "xray",
        "v2ray",
    ):
        raise ValueError(
            "unsupported protocol"
        )

    reason = str(
        payload.get("reason")
        or ""
    ).strip()

    return (
        payload,
        subscription_id,
        protocol,
        reason,
    )



# TWINPANEL_OPENCONNECT_SUBSCRIPTION_ENFORCEMENT_V1

def _v3_openconnect_payload(
    unsigned,
):
    payload = unsigned.get("payload")

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "missing subscription payload"
        )

    try:
        subscription_id = int(
            payload.get(
                "subscription_id"
            )
        )
    except Exception as exc:
        raise ValueError(
            "invalid subscription_id"
        ) from exc

    if subscription_id <= 0:
        raise ValueError(
            "invalid subscription_id"
        )

    protocol = str(
        payload.get("protocol")
        or ""
    ).lower()

    if protocol not in (
        "openconnect",
        "cisco",
    ):
        raise ValueError(
            "unsupported openconnect protocol"
        )

    reason = str(
        payload.get("reason")
        or ""
    ).strip()

    return (
        payload,
        subscription_id,
        protocol,
        reason,
    )


def _v3_openconnect_identity(
    cfg,
    subscription_id,
):
    rows = []

    for device in cfg.get(
        "devices",
        [],
    ):
        if not isinstance(
            device,
            dict,
        ):
            continue

        try:
            device_sub = int(
                device.get(
                    "subscription_id"
                )
            )
        except Exception:
            continue

        if (
            device_sub
            != int(subscription_id)
        ):
            continue

        protocol = str(
            device.get("protocol")
            or ""
        ).lower()

        if protocol not in (
            "openconnect",
            "cisco",
        ):
            continue

        identity = str(
            device.get("identity")
            or ""
        ).strip()

        if not identity:
            raise ValueError(
                "openconnect identity missing"
            )

        rows.append(identity)

    if len(rows) != 1:
        if str(unsigned.get("command_type","")) == "revoke_subscription":
            return None

        raise ValueError(
            "openconnect identity count="
            + str(len(rows))
        )

    return rows[0]


def _v3_openconnect_user_exists(
    username,
):
    path = Path(
        "/etc/ocserv/ocpasswd"
    )

    if not path.exists():
        return False

    for raw in path.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines():

        if (
            raw.split(
                ":",
                1,
            )[0].strip()
            == username
        ):
            return True

    return False


def _v3_openconnect_binary(
    name,
):
    path = shutil.which(name)

    if not path:
        raise RuntimeError(
            name + " binary not found"
        )

    return path


def _v3_openconnect_run(
    args,
):
    result = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )

    output = (
        (result.stdout or "")
        + "\n"
        + (result.stderr or "")
    ).strip()

    return (
        result.returncode,
        output,
    )


def _v3_openconnect_session_keys(
    cfg,
    node_id,
    payload,
    reason,
    api_request,
):
    session_keys = payload.get(
        "session_keys",
        [],
    )

    if session_keys is None:
        session_keys = []

    if not isinstance(
        session_keys,
        list,
    ):
        raise ValueError(
            "session_keys is not list"
        )

    if len(session_keys) > 100:
        raise ValueError(
            "too many session_keys"
        )

    closed = 0

    for key in session_keys:
        key = str(
            key or ""
        ).strip()

        if (
            not key
            or len(key) > 160
        ):
            raise ValueError(
                "invalid session_key"
            )

        api_request(
            cfg,
            "POST",
            (
                f"/v1/nodes/{node_id}"
                "/quota/sessions/close"
            ),
            {
                "session_key": key,
                "reason": reason,
            },
        )

        closed += 1

    return closed


def _execute_openconnect_revoke_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    (
        payload,
        subscription_id,
        _,
        reason,
    ) = _v3_openconnect_payload(
        unsigned
    )

    if reason not in {
        "admin_suspend",
        "subscription_expired",
        "subscription_deleted",
        "protocol_removed",
        "quota_exhausted",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported revoke reason"
        )

    username = (
        _v3_openconnect_identity(
            cfg,
            subscription_id,
        )
    )

    ocpasswd = (
        _v3_openconnect_binary(
            "ocpasswd"
        )
    )

    occtl = (
        _v3_openconnect_binary(
            "occtl"
        )
    )

    existed = (
        _v3_openconnect_user_exists(
            username
        )
    )

    locked = 0

    if existed:
        rc, output = (
            _v3_openconnect_run([
                ocpasswd,
                "-c",
                "/etc/ocserv/ocpasswd",
                "-l",
                username,
            ])
        )

        if rc != 0:
            raise RuntimeError(
                "ocpasswd lock failed: "
                + output[:200]
            )

        locked = 1

    rc, output = (
        _v3_openconnect_run([
            occtl,
            "terminate",
            "user",
            username,
        ])
    )

    if rc == 0:
        runtime = "terminated"

    elif (
        "could not terminate user"
        in output.lower()
    ):
        # No live session is already
        # the desired state.
        runtime = "no_active_session"

    else:
        raise RuntimeError(
            "occtl terminate failed: "
            + output[:200]
        )

    closed = (
        _v3_openconnect_session_keys(
            cfg,
            node_id,
            payload,
            reason,
            api_request,
        )
    )

    return {
        "status": "succeeded",
        "result_code":
            "openconnect_subscription_revoked",
        "result_message": (
            "openconnect subscription revoked; "
            f"credential_present={int(existed)}; "
            f"locked={locked}; "
            f"runtime={runtime}; "
            f"sessions_closed={closed}"
        ),
    }


def _execute_openconnect_restore_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    del node_id
    del api_request

    (
        _payload,
        subscription_id,
        _,
        reason,
    ) = _v3_openconnect_payload(
        unsigned
    )

    if reason not in {
        "admin_activate",
        "reconcile",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported restore reason"
        )

    username = (
        _v3_openconnect_identity(
            cfg,
            subscription_id,
        )
    )

    if not _v3_openconnect_user_exists(
        username
    ):
        # Never recreate a missing password
        # from an untrusted command payload.
        # Backend reconciliation owns that.
        raise RuntimeError(
            "openconnect credential missing; "
            "reconcile required"
        )

    ocpasswd = (
        _v3_openconnect_binary(
            "ocpasswd"
        )
    )

    rc, output = (
        _v3_openconnect_run([
            ocpasswd,
            "-c",
            "/etc/ocserv/ocpasswd",
            "-u",
            username,
        ])
    )

    if rc != 0:
        raise RuntimeError(
            "ocpasswd unlock failed: "
            + output[:200]
        )

    return {
        "status": "succeeded",
        "result_code":
            "openconnect_subscription_restored",
        "result_message": (
            "openconnect subscription restored; "
            f"username={username}"
        ),
    }




# TWINPANEL_WG_OPENVPN_SUBSCRIPTION_ENFORCEMENT_V1

WG_INTERFACE = "wg-access0"

WG_CONFIG = Path(
    "/etc/wireguard/wg-access0.conf"
)

OPENVPN_DISABLED_DIR = Path(
    "/etc/openvpn/twinpanel-disabled"
)

OPENVPN_MGMT_SOCKET = Path(
    "/run/openvpn-server/twinpanel-mgmt.sock"
)


def _v3_final_payload(
    unsigned,
    protocol,
):
    payload = unsigned.get(
        "payload"
    )

    if not isinstance(payload, dict):
        raise ValueError(
            "missing subscription payload"
        )

    try:
        subscription_id = int(
            payload.get(
                "subscription_id"
            )
        )
    except Exception as exc:
        raise ValueError(
            "invalid subscription_id"
        ) from exc

    if subscription_id <= 0:
        raise ValueError(
            "invalid subscription_id"
        )

    actual = str(
        payload.get(
            "protocol"
        )
        or ""
    ).lower()

    if actual != protocol:
        raise ValueError(
            "unexpected protocol"
        )

    reason = str(
        payload.get(
            "reason"
        )
        or ""
    ).strip()

    return (
        payload,
        subscription_id,
        reason,
    )


def _v3_final_device(
    cfg,
    subscription_id,
    protocol,
):
    rows = []

    for device in cfg.get(
        "devices",
        [],
    ):
        if not isinstance(
            device,
            dict,
        ):
            continue

        try:
            sid = int(
                device.get(
                    "subscription_id"
                )
            )
        except Exception:
            continue

        if sid != int(
            subscription_id
        ):
            continue

        if str(
            device.get(
                "protocol"
            )
            or ""
        ).lower() != protocol:
            continue

        rows.append(device)

    if len(rows) != 1:
        if str(unsigned.get("command_type","")) == "revoke_subscription":
            return None

        raise ValueError(
            f"{protocol} device count="
            + str(len(rows))
        )

    return rows[0]


# ==================================================
# WIREGUARD
# ==================================================

def _v3_wg_identity(
    cfg,
    subscription_id,
):
    device = _v3_final_device(
        cfg,
        subscription_id,
        "wireguard",
    )

    public_key = str(
        device.get("identity")
        or ""
    ).strip()

    allowed_ips = str(
        device.get("allowed_ips")
        or ""
    ).strip()

    if not public_key:
        raise ValueError(
            "wireguard public key missing"
        )

    if not allowed_ips:
        raise ValueError(
            "wireguard allowed_ips missing"
        )

    return (
        public_key,
        allowed_ips,
    )


def _v3_wg_peer_ranges(
    text,
):
    lines = text.splitlines(
        keepends=True
    )

    starts = [
        i
        for i, line in enumerate(lines)
        if line.strip().lower()
        == "[peer]"
    ]

    result = []

    for pos, start in enumerate(
        starts
    ):
        end = (
            starts[pos + 1]
            if pos + 1 < len(starts)
            else len(lines)
        )

        public_key = None
        allowed_ips = None

        for line in lines[
            start:end
        ]:
            stripped = line.strip()

            if "=" not in stripped:
                continue

            key, value = stripped.split(
                "=",
                1,
            )

            key = key.strip().lower()
            value = value.strip()

            if key == "publickey":
                public_key = value

            elif key == "allowedips":
                allowed_ips = value

        result.append({
            "start": start,
            "end": end,
            "public_key":
                public_key,
            "allowed_ips":
                allowed_ips,
        })

    return lines, result


def _v3_wg_write(
    text,
):
    if not WG_CONFIG.exists():
        raise RuntimeError(
            "WireGuard config missing"
        )

    st = WG_CONFIG.stat()

    fd, tmp = tempfile.mkstemp(
        prefix="wgtmp",
        suffix=".conf",
        dir=str(
            WG_CONFIG.parent
        ),
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as f:
            f.write(text)

            if not text.endswith(
                "\n"
            ):
                f.write("\n")

            f.flush()
            os.fsync(
                f.fileno()
            )

        test = subprocess.run(
            [
                "wg-quick",
                "strip",
                tmp,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )

        if test.returncode != 0:
            raise RuntimeError(
                "WireGuard config validation "
                "failed: "
                + (
                    test.stderr
                    or test.stdout
                    or ""
                )[:300]
            )

        os.chmod(
            tmp,
            st.st_mode & 0o777,
        )

        os.chown(
            tmp,
            st.st_uid,
            st.st_gid,
        )

        backup = Path(
            str(WG_CONFIG)
            + ".bak-enforcement-last"
        )

        shutil.copy2(
            WG_CONFIG,
            backup,
        )

        os.replace(
            tmp,
            WG_CONFIG,
        )

    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _v3_wg_remove_persistent(
    public_key,
):
    if not WG_CONFIG.exists():
        raise RuntimeError(
            "WireGuard config missing"
        )

    text = WG_CONFIG.read_text(
        encoding="utf-8",
        errors="strict",
    )

    lines, peers = (
        _v3_wg_peer_ranges(
            text
        )
    )

    matches = [
        peer
        for peer in peers
        if peer["public_key"]
        == public_key
    ]

    if len(matches) > 1:
        raise ValueError(
            "duplicate WireGuard peer"
        )

    if not matches:
        return 0

    target = matches[0]

    new = "".join(
        lines[
            :target["start"]
        ]
        + lines[
            target["end"]:
        ]
    )

    _v3_wg_write(new)

    return 1


def _v3_wg_add_persistent(
    public_key,
    allowed_ips,
):
    if not WG_CONFIG.exists():
        raise RuntimeError(
            "WireGuard config missing"
        )

    text = WG_CONFIG.read_text(
        encoding="utf-8",
        errors="strict",
    )

    _lines, peers = (
        _v3_wg_peer_ranges(
            text
        )
    )

    matching = [
        peer
        for peer in peers
        if peer["public_key"]
        == public_key
    ]

    if len(matching) > 1:
        raise ValueError(
            "duplicate WireGuard peer"
        )

    if matching:
        current = str(
            matching[0].get(
                "allowed_ips"
            )
            or ""
        ).strip()

        if current != allowed_ips:
            raise ValueError(
                "WireGuard peer "
                "AllowedIPs conflict"
            )

        return 0

    wanted = {
        x.strip()
        for x in allowed_ips.split(",")
        if x.strip()
    }

    for peer in peers:
        if (
            peer["public_key"]
            == public_key
        ):
            continue

        current = {
            x.strip()
            for x in str(
                peer.get(
                    "allowed_ips"
                )
                or ""
            ).split(",")
            if x.strip()
        }

        if wanted & current:
            raise ValueError(
                "WireGuard AllowedIPs "
                "collision"
            )

    block = (
        "\n[Peer]\n"
        f"PublicKey = {public_key}\n"
        f"AllowedIPs = {allowed_ips}\n"
    )

    new = (
        text.rstrip()
        + "\n"
        + block
    )

    _v3_wg_write(new)

    return 1


def _v3_wg_runtime_peers():
    result = subprocess.run(
        [
            "wg",
            "show",
            WG_INTERFACE,
            "peers",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "WireGuard interface unavailable: "
            + (
                result.stderr
                or result.stdout
                or ""
            )[:200]
        )

    return {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }


def _v3_wg_runtime_remove(
    public_key,
):
    if (
        public_key
        not in _v3_wg_runtime_peers()
    ):
        return 0

    result = subprocess.run(
        [
            "wg",
            "set",
            WG_INTERFACE,
            "peer",
            public_key,
            "remove",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "WireGuard runtime remove "
            "failed: "
            + (
                result.stderr
                or result.stdout
                or ""
            )[:200]
        )

    return 1


def _v3_wg_runtime_add(
    public_key,
    allowed_ips,
):
    result = subprocess.run(
        [
            "wg",
            "show",
            WG_INTERFACE,
            "allowed-ips",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "WireGuard runtime query "
            "failed"
        )

    wanted = {
        x.strip()
        for x in allowed_ips.split(",")
        if x.strip()
    }

    for raw in result.stdout.splitlines():
        parts = raw.split()

        if len(parts) < 2:
            continue

        peer_key = parts[0]

        current = {
            x.strip()
            for x in parts[1].split(",")
            if x.strip()
        }

        if (
            peer_key != public_key
            and wanted & current
        ):
            raise ValueError(
                "WireGuard runtime "
                "AllowedIPs collision"
            )

    result = subprocess.run(
        [
            "wg",
            "set",
            WG_INTERFACE,
            "peer",
            public_key,
            "allowed-ips",
            allowed_ips,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "WireGuard runtime restore "
            "failed: "
            + (
                result.stderr
                or result.stdout
                or ""
            )[:200]
        )

    return 1


def _execute_wireguard_revoke_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    (
        payload,
        subscription_id,
        reason,
    ) = _v3_final_payload(
        unsigned,
        "wireguard",
    )

    if reason not in {
        "admin_suspend",
        "subscription_expired",
        "subscription_deleted",
        "protocol_removed",
        "quota_exhausted",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported revoke reason"
        )

    (
        public_key,
        _allowed_ips,
    ) = _v3_wg_identity(
        cfg,
        subscription_id,
    )

    runtime_removed = (
        _v3_wg_runtime_remove(
            public_key
        )
    )

    # TWINPANEL_KEEP_WG_CREDENTIAL_ON_SUSPEND
    # فقط runtime قطع می‌شود.
    # peer دائمی حذف نمی‌شود تا activate بتواند همان اکانت را برگرداند.
    persistent_removed = False

    sessions_closed = (
        _v3_openconnect_session_keys(
            cfg,
            node_id,
            payload,
            reason,
            api_request,
        )
    )

    return {
        "status": "succeeded",
        "result_code":
            "wireguard_subscription_revoked",
        "result_message": (
            "wireguard subscription revoked; "
            f"runtime_removed={runtime_removed}; "
            f"persistent_removed={persistent_removed}; "
            f"sessions_closed={sessions_closed}"
        ),
    }


def _execute_wireguard_restore_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    del node_id
    del api_request

    (
        _payload,
        subscription_id,
        reason,
    ) = _v3_final_payload(
        unsigned,
        "wireguard",
    )

    if reason not in {
        "admin_activate",
        "reconcile",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported restore reason"
        )

    (
        public_key,
        allowed_ips,
    ) = _v3_wg_identity(
        cfg,
        subscription_id,
    )

    persistent_added = (
        _v3_wg_add_persistent(
            public_key,
            allowed_ips,
        )
    )

    runtime_added = (
        _v3_wg_runtime_add(
            public_key,
            allowed_ips,
        )
    )

    return {
        "status": "succeeded",
        "result_code":
            "wireguard_subscription_restored",
        "result_message": (
            "wireguard subscription restored; "
            f"persistent_added={persistent_added}; "
            f"runtime_added={runtime_added}"
        ),
    }


# ==================================================
# OPENVPN
# ==================================================

def _v3_openvpn_identity(
    cfg,
    subscription_id,
):
    device = _v3_final_device(
        cfg,
        subscription_id,
        "openvpn",
    )

    cn = str(
        device.get("identity")
        or ""
    ).strip()

    if not cn:
        raise ValueError(
            "OpenVPN common name missing"
        )

    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.@-"
    )

    if any(
        c not in allowed
        for c in cn
    ):
        raise ValueError(
            "invalid OpenVPN common name"
        )

    return cn


def _v3_openvpn_marker(
    cn,
):
    return (
        OPENVPN_DISABLED_DIR
        / cn
    )


def _v3_openvpn_disable(
    cn,
    subscription_id,
    reason,
):
    OPENVPN_DISABLED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.chmod(
        OPENVPN_DISABLED_DIR,
        0o755,
    )

    marker = _v3_openvpn_marker(
        cn
    )

    if marker.exists():
        return 0

    fd, tmp = tempfile.mkstemp(
        prefix=".disable-",
        dir=str(
            OPENVPN_DISABLED_DIR
        ),
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as f:
            f.write(
                f"subscription_id={subscription_id}\n"
                f"reason={reason}\n"
            )

            f.flush()
            os.fsync(
                f.fileno()
            )

        os.chmod(
            tmp,
            0o600,
        )

        os.replace(
            tmp,
            marker,
        )

    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    return 1


def _v3_openvpn_enable(
    cn,
):
    marker = _v3_openvpn_marker(
        cn
    )

    if not marker.exists():
        return 0

    marker.unlink()

    return 1


def _v3_openvpn_kill(
    cn,
):
    if not OPENVPN_MGMT_SOCKET.exists():
        raise RuntimeError(
            "OpenVPN management socket missing"
        )

    client = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )

    client.settimeout(2)

    try:
        client.connect(
            str(
                OPENVPN_MGMT_SOCKET
            )
        )

        try:
            client.recv(4096)
        except Exception:
            pass

        client.sendall(
            (
                "kill "
                + cn
                + "\n"
            ).encode()
        )

        time.sleep(0.15)

        chunks = []

        while True:
            try:
                part = client.recv(
                    4096
                )
            except socket.timeout:
                break

            if not part:
                break

            chunks.append(part)

            if b"\n" in part:
                break

        response = b"".join(
            chunks
        ).decode(
            errors="ignore"
        ).strip()

    finally:
        client.close()

    lower = response.lower()

    if (
        "common name" in lower
        and "not found" in lower
    ):
        return (
            "no_active_session"
        )

    if (
        "success" in lower
        or "killed" in lower
    ):
        return (
            response[:160]
            or "killed"
        )

    raise RuntimeError(
        "OpenVPN management kill "
        "failed: "
        + response[:200]
    )


def _execute_openvpn_revoke_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    (
        payload,
        subscription_id,
        reason,
    ) = _v3_final_payload(
        unsigned,
        "openvpn",
    )

    if reason not in {
        "admin_suspend",
        "subscription_expired",
        "subscription_deleted",
        "protocol_removed",
        "quota_exhausted",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported revoke reason"
        )

    cn = _v3_openvpn_identity(
        cfg,
        subscription_id,
    )

    disabled = (
        _v3_openvpn_disable(
            cn,
            subscription_id,
            reason,
        )
    )

    runtime = (
        _v3_openvpn_kill(
            cn
        )
    )

    sessions_closed = (
        _v3_openconnect_session_keys(
            cfg,
            node_id,
            payload,
            reason,
            api_request,
        )
    )

    return {
        "status": "succeeded",
        "result_code":
            "openvpn_subscription_revoked",
        "result_message": (
            "openvpn subscription revoked; "
            f"disabled={disabled}; "
            f"runtime={runtime}; "
            f"sessions_closed={sessions_closed}"
        ),
    }


def _execute_openvpn_restore_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    del node_id
    del api_request

    (
        _payload,
        subscription_id,
        reason,
    ) = _v3_final_payload(
        unsigned,
        "openvpn",
    )

    if reason not in {
        "admin_activate",
        "reconcile",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported restore reason"
        )

    cn = _v3_openvpn_identity(
        cfg,
        subscription_id,
    )

    enabled = (
        _v3_openvpn_enable(
            cn
        )
    )

    return {
        "status": "succeeded",
        "result_code":
            "openvpn_subscription_restored",
        "result_message": (
            "openvpn subscription restored; "
            f"enabled={enabled}; "
            f"common_name={cn}"
        ),
    }



# TWINPANEL_L2TP_SUBSCRIPTION_ENFORCEMENT_V1

L2TP_DISABLED_PREFIX = (
    "# TWINPANEL-L2TP-DISABLED "
)

L2TP_CHAP = Path(
    "/etc/ppp/chap-secrets"
)

L2TP_SESSION_DIR = Path(
    "/run/twinpanel-l2tp-sessions"
)


def _v3_l2tp_payload(unsigned):
    payload = unsigned.get("payload")

    if not isinstance(payload, dict):
        raise ValueError(
            "missing subscription payload"
        )

    try:
        subscription_id = int(
            payload.get("subscription_id")
        )
    except Exception as exc:
        raise ValueError(
            "invalid subscription_id"
        ) from exc

    if subscription_id <= 0:
        raise ValueError(
            "invalid subscription_id"
        )

    protocol = str(
        payload.get("protocol") or ""
    ).lower()

    if protocol != "l2tp":
        raise ValueError(
            "unsupported l2tp protocol"
        )

    reason = str(
        payload.get("reason") or ""
    ).strip()

    return (
        payload,
        subscription_id,
        reason,
    )


def _v3_l2tp_identity(
    cfg,
    subscription_id,
):
    identities = []

    for device in cfg.get(
        "devices",
        [],
    ):
        if not isinstance(device, dict):
            continue

        try:
            sid = int(
                device.get(
                    "subscription_id"
                )
            )
        except Exception:
            continue

        if sid != int(subscription_id):
            continue

        if str(
            device.get("protocol")
            or ""
        ).lower() != "l2tp":
            continue

        identity = str(
            device.get("identity")
            or ""
        ).strip()

        if not identity:
            raise ValueError(
                "l2tp identity missing"
            )

        identities.append(identity)

    if len(identities) != 1:
        raise ValueError(
            "l2tp identity count="
            + str(len(identities))
        )

    return identities[0]


def _v3_l2tp_atomic_write(lines):
    if not L2TP_CHAP.exists():
        raise RuntimeError(
            "chap-secrets missing"
        )

    st = L2TP_CHAP.stat()

    fd, tmp = tempfile.mkstemp(
        prefix=".chap-secrets.twinpanel.",
        dir=str(L2TP_CHAP.parent),
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as f:
            f.write(
                "\n".join(lines)
                + "\n"
            )

            f.flush()
            os.fsync(f.fileno())

        os.chmod(
            tmp,
            st.st_mode & 0o777,
        )

        os.chown(
            tmp,
            st.st_uid,
            st.st_gid,
        )

        os.replace(
            tmp,
            L2TP_CHAP,
        )

    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _v3_l2tp_state(username):
    if not L2TP_CHAP.exists():
        raise RuntimeError(
            "chap-secrets missing"
        )

    lines = L2TP_CHAP.read_text(
        encoding="utf-8",
        errors="strict",
    ).splitlines()

    active = []
    disabled = []

    for index, raw in enumerate(lines):
        stripped = raw.strip()

        if not stripped:
            continue

        if stripped.startswith(
            L2TP_DISABLED_PREFIX
        ):
            parts = stripped.split(
                " ",
                3,
            )

            if len(parts) != 4:
                continue

            try:
                marker_user = (
                    base64.b64decode(
                        parts[2]
                    )
                    .decode("utf-8")
                )

                original = (
                    base64.b64decode(
                        parts[3]
                    )
                    .decode("utf-8")
                )

            except Exception:
                continue

            if marker_user == username:
                disabled.append(
                    (
                        index,
                        original,
                    )
                )

            continue

        if stripped.startswith("#"):
            continue

        try:
            values = shlex.split(raw)
        except Exception:
            continue

        if (
            values
            and values[0] == username
        ):
            active.append(
                (
                    index,
                    raw,
                )
            )

    if len(active) > 1:
        raise ValueError(
            "duplicate active l2tp user"
        )

    if len(disabled) > 1:
        raise ValueError(
            "duplicate disabled l2tp user"
        )

    if active and disabled:
        raise ValueError(
            "l2tp user active and disabled"
        )

    return (
        lines,
        active,
        disabled,
    )


def _v3_l2tp_disable(username):
    (
        lines,
        active,
        disabled,
    ) = _v3_l2tp_state(
        username
    )

    if disabled:
        return 0

    if not active:
        raise RuntimeError(
            "l2tp credential missing; "
            "reconcile required"
        )

    index, original = active[0]

    user64 = base64.b64encode(
        username.encode("utf-8")
    ).decode("ascii")

    line64 = base64.b64encode(
        original.encode("utf-8")
    ).decode("ascii")

    lines[index] = (
        L2TP_DISABLED_PREFIX
        + user64
        + " "
        + line64
    )

    _v3_l2tp_atomic_write(
        lines
    )

    return 1


def _v3_l2tp_restore(username):
    (
        lines,
        active,
        disabled,
    ) = _v3_l2tp_state(
        username
    )

    if active:
        return 0

    if not disabled:
        raise RuntimeError(
            "l2tp disabled credential "
            "missing; reconcile required"
        )

    index, original = disabled[0]

    try:
        values = shlex.split(
            original
        )
    except Exception as exc:
        raise ValueError(
            "invalid saved chap line"
        ) from exc

    if (
        not values
        or values[0] != username
    ):
        raise ValueError(
            "saved l2tp identity mismatch"
        )

    lines[index] = original

    _v3_l2tp_atomic_write(
        lines
    )

    return 1


def _v3_l2tp_kill_sessions(
    username,
):
    if not L2TP_SESSION_DIR.exists():
        return 0

    killed = 0

    for path in (
        L2TP_SESSION_DIR.glob(
            "*.session"
        )
    ):
        try:
            parts = path.read_text(
                encoding="utf-8"
            ).strip().split("\t")

            if len(parts) < 2:
                continue

            stored_user = (
                base64.b64decode(
                    parts[0]
                )
                .decode("utf-8")
            )

            pid = int(parts[1])

        except Exception:
            continue

        if stored_user != username:
            continue

        proc = Path(
            f"/proc/{pid}/cmdline"
        )

        if not proc.exists():
            try:
                path.unlink()
            except Exception:
                pass

            continue

        try:
            cmdline = proc.read_bytes()
        except Exception:
            continue

        if b"pppd" not in cmdline:
            continue

        try:
            os.kill(
                pid,
                signal.SIGTERM,
            )

            killed += 1

        except ProcessLookupError:
            pass

        try:
            path.unlink()
        except Exception:
            pass

    return killed


def _execute_l2tp_revoke_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    (
        payload,
        subscription_id,
        reason,
    ) = _v3_l2tp_payload(
        unsigned
    )

    if reason not in {
        "admin_suspend",
        "subscription_expired",
        "subscription_deleted",
        "protocol_removed",
        "quota_exhausted",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported revoke reason"
        )

    username = _v3_l2tp_identity(
        cfg,
        subscription_id,
    )

    disabled = _v3_l2tp_disable(
        username
    )

    killed = _v3_l2tp_kill_sessions(
        username
    )

    closed = (
        _v3_openconnect_session_keys(
            cfg,
            node_id,
            payload,
            reason,
            api_request,
        )
    )

    return {
        "status": "succeeded",
        "result_code":
            "l2tp_subscription_revoked",
        "result_message": (
            "l2tp subscription revoked; "
            f"disabled={disabled}; "
            f"runtime_killed={killed}; "
            f"sessions_closed={closed}"
        ),
    }


def _execute_l2tp_restore_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    del node_id
    del api_request

    (
        _payload,
        subscription_id,
        reason,
    ) = _v3_l2tp_payload(
        unsigned
    )

    if reason not in {
        "admin_activate",
        "reconcile",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported restore reason"
        )

    username = _v3_l2tp_identity(
        cfg,
        subscription_id,
    )

    restored = _v3_l2tp_restore(
        username
    )

    return {
        "status": "succeeded",
        "result_code":
            "l2tp_subscription_restored",
        "result_message": (
            "l2tp subscription restored; "
            f"restored={restored}"
        ),
    }


def _execute_xray_revoke_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    (
        payload,
        subscription_id,
        _,
        reason,
    ) = _v3_subscription_payload(
        unsigned
    )

    allowed = {
        "admin_suspend",
        "subscription_expired",
        "subscription_deleted",
        "protocol_removed",
        "quota_exhausted",
        "stage3_test",
    }

    if reason not in allowed:
        raise ValueError(
            "unsupported revoke reason"
        )

    email = _xray_device_identity(
        cfg,
        subscription_id,
    )

    removed = (
        _v3_remove_xray_persistent(
            cfg,
            email,
        )
    )

    runtime = _v3_runtime_remove(
        cfg,
        email,
    )

    closed = 0

    session_keys = payload.get(
        "session_keys",
        [],
    )

    if session_keys is None:
        session_keys = []

    if not isinstance(
        session_keys,
        list,
    ):
        raise ValueError(
            "session_keys is not list"
        )

    if len(session_keys) > 100:
        raise ValueError(
            "too many session_keys"
        )

    for session_key in session_keys:
        session_key = str(
            session_key or ""
        ).strip()

        if (
            not session_key
            or len(session_key) > 160
        ):
            raise ValueError(
                "invalid session_key"
            )

        api_request(
            cfg,
            "POST",
            (
                f"/v1/nodes/{node_id}"
                "/quota/sessions/close"
            ),
            {
                "session_key":
                    session_key,
                "reason":
                    reason,
            },
        )

        closed += 1

    return {
        "status": "succeeded",
        "result_code":
            "xray_subscription_revoked",
        "result_message": (
            "xray subscription revoked; "
            f"persistent_removed={removed}; "
            f"sessions_closed={closed}; "
            f"runtime={runtime[:100]}"
        ),
    }


def _execute_xray_restore_subscription(
    cfg,
    node_id,
    unsigned,
    api_request,
):
    del node_id
    del api_request

    (
        payload,
        subscription_id,
        _,
        reason,
    ) = _v3_subscription_payload(
        unsigned
    )

    if reason not in {
        "admin_activate",
        "reconcile",
        "stage3_test",
    }:
        raise ValueError(
            "unsupported restore reason"
        )

    email = _xray_device_identity(
        cfg,
        subscription_id,
    )

    client = payload.get(
        "client"
    )

    if not isinstance(
        client,
        dict,
    ):
        raise ValueError(
            "missing restore client"
        )

    client_id = str(
        client.get("id")
        or ""
    ).strip()

    supplied_email = str(
        client.get("email")
        or ""
    ).strip()

    if supplied_email != email:
        raise ValueError(
            "restore email mismatch"
        )

    try:
        parsed = uuid.UUID(
            client_id
        )
    except Exception as exc:
        raise ValueError(
            "invalid restore UUID"
        ) from exc

    if str(parsed) != client_id.lower():
        raise ValueError(
            "non-canonical restore UUID"
        )

    added = _v3_add_xray_persistent(
        cfg,
        email,
        client_id,
    )

    runtime = _v3_runtime_restore(
        cfg,
        email,
        client_id,
    )

    return {
        "status": "succeeded",
        "result_code":
            "xray_subscription_restored",
        "result_message": (
            "xray subscription restored; "
            f"persistent_added={added}; "
            f"runtime={runtime[:120]}"
        ),
    }


def process_commands(
    cfg,
    state,
    node_id,
    api_request,
    save_state,
    log,
):
    _prune(state)

    results = state.setdefault(
        "command_results",
        {},
    )

    nonces = state.setdefault(
        "command_nonces",
        {},
    )

    commands = api_request(
        cfg,
        "GET",
        f"/v1/nodes/{node_id}/quota/commands",
    )

    if not isinstance(commands, list):
        raise RuntimeError(
            "invalid command response"
        )

    for command in commands:
        command_id = str(
            command.get("command_id") or ""
        )

        existing = results.get(command_id)

        if existing:
            try:
                _ack(
                    cfg,
                    node_id,
                    command_id,
                    existing["result"],
                    api_request,
                )
            except Exception as exc:
                log(
                    "command ACK retry failed "
                    f"{command_id} {exc!r}"
                )

            continue

        try:
            unsigned = _verify(
                cfg,
                command,
                node_id,
            )
        except Exception as exc:
            log(
                "command rejected before execution "
                f"id={command_id or '?'} "
                f"error={exc!r}"
            )
            continue

        nonce = str(unsigned["nonce"])

        previous = nonces.get(nonce)

        if (
            previous is not None
            and previous != command_id
        ):
            log(
                "command replay blocked "
                f"id={command_id} "
                f"nonce={nonce}"
            )
            continue

        command_type = str(
            unsigned.get("command_type") or ""
        )

        if command_type == "noop":
            result = {
                "status": "succeeded",
                "result_code": "ok",
                "result_message":
                    "verified noop command executed",
            }

        elif command_type == "disconnect_session":
            payload = unsigned.get("payload")

            protocol = ""

            if isinstance(payload, dict):
                protocol = str(
                    payload.get("protocol") or ""
                ).lower()

            # Other protocols stay pending until
            # their dedicated safe handlers exist.
            if protocol not in ("xray", "v2ray"):
                log(
                    "command verified but deferred "
                    f"id={command_id} "
                    f"type={command_type} "
                    f"protocol={protocol or '?'}"
                )
                continue

            try:
                result = _execute_xray_disconnect(
                    cfg,
                    node_id,
                    unsigned,
                    api_request,
                )

            except ValueError as exc:
                result = {
                    "status": "rejected",
                    "result_code":
                        "invalid_disconnect_command",
                    "result_message":
                        str(exc)[:300],
                }

            except Exception as exc:
                # No ACK for transient execution
                # failures. The signed command stays
                # pending and is retried. The Xray
                # remove operation is idempotent.
                log(
                    "command execution retryable "
                    f"failure id={command_id} "
                    f"type={command_type} "
                    f"error={exc!r}"
                )
                continue

        elif command_type in (
            "revoke_subscription",
            "restore_subscription",
        ):
            try:
                payload = unsigned.get(
                    "payload"
                )

                protocol = ""

                if isinstance(
                    payload,
                    dict,
                ):
                    protocol = str(
                        payload.get(
                            "protocol"
                        )
                        or ""
                    ).lower()

                if protocol in (
                    "xray",
                    "v2ray",
                ):
                    if (
                        command_type
                        == "revoke_subscription"
                    ):
                        result = (
                            _execute_xray_revoke_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )
                    else:
                        result = (
                            _execute_xray_restore_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )

                elif protocol in (
                    "openconnect",
                    "cisco",
                ):
                    if (
                        command_type
                        == "revoke_subscription"
                    ):
                        result = (
                            _execute_openconnect_revoke_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )
                    else:
                        result = (
                            _execute_openconnect_restore_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )

                elif protocol == "l2tp":
                    if (
                        command_type
                        == "revoke_subscription"
                    ):
                        result = (
                            _execute_l2tp_revoke_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )
                    else:
                        result = (
                            _execute_l2tp_restore_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )

                elif protocol == "wireguard":
                    if (
                        command_type
                        == "revoke_subscription"
                    ):
                        result = (
                            _execute_wireguard_revoke_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )
                    else:
                        result = (
                            _execute_wireguard_restore_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )

                elif protocol == "openvpn":
                    if (
                        command_type
                        == "revoke_subscription"
                    ):
                        result = (
                            _execute_openvpn_revoke_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )
                    else:
                        result = (
                            _execute_openvpn_restore_subscription(
                                cfg,
                                node_id,
                                unsigned,
                                api_request,
                            )
                        )

                else:
                    raise ValueError(
                        "unsupported subscription protocol"
                    )

            except ValueError as exc:
                message = str(exc)

                if (
                    command_type == "revoke_subscription"
                    and any(
                        x in message
                        for x in [
                            "device count=0",
                            "identity count=0",
                            "mapping expected=1 found=0",
                        ]
                    )
                ):
                    result = {
                        "status": "succeeded",
                        "result_code": "already_revoked",
                        "result_message": message,
                    }

                else:
                    result = {
                        "status": "rejected",
                        "result_code":
                            "invalid_subscription_command",
                        "result_message":
                            message[:300],
                    }

            except Exception as exc:
                log(
                    "command execution retryable "
                    f"failure id={command_id} "
                    f"type={command_type} "
                    f"error={exc!r}"
                )
                continue

        else:
            log(
                "command verified but deferred "
                f"id={command_id} "
                f"type={command_type}"
            )
            continue

        results[command_id] = {
            "nonce": nonce,
            "handled_at": time.time(),
            "result": result,
        }

        nonces[nonce] = command_id

        # Persist BEFORE ACK.
        # If the agent crashes after execution,
        # it will only resend the ACK.
        save_state(state)

        try:
            reply = _ack(
                cfg,
                node_id,
                command_id,
                result,
                api_request,
            )

            log(
                "command completed "
                f"id={command_id} "
                f"type={command_type} "
                f"ack="
                f"{reply.get('status') if isinstance(reply, dict) else '?'}"
            )

        except Exception as exc:
            log(
                "command executed; ACK pending "
                f"id={command_id} "
                f"error={exc!r}"
            )
