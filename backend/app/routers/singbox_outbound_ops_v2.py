from __future__ import annotations

import base64
import json
import shlex
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_runtime_connection import connect_protocol_runtime
from ..singbox_outbound_import import IMPORTABLE_TYPES
from .singbox_outbounds import (
    CONFIG_PATH,
    SERVICE_NAME,
    _inventory_from_document,
    _node,
    _read_document,
    _valid_tag,
)


router = APIRouter(
    prefix="/v1/settings/vpn/outbounds",
    tags=["singbox-outbounds-v2"],
    dependencies=[Depends(require_admin)],
)


class OutboundEditIn(BaseModel):
    server: str | None = Field(default=None, max_length=255)
    server_port: int | None = Field(default=None, ge=1, le=65535)
    host: str | None = Field(default=None, max_length=512)
    path: str | None = Field(default=None, max_length=2048)
    sni: str | None = Field(default=None, max_length=255)


def _find_imported(doc: dict[str, Any], tag: str) -> dict[str, Any]:
    outbounds = doc.get("outbounds") if isinstance(doc.get("outbounds"), list) else []
    target = next(
        (
            item
            for item in outbounds
            if isinstance(item, dict) and str(item.get("tag") or "") == tag
        ),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Outbound پیدا نشد")
    kind = str(target.get("type") or "").strip().lower()
    if kind not in IMPORTABLE_TYPES or not tag.startswith("ext-"):
        raise HTTPException(
            status_code=409,
            detail="ویرایش و تست پیشرفته فقط برای کانفیگ‌های واردشده فعال است",
        )
    return target


def _edit_mutation_script(*, tag: str, payload: dict[str, Any]) -> str:
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    importable_types = sorted(IMPORTABLE_TYPES)
    return f'''from __future__ import annotations
import base64
import json
import os

CONFIG = {CONFIG_PATH!r}
TAG = {tag!r}
PAYLOAD = json.loads(base64.b64decode({encoded!r}).decode("utf-8"))
IMPORTABLE_TYPES = set({importable_types!r})

with open(CONFIG, "r", encoding="utf-8") as handle:
    doc = json.load(handle)
if not isinstance(doc, dict):
    raise SystemExit("config_not_object")

outbounds = doc.get("outbounds")
if not isinstance(outbounds, list):
    raise SystemExit("outbounds_missing")

target = None
for item in outbounds:
    if isinstance(item, dict) and str(item.get("tag") or "") == TAG:
        target = item
        break
if target is None:
    raise SystemExit("outbound_not_found")

kind = str(target.get("type") or "").strip().lower()
if kind not in IMPORTABLE_TYPES or not TAG.startswith("ext-"):
    raise SystemExit("outbound_not_managed_import")

if "server" in PAYLOAD:
    server = str(PAYLOAD.get("server") or "").strip()
    if not server or any(ch.isspace() for ch in server):
        raise SystemExit("invalid_server")
    target["server"] = server

if "server_port" in PAYLOAD:
    port = int(PAYLOAD.get("server_port") or 0)
    if not 1 <= port <= 65535:
        raise SystemExit("invalid_server_port")
    target["server_port"] = port

transport = target.get("transport")
if "host" in PAYLOAD or "path" in PAYLOAD:
    if not isinstance(transport, dict):
        raise SystemExit("transport_not_configured")

if "host" in PAYLOAD:
    headers = transport.get("headers")
    if not isinstance(headers, dict):
        headers = {{}}
    host = str(PAYLOAD.get("host") or "").strip()
    if host:
        headers["Host"] = host
    else:
        headers.pop("Host", None)
        headers.pop("host", None)
    if headers:
        transport["headers"] = headers
    else:
        transport.pop("headers", None)

if "path" in PAYLOAD:
    path = str(PAYLOAD.get("path") or "").strip()
    if path:
        if not path.startswith("/"):
            path = "/" + path
        transport["path"] = path
    else:
        transport.pop("path", None)

if "sni" in PAYLOAD:
    tls = target.get("tls")
    if not isinstance(tls, dict) or not bool(tls.get("enabled", True)):
        raise SystemExit("tls_not_configured")
    sni = str(PAYLOAD.get("sni") or "").strip()
    if sni:
        tls["server_name"] = sni
    else:
        tls.pop("server_name", None)

with open(CONFIG + ".new", "w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")
os.chmod(CONFIG + ".new", 0o600)
'''


async def _apply_edit(conn, *, tag: str, payload: dict[str, Any]) -> None:
    script = _edit_mutation_script(tag=tag, payload=payload)
    script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    command = f'''set -eu
CONFIG={shlex.quote(CONFIG_PATH)}
SERVICE={shlex.quote(SERVICE_NAME)}
BIN=/usr/local/bin/twinpanel-sing-box
if [ ! -x "$BIN" ]; then BIN="$(command -v sing-box || true)"; fi
[ -n "$BIN" ] || {{ echo singbox_binary_missing >&2; exit 41; }}
[ -s "$CONFIG" ] || {{ echo singbox_config_missing >&2; exit 42; }}
BACKUP="${{CONFIG}}.outbound-edit-backup-$(date +%Y%m%d-%H%M%S)-$$"
cp -a "$CONFIG" "$BACKUP"
cleanup() {{ rm -f "${{CONFIG}}.new"; }}
trap cleanup EXIT
printf '%s' {shlex.quote(script_b64)} | base64 -d | python3
"$BIN" check -c "${{CONFIG}}.new"
mv "${{CONFIG}}.new" "$CONFIG"
chmod 600 "$CONFIG"
if ! systemctl restart "${{SERVICE}}.service"; then
  cp -a "$BACKUP" "$CONFIG"
  systemctl restart "${{SERVICE}}.service" >/dev/null 2>&1 || true
  echo singbox_restart_failed_rolled_back >&2
  exit 43
fi
systemctl is-active --quiet "${{SERVICE}}.service" || {{
  cp -a "$BACKUP" "$CONFIG"
  systemctl restart "${{SERVICE}}.service" >/dev/null 2>&1 || true
  echo singbox_not_active_rolled_back >&2
  exit 44
}}
echo "$BACKUP"
'''
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        detail = str(result.stderr or result.stdout or "outbound_edit_failed").strip()
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ویرایش Outbound ناموفق بود؛ config قبلی بازیابی شد",
                "error": detail[-1600:],
            },
        )


