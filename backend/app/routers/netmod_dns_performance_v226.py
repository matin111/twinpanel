from __future__ import annotations

import ipaddress
import shlex
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from .dns_emergency import _connect, _parse_lines, _run_script
from .netmod_dns import (
    DNSTT_BINARY_PATH,
    DNSTT_PORT,
    DNSTT_SERVICE,
    ENGINE,
    PASSWORD_PATH,
    PRIVATE_KEY_PATH,
    SSH_PORT,
    SSH_USER,
    _eligible_exit,
    _netmod_encrypt_payload,
    _setting,
)


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["netmod-dns-performance"],
    dependencies=[Depends(require_admin)],
)

PERFORMANCE_DROPIN_DIR = f"/etc/systemd/system/{DNSTT_SERVICE}.d"
PERFORMANCE_DROPIN_PATH = f"{PERFORMANCE_DROPIN_DIR}/10-performance.conf"
DEFAULT_DNSTT_MTU = 1232
MIN_DNSTT_MTU = 512
MAX_DNSTT_MTU = 1452
RESOLVER_PRESETS: tuple[tuple[str, str], ...] = (
    ("Google", "8.8.8.8"),
    ("Cloudflare", "1.1.1.1"),
    ("Quad9", "9.9.9.9"),
    ("OpenDNS", "208.67.222.222"),
)


class NetModMtuIn(BaseModel):
    mtu: int = Field(ge=MIN_DNSTT_MTU, le=MAX_DNSTT_MTU)


def _validated_mtu(value: int) -> int:
    mtu = int(value)
    if mtu < MIN_DNSTT_MTU or mtu > MAX_DNSTT_MTU:
        raise HTTPException(
            status_code=422,
            detail=f"MTU باید بین {MIN_DNSTT_MTU} و {MAX_DNSTT_MTU} باشد",
        )
    return mtu


def _profile_payload(*, node: Any, setting: Any, resolver: str, password: str) -> dict[str, str]:
    try:
        resolver_ip = ipaddress.ip_address(str(resolver)).compressed
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Resolver معتبر نیست") from exc
    if ":" in resolver_ip:
        raise HTTPException(status_code=422, detail="Resolver تست باید IPv4 باشد")
    if not setting.tunnel_domain or not setting.public_key:
        raise HTTPException(status_code=409, detail="NetMod DNS هنوز آماده ساخت پروفایل تست نیست")
    return {
        "ps": f"TwinPanel {node.name} · {resolver_ip}",
        "addr": resolver_ip,
        "ns": str(setting.tunnel_domain),
        "pubkey": str(setting.public_key),
        "user": SSH_USER,
        "pass": password,
    }


def _performance_status_script(*, public_ip: str) -> str:
    q_dropin = shlex.quote(PERFORMANCE_DROPIN_PATH)
    q_service = shlex.quote(DNSTT_SERVICE)
    q_public = shlex.quote(str(ipaddress.ip_address(public_ip)))
    return f"""set -u
mtu={DEFAULT_DNSTT_MTU}
if [ -s {q_dropin} ]; then
  parsed="$(grep -oE -- '-mtu [0-9]+' {q_dropin} 2>/dev/null | tail -n1 | awk '{{print $2}}' || true)"
  case "$parsed" in
    ''|*[!0-9]*) ;;
    *) mtu="$parsed" ;;
  esac
fi
service="$(systemctl is-active {q_service} 2>/dev/null || true)"
listener=no
ss -H -lunp 2>/dev/null | grep -F '{q_public}:{DNSTT_PORT} ' >/dev/null 2>&1 && listener=yes || true
effective="$(journalctl -u {q_service} -n 120 --no-pager 2>/dev/null | sed -n 's/.*effective MTU \([0-9][0-9]*\).*/\1/p' | tail -n1)"
formerr=no
journalctl -u {q_service} -n 120 --no-pager 2>/dev/null | grep -F 'FORMERR: requester payload size' >/dev/null 2>&1 && formerr=yes || true
printf 'MTU=%s\\n' "$mtu"
printf 'EFFECTIVE_MTU=%s\\n' "${{effective:-unknown}}"
printf 'SERVICE=%s\\n' "$service"
printf 'LISTENER=%s\\n' "$listener"
printf 'FORMERR_RECENT=%s\\n' "$formerr"
"""


