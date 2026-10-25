from __future__ import annotations

import base64
import json
import re
import shlex
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node
from ..modern_protocol_runtime import CONFIG_PATH, SERVICE_NAME
from ..node_runtime_connection import (
    connect_protocol_runtime,
    protocol_runtime_node_clause,
)


router = APIRouter(
    prefix="/v1/settings/vpn/outbounds",
    tags=["singbox-outbounds"],
    dependencies=[Depends(require_admin)],
)

_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_SUPPORTED = {"direct", "socks", "http"}
_REDACTED = "********"


class OutboundUpsertIn(BaseModel):
    type: Literal["direct", "socks", "http"]
    server: str | None = Field(default=None, max_length=255)
    server_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)
    set_default: bool = False


class OutboundDefaultIn(BaseModel):
    tag: str = Field(min_length=1, max_length=63)


def _valid_tag(raw: str) -> str:
    tag = str(raw or "").strip()
    if not _TAG_RE.fullmatch(tag):
        raise HTTPException(
            status_code=422,
            detail=(
                "Tag نامعتبر است؛ فقط حروف انگلیسی، عدد، نقطه، خط تیره و "
                "underscore مجاز است"
            ),
        )
    return tag


def _node(db: Session, node_id: int) -> Node:
    node = (
        db.query(Node)
        .filter(
            Node.id == int(node_id),
            Node.retired_at.is_(None),
            protocol_runtime_node_clause(),
        )
        .first()
    )
    if not node:
        raise HTTPException(
            status_code=404,
            detail="نود خروجی یا Local Core پیدا نشد",
        )
    return node


def _redact(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    secret = row.pop("password", None)
    row["has_password"] = bool(secret)
    if secret:
        row["password"] = _REDACTED
    return row


def _inventory_from_document(doc: dict[str, Any]) -> dict[str, Any]:
    raw_outbounds = doc.get("outbounds")
    outbounds = raw_outbounds if isinstance(raw_outbounds, list) else []
    rows: list[dict[str, Any]] = []
    for item in outbounds:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        kind = str(item.get("type") or "").strip().lower()
        if not tag:
            continue
        row = _redact(item)
        row["managed"] = kind in _SUPPORTED
        rows.append(row)

    route = doc.get("route") if isinstance(doc.get("route"), dict) else {}
    final = str(route.get("final") or "").strip() or None
    if final is None:
        # sing-box uses the first matching/default route when final is absent;
        # TwinPanel deliberately reports that as implicit instead of guessing.
        final_mode = "implicit"
    else:
        final_mode = "explicit"

    return {
        "outbounds": rows,
        "default_tag": final,
        "default_mode": final_mode,
    }


async def _read_document(conn) -> dict[str, Any]:
    result = await conn.run(
        f"cat {shlex.quote(CONFIG_PATH)}",
        check=False,
    )
    if result.exit_status != 0:
        raise HTTPException(
            status_code=409,
            detail="Sing-box config هنوز روی این نود ساخته نشده است",
        )
    try:
        doc = json.loads(result.stdout or "{}")
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Sing-box config روی نود JSON معتبر نیست",
        ) from exc
    if not isinstance(doc, dict):
        raise HTTPException(status_code=502, detail="Sing-box config معتبر نیست")
    return doc