def _test_script(tag: str) -> str:
    return f'''from __future__ import annotations
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time

CONFIG = {CONFIG_PATH!r}
TAG = {tag!r}
result = {{
    "ok": False,
    "tag": TAG,
    "tcp_ok": False,
    "tcp_ms": None,
    "e2e_ok": False,
    "exit_ip": None,
    "http_code": None,
    "latency_ms": None,
    "error": None,
}}
process = None
config_path = None
log_path = None
try:
    with open(CONFIG, "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    outbounds = doc.get("outbounds") if isinstance(doc.get("outbounds"), list) else []
    target = next(
        (item for item in outbounds if isinstance(item, dict) and str(item.get("tag") or "") == TAG),
        None,
    )
    if target is None:
        raise RuntimeError("outbound_not_found")
    kind = str(target.get("type") or "").strip().lower()
    if kind not in {sorted(IMPORTABLE_TYPES)!r} or not TAG.startswith("ext-"):
        raise RuntimeError("outbound_not_managed_import")

    server = str(target.get("server") or "").strip()
    server_port = int(target.get("server_port") or 0)
    if not server or not 1 <= server_port <= 65535:
        raise RuntimeError("outbound_endpoint_missing")

    started = time.perf_counter()
    sock = socket.create_connection((server, server_port), timeout=6)
    sock.close()
    result["tcp_ok"] = True
    result["tcp_ms"] = round((time.perf_counter() - started) * 1000, 1)

    binary = "/usr/local/bin/twinpanel-sing-box"
    if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        binary = shutil.which("sing-box") or ""
    if not binary:
        raise RuntimeError("singbox_binary_missing")
    curl = shutil.which("curl") or ""
    if not curl:
        raise RuntimeError("curl_missing")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    local_port = int(listener.getsockname()[1])
    listener.close()

    test_doc = {{
        "log": {{"level": "error", "timestamp": True}},
        "inbounds": [{{
            "type": "mixed",
            "tag": "twinpanel-outbound-test",
            "listen": "127.0.0.1",
            "listen_port": local_port,
        }}],
        "outbounds": outbounds,
        "route": {{"final": TAG}},
    }}
    if isinstance(doc.get("dns"), dict):
        test_doc["dns"] = doc["dns"]
    if isinstance(doc.get("endpoints"), list):
        test_doc["endpoints"] = doc["endpoints"]

    fd, config_path = tempfile.mkstemp(prefix="twinpanel-outbound-test-", suffix=".json")
    os.close(fd)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(test_doc, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
    os.chmod(config_path, 0o600)

    checked = subprocess.run(
        [binary, "check", "-c", config_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=12,
        check=False,
    )
    if checked.returncode != 0:
        raise RuntimeError("test_config_invalid: " + (checked.stderr or checked.stdout)[-800:])

    log_fd, log_path = tempfile.mkstemp(prefix="twinpanel-outbound-test-", suffix=".log")
    os.close(log_fd)
    log_handle = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen(
        [binary, "run", "-c", config_path],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    ready = False
    for _ in range(30):
        if process.poll() is not None:
            break
        try:
            probe = socket.create_connection(("127.0.0.1", local_port), timeout=0.2)
            probe.close()
            ready = True
            break
        except OSError:
            time.sleep(0.1)
    if not ready:
        log_handle.close()
        detail = ""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                detail = handle.read()[-800:]
        except Exception:
            pass
        raise RuntimeError("test_core_not_ready: " + detail)

    proxy = f"127.0.0.1:{{local_port}}"
    ip_run = subprocess.run(
        [curl, "-4", "-sS", "--socks5-hostname", proxy,
         "--connect-timeout", "8", "--max-time", "20", "https://api.ipify.org"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=25,
        check=False,
    )
    if ip_run.returncode != 0 or not (ip_run.stdout or "").strip():
        raise RuntimeError("egress_ip_failed: " + (ip_run.stderr or "")[-500:])
    result["exit_ip"] = (ip_run.stdout or "").strip()[:128]

    web_run = subprocess.run(
        [curl, "-4", "-sS", "-o", "/dev/null", "--socks5-hostname", proxy,
         "--connect-timeout", "8", "--max-time", "20",
         "-w", "%{{http_code}}|%{{time_total}}", "https://www.cloudflare.com/"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=25,
        check=False,
    )
    if web_run.returncode != 0:
        raise RuntimeError("https_probe_failed: " + (web_run.stderr or "")[-500:])
    raw = (web_run.stdout or "").strip().split("|", 1)
    result["http_code"] = int(raw[0]) if raw and raw[0].isdigit() else None
    if len(raw) > 1:
        try:
            result["latency_ms"] = round(float(raw[1]) * 1000, 1)
        except Exception:
            pass
    result["e2e_ok"] = bool(result["http_code"] and 200 <= int(result["http_code"]) < 500)
    result["ok"] = bool(result["tcp_ok"] and result["e2e_ok"] and result["exit_ip"])
except Exception as exc:
    result["error"] = str(exc)[:1200]
finally:
    if process is not None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    for path in (config_path, log_path):
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass
print(json.dumps(result, ensure_ascii=False))
'''