def _mtu_apply_script(*, public_ip: str, domain: str, mtu: int) -> str:
    safe_ip = str(ipaddress.ip_address(public_ip))
    safe_mtu = _validated_mtu(mtu)
    if not domain or any(ch.isspace() for ch in domain):
        raise HTTPException(status_code=422, detail="Tunnel Domain معتبر نیست")
    q_dir = shlex.quote(PERFORMANCE_DROPIN_DIR)
    q_dropin = shlex.quote(PERFORMANCE_DROPIN_PATH)
    q_service = shlex.quote(DNSTT_SERVICE)
    exec_start = (
        f"{DNSTT_BINARY_PATH} -udp {safe_ip}:{DNSTT_PORT} "
        f"-privkey-file {PRIVATE_KEY_PATH} -mtu {safe_mtu} "
        f"{domain} 127.0.0.1:{SSH_PORT}"
    )
    return f"""set -u
DROPIN_DIR={q_dir}
DROPIN={q_dropin}
BACKUP="$(mktemp)"
HAD_OLD=no
if [ -f "$DROPIN" ]; then
  cp -a "$DROPIN" "$BACKUP"
  HAD_OLD=yes
fi
rollback() {{
  if [ "$HAD_OLD" = yes ]; then
    install -D -m 0644 "$BACKUP" "$DROPIN"
  else
    rm -f "$DROPIN"
    rmdir "$DROPIN_DIR" >/dev/null 2>&1 || true
  fi
  systemctl daemon-reload
  systemctl restart {q_service} >/dev/null 2>&1 || true
  rm -f "$BACKUP"
}}

if [ {safe_mtu} -eq {DEFAULT_DNSTT_MTU} ]; then
  rm -f "$DROPIN"
  rmdir "$DROPIN_DIR" >/dev/null 2>&1 || true
else
  install -d -m 0755 "$DROPIN_DIR"
  cat > "$DROPIN" <<'EOF'
[Service]
ExecStart=
ExecStart={exec_start}
EOF
  chmod 0644 "$DROPIN"
fi

systemctl daemon-reload
if ! systemctl restart {q_service}; then
  rollback
  echo 'MTU_APPLY_RESTART_FAILED' >&2
  exit 42
fi
sleep 1
if ! systemctl is-active --quiet {q_service}; then
  rollback
  echo 'MTU_APPLY_SERVICE_INACTIVE' >&2
  exit 43
fi
if ! ss -H -lunp 2>/dev/null | grep -F '{safe_ip}:{DNSTT_PORT} ' >/dev/null 2>&1; then
  rollback
  echo 'MTU_APPLY_LISTENER_MISSING' >&2
  exit 44
fi

effective="$(journalctl -u {q_service} -n 80 --no-pager 2>/dev/null | sed -n 's/.*effective MTU \([0-9][0-9]*\).*/\1/p' | tail -n1)"
formerr=no
journalctl -u {q_service} -n 80 --no-pager 2>/dev/null | grep -F 'FORMERR: requester payload size' >/dev/null 2>&1 && formerr=yes || true
rm -f "$BACKUP"
printf 'MTU={safe_mtu}\\n'
printf 'EFFECTIVE_MTU=%s\\n' "${{effective:-unknown}}"
printf 'SERVICE=active\\n'
printf 'LISTENER=yes\\n'
printf 'FORMERR_RECENT=%s\\n' "$formerr"
"""


async def _password_for_node(node: Any, db: Session) -> str:
    q_password = shlex.quote(PASSWORD_PATH)
    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(
                conn,
                f"set -Eeuo pipefail; test -s {q_password}; printf 'PASSWORD='; tr -d '\\r\\n' < {q_password}; printf '\\n'",
            )
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "دریافت credential تست NetMod ناموفق بود", "error": str(exc)[:1200]},
        ) from exc
    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(status_code=502, detail="Credential داخلی NetMod از Exit دریافت نشد")
    password = _parse_lines(result.stdout).get("PASSWORD", "")
    if not password or len(password) > 256 or any(ch.isspace() for ch in password):
        raise HTTPException(status_code=502, detail="Credential داخلی NetMod معتبر نیست")
    return password