def _mutation_script(
    *,
    action: str,
    tag: str,
    payload: dict[str, Any] | None = None,
) -> str:
    encoded = base64.b64encode(
        json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    return f'''from __future__ import annotations
import base64
import json
import os

CONFIG = {CONFIG_PATH!r}
ACTION = {action!r}
TAG = {tag!r}
PAYLOAD = json.loads(base64.b64decode({encoded!r}).decode("utf-8"))

with open(CONFIG, "r", encoding="utf-8") as handle:
    doc = json.load(handle)
if not isinstance(doc, dict):
    raise SystemExit("config_not_object")

outbounds = doc.get("outbounds")
if not isinstance(outbounds, list):
    outbounds = []

index = None
existing = None
for i, item in enumerate(outbounds):
    if isinstance(item, dict) and str(item.get("tag") or "") == TAG:
        index = i
        existing = item
        break

if ACTION == "upsert":
    kind = str(PAYLOAD.get("type") or "").strip().lower()
    if kind not in ("direct", "socks", "http"):
        raise SystemExit("unsupported_type")
    if TAG == "direct" and kind != "direct":
        raise SystemExit("reserved_direct_tag")
    if kind == "direct" and TAG != "direct":
        raise SystemExit("direct_tag_must_be_direct")

    fresh = {{"type": kind, "tag": TAG}}
    if kind in ("socks", "http"):
        server = str(PAYLOAD.get("server") or "").strip()
        port = int(PAYLOAD.get("server_port") or 0)
        if not server or not (1 <= port <= 65535):
            raise SystemExit("proxy_endpoint_required")
        fresh["server"] = server
        fresh["server_port"] = port
        username = PAYLOAD.get("username")
        password = PAYLOAD.get("password")
        if username is None and isinstance(existing, dict):
            username = existing.get("username")
        if password is None and isinstance(existing, dict):
            password = existing.get("password")
        if isinstance(username, str) and username:
            fresh["username"] = username
        if isinstance(password, str) and password:
            fresh["password"] = password

    if index is None:
        outbounds.append(fresh)
    else:
        outbounds[index] = fresh

    if bool(PAYLOAD.get("set_default")):
        route = doc.get("route")
        if not isinstance(route, dict):
            route = {{}}
        route["final"] = TAG
        doc["route"] = route

elif ACTION == "delete":
    if TAG == "direct":
        raise SystemExit("direct_cannot_be_deleted")
    if index is None:
        raise SystemExit("outbound_not_found")
    del outbounds[index]
    route = doc.get("route")
    if isinstance(route, dict) and str(route.get("final") or "") == TAG:
        route.pop("final", None)
        if route:
            doc["route"] = route
        else:
            doc.pop("route", None)

elif ACTION == "default":
    if index is None:
        raise SystemExit("outbound_not_found")
    route = doc.get("route")
    if not isinstance(route, dict):
        route = {{}}
    route["final"] = TAG
    doc["route"] = route

elif ACTION == "clear_default":
    route = doc.get("route")
    if isinstance(route, dict):
        route.pop("final", None)
        if route:
            doc["route"] = route
        else:
            doc.pop("route", None)
else:
    raise SystemExit("unknown_action")

doc["outbounds"] = outbounds
with open(CONFIG + ".new", "w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")
os.chmod(CONFIG + ".new", 0o600)
'''


async def _apply(conn, *, action: str, tag: str, payload: dict[str, Any] | None = None) -> None:
    script = _mutation_script(action=action, tag=tag, payload=payload)
    script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    command = f'''set -eu
CONFIG={shlex.quote(CONFIG_PATH)}
SERVICE={shlex.quote(SERVICE_NAME)}
BIN=/usr/local/bin/twinpanel-sing-box
if [ ! -x "$BIN" ]; then BIN="$(command -v sing-box || true)"; fi
[ -n "$BIN" ] || {{ echo singbox_binary_missing >&2; exit 41; }}
[ -s "$CONFIG" ] || {{ echo singbox_config_missing >&2; exit 42; }}
BACKUP="${{CONFIG}}.outbound-backup-$(date +%Y%m%d-%H%M%S)-$$"
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
        detail = str(result.stderr or result.stdout or "outbound_apply_failed").strip()
        raise HTTPException(
            status_code=502,
            detail={
                "message": "اعمال Outbound ناموفق بود؛ config قبلی حفظ/بازیابی شد",
                "error": detail[-1600:],
            },
        )


@router.get("")
async def inventory(db: Session = Depends(get_db)):
    nodes = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            protocol_runtime_node_clause(),
        )
        .order_by(Node.id.asc())
        .all()
    )
    payload: list[dict[str, Any]] = []
    for node in nodes:
        conn = None
        try:
            conn = await connect_protocol_runtime(node, db)
            doc = await _read_document(conn)
            data = _inventory_from_document(doc)
            state = await conn.run(
                f"systemctl is-active {shlex.quote(SERVICE_NAME)}.service",
                check=False,
            )
            payload.append({
                "id": node.id,
                "name": node.name,
                "public_ip": node.public_ip,
                "public_domain": node.public_domain,
                "service_active": state.exit_status == 0,
                "error": None,
                **data,
            })
        except HTTPException as exc:
            payload.append({
                "id": node.id,
                "name": node.name,
                "public_ip": node.public_ip,
                "public_domain": node.public_domain,
                "service_active": False,
                "outbounds": [],
                "default_tag": None,
                "default_mode": "implicit",
                "error": exc.detail,
            })
        except Exception as exc:
            payload.append({
                "id": node.id,
                "name": node.name,
                "public_ip": node.public_ip,
                "public_domain": node.public_domain,
                "service_active": False,
                "outbounds": [],
                "default_tag": None,
                "default_mode": "implicit",
                "error": str(exc)[:800],
            })
        finally:
            if conn is not None:
                conn.close()
                try:
                    await conn.wait_closed()
                except Exception:
                    pass
    return {
        "ok": True,
        "supported_types": ["direct", "socks", "http"],
        "nodes": payload,
    }


@router.put("/{node_id}/{tag}")
async def upsert_outbound(
    node_id: int,
    tag: str,
    payload: OutboundUpsertIn,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    clean_tag = _valid_tag(tag)
    kind = str(payload.type).lower()
    if clean_tag == "direct" and kind != "direct":
        raise HTTPException(status_code=422, detail="Tag direct رزرو شده است")
    if kind == "direct" and clean_tag != "direct":
        raise HTTPException(status_code=422, detail="Outbound مستقیم باید tag=direct داشته باشد")
    if kind in {"socks", "http"}:
        if not str(payload.server or "").strip() or payload.server_port is None:
            raise HTTPException(status_code=422, detail="آدرس و پورت Proxy الزامی است")

    data = payload.model_dump()
    data["server"] = str(payload.server or "").strip() or None
    if data.get("password") == _REDACTED:
        data["password"] = None

    conn = await connect_protocol_runtime(node, db)
    try:
        await _apply(conn, action="upsert", tag=clean_tag, payload=data)
        doc = await _read_document(conn)
        return {
            "ok": True,
            "node_id": node.id,
            "tag": clean_tag,
            **_inventory_from_document(doc),
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.delete("/{node_id}/{tag}")
async def delete_outbound(
    node_id: int,
    tag: str,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    clean_tag = _valid_tag(tag)
    if clean_tag == "direct":
        raise HTTPException(status_code=409, detail="Outbound پایه direct قابل حذف نیست")
    conn = await connect_protocol_runtime(node, db)
    try:
        await _apply(conn, action="delete", tag=clean_tag)
        doc = await _read_document(conn)
        return {"ok": True, "node_id": node.id, **_inventory_from_document(doc)}
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/default")
async def set_default_outbound(
    node_id: int,
    payload: OutboundDefaultIn,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    clean_tag = _valid_tag(payload.tag)
    conn = await connect_protocol_runtime(node, db)
    try:
        await _apply(conn, action="default", tag=clean_tag)
        doc = await _read_document(conn)
        return {"ok": True, "node_id": node.id, **_inventory_from_document(doc)}
    finally:
        conn.close()
        await conn.wait_closed()


@router.delete("/{node_id}/default")
async def clear_default_outbound(
    node_id: int,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        await _apply(conn, action="clear_default", tag="direct")
        doc = await _read_document(conn)
        return {"ok": True, "node_id": node.id, **_inventory_from_document(doc)}
    finally:
        conn.close()
        await conn.wait_closed()