@router.patch("/{node_id}/{tag}")
async def edit_imported_outbound(
    node_id: int,
    tag: str,
    payload: OutboundEditIn,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    clean_tag = _valid_tag(tag)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="حداقل یک مقدار برای ویرایش لازم است")
    if "server" in changes:
        changes["server"] = str(changes.get("server") or "").strip()
        if not changes["server"] or any(ch.isspace() for ch in changes["server"]):
            raise HTTPException(status_code=422, detail="آدرس/IP معتبر وارد کنید")
    for field in ("host", "path", "sni"):
        if field in changes and changes[field] is not None:
            changes[field] = str(changes[field]).strip()

    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        _find_imported(doc, clean_tag)
        await _apply_edit(conn, tag=clean_tag, payload=changes)
        fresh = await _read_document(conn)
        return {
            "ok": True,
            "node_id": node.id,
            "tag": clean_tag,
            **_inventory_from_document(fresh),
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/{tag}/test")
async def test_imported_outbound(
    node_id: int,
    tag: str,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    clean_tag = _valid_tag(tag)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        _find_imported(doc, clean_tag)
        script = _test_script(clean_tag)
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        command = (
            f"printf '%s' {shlex.quote(encoded)} | base64 -d | "
            "python3"
        )
        result = await conn.run(command, check=False, timeout=75)
        if result.exit_status != 0:
            detail = str(result.stderr or result.stdout or "outbound_test_failed").strip()
            raise HTTPException(
                status_code=502,
                detail={"message": "تست Outbound اجرا نشد", "error": detail[-1600:]},
            )
        lines = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise HTTPException(status_code=502, detail="تست Outbound نتیجه‌ای برنگرداند")
        try:
            data = json.loads(lines[-1])
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"message": "پاسخ تست Outbound معتبر نیست", "error": lines[-1][-1200:]},
            ) from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="پاسخ تست Outbound معتبر نیست")
        return {"node_id": node.id, **data}
    finally:
        conn.close()
        await conn.wait_closed()