@router.get("/netmod-dns/{node_id}/performance")
async def performance_status(node_id: int, db: Session = Depends(get_db)):
    node = _eligible_exit(db, node_id)
    row = _setting(db, node.id)
    if not row or row.runtime_status != "online" or not row.tunnel_domain:
        raise HTTPException(status_code=409, detail="NetMod DNS روی این Exit Online نیست")
    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, _performance_status_script(public_ip=str(node.public_ip)))
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "خواندن وضعیت Performance ناموفق بود", "error": str(exc)[:1200]},
        ) from exc
    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(status_code=502, detail="وضعیت DNSTT Performance خوانده نشد")
    runtime = _parse_lines(result.stdout)
    return {
        "ok": runtime.get("SERVICE") == "active" and runtime.get("LISTENER") == "yes",
        "engine": ENGINE,
        "node_id": int(node.id),
        "mtu": int(runtime.get("MTU") or DEFAULT_DNSTT_MTU),
        "effective_mtu": runtime.get("EFFECTIVE_MTU") or "unknown",
        "formerr_recent": runtime.get("FORMERR_RECENT") == "yes",
        "resolver_presets": [
            {"label": label, "resolver": resolver}
            for label, resolver in RESOLVER_PRESETS
        ],
        "measurement_scope": "client",
        "note": "Resolver quality must be measured from the NetMod client path; Exit-side ranking is intentionally not fabricated.",
    }


@router.get("/netmod-dns/{node_id}/performance/profiles")
async def performance_profiles(node_id: int, db: Session = Depends(get_db)):
    node = _eligible_exit(db, node_id)
    row = _setting(db, node.id)
    if not row or row.runtime_status != "online" or not row.tunnel_domain or not row.public_key:
        raise HTTPException(status_code=409, detail="NetMod DNS روی این Exit Online نیست")
    password = await _password_for_node(node, db)
    profiles = []
    for label, resolver in RESOLVER_PRESETS:
        payload = _profile_payload(node=node, setting=row, resolver=resolver, password=password)
        profiles.append(
            {
                "label": label,
                "resolver": resolver,
                "name": payload["ps"],
                "nm_dns": _netmod_encrypt_payload(payload),
            }
        )
    return {
        "ok": True,
        "engine": ENGINE,
        "node_id": int(node.id),
        "secret": True,
        "mode": "vpn",
        "profiles": profiles,
        "instructions": "Import one profile at a time in NetMod VPN mode and compare real ping/download/upload before choosing the resolver.",
    }


@router.post("/netmod-dns/{node_id}/performance/mtu")
async def apply_mtu(node_id: int, payload: NetModMtuIn, db: Session = Depends(get_db)):
    node = _eligible_exit(db, node_id)
    row = _setting(db, node.id)
    if not row or row.runtime_status != "online" or not row.tunnel_domain:
        raise HTTPException(status_code=409, detail="NetMod DNS روی این Exit Online نیست")
    mtu = _validated_mtu(payload.mtu)
    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(
                conn,
                _mtu_apply_script(
                    public_ip=str(node.public_ip),
                    domain=str(row.tunnel_domain),
                    mtu=mtu,
                ),
            )
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "اعمال MTU ناموفق بود؛ تنظیم قبلی حفظ شد", "error": str(exc)[:1400]},
        ) from exc
    if int(getattr(result, "exit_status", 1) or 0) != 0:
        message = str(result.stderr or result.stdout or "DNSTT MTU apply failed")[-1400:]
        raise HTTPException(
            status_code=502,
            detail={"message": "اعمال MTU ناموفق بود و rollback اجرا شد", "error": message},
        )
    runtime = _parse_lines(result.stdout)
    return {
        "ok": runtime.get("SERVICE") == "active" and runtime.get("LISTENER") == "yes",
        "engine": ENGINE,
        "node_id": int(node.id),
        "mtu": int(runtime.get("MTU") or mtu),
        "effective_mtu": runtime.get("EFFECTIVE_MTU") or "unknown",
        "formerr_recent": runtime.get("FORMERR_RECENT") == "yes",
        "rollback_safe": True,
    }
