

from ..services.public_urls import api_base_url
from fastapi import Request
from datetime import datetime, timedelta, timezone
from textwrap import dedent

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..models import Node

router = APIRouter(tags=["bootstrap"])

ALGORITHM = "HS256"
INSTALL_TTL_MINUTES = 15


def make_install_token(node_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"node-install:{node_id}",
        "node_id": node_id,
        "purpose": "node_install",
        "iat": now,
        "exp": now + timedelta(minutes=INSTALL_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


def parse_install_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Install token invalid or expired") from exc

    if payload.get("purpose") != "node_install":
        raise HTTPException(status_code=401, detail="Invalid install token")

    node_id = payload.get("node_id")
    if not isinstance(node_id, int):
        raise HTTPException(status_code=401, detail="Invalid node id")

    return node_id


@router.post(
    "/v1/admin/nodes/{node_id}/install-command",
    dependencies=[Depends(require_admin)],
)
def install_command(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="نود پیدا نشد")

    token = make_install_token(node_id)
    base = api_base_url(
        db,
        request,
    )

    if not base:
        raise HTTPException(
            status_code=503,
            detail="public_api_base_unavailable",
        )

    command = (
        f"curl -fsSL "
        f"'{base}/v1/install/{token}' | bash"
    )

    return {
        "ok": True,
        "node_id": node.id,
        "node_name": node.name,
        "expires_in_minutes": INSTALL_TTL_MINUTES,
        "command": command,
    }


@router.get("/install/{token}", response_class=PlainTextResponse)
@router.get("/v1/install/{token}", response_class=PlainTextResponse)
def install_agent(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    node_id = parse_install_token(token)
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    central_api = api_base_url(
        db,
        request,
    )

    if not central_api:
        raise HTTPException(
            status_code=503,
            detail="public_api_base_unavailable",
        )
    secret = settings.node_agent_shared_secret

    script = f"""#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/twinpanel-agent"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root."
  exit 1
fi

echo "[1/5] Installing dependencies..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip iputils-ping wireguard-tools curl

echo "[2/5] Creating TwinPanel Agent..."
mkdir -p "$INSTALL_DIR"

cat >"$INSTALL_DIR/agent.py" <<'PYEOF'
import asyncio
import re
import socket
import subprocess

import httpx
import psutil

CENTRAL_API = {central_api!r}
NODE_ID = {node.id}
NODE_SECRET = {secret!r}


def run(args, timeout=5):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except Exception:
        return 255, ""


def active(service):
    code, _ = run(["systemctl", "is-active", "--quiet", service], 4)
    return code == 0


def has_running_service(text):
    code, out = run(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend"], 5)
    return code == 0 and text.lower() in out.lower()


def wg_active():
    code, out = run(["wg", "show", "interfaces"], 4)
    return code == 0 and bool(out.strip())


def protocols():
    return {{
        "cisco": active("ocserv"),
        "openvpn": has_running_service("openvpn"),
        "wireguard": wg_active(),
        "l2tp": active("xl2tpd") or active("strongswan"),
        "v2ray": active("xray") or active("v2ray"),
    }}


def count_users():
    count = 0

    code, out = run(["occtl", "-j", "show", "users"], 5)
    if code == 0:
        count += len(re.findall(r'"username"\\s*:', out))

    code, out = run(["wg", "show", "all", "dump"], 5)
    if code == 0:
        for line in out.splitlines():
            if len(line.split("\\t")) >= 8:
                count += 1

    return count


def payload():
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {{
        "current_users": count_users(),
        "cpu_percent": round(psutil.cpu_percent(interval=0.2), 2),
        "memory_percent": round(vm.percent, 2),
        "disk_percent": round(disk.percent, 2),
        "hostname": socket.gethostname(),
        "protocols": protocols(),
    }}


async def main():
    async with httpx.AsyncClient(timeout=15.0, verify=True) as client:
        while True:
            try:
                r = await client.post(
                    f"{{CENTRAL_API}}/v1/nodes/{{NODE_ID}}/heartbeat",
                    headers={{"X-Node-Secret": NODE_SECRET}},
                    json=payload(),
                )
                r.raise_for_status()
                print("[TwinPanel] heartbeat OK", flush=True)
            except Exception as exc:
                print(f"[TwinPanel] heartbeat ERROR: {{exc}}", flush=True)

            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
PYEOF

cat >"$INSTALL_DIR/requirements.txt" <<'REQEOF'
httpx==0.28.1
psutil==7.0.0
REQEOF

echo "[3/5] Installing Python packages..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "[4/5] Creating systemd service..."
cat >/etc/systemd/system/twinpanel-agent.service <<'SVCEOF'
[Unit]
Description=TwinPanel VPN Node Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/twinpanel-agent
ExecStart=/opt/twinpanel-agent/venv/bin/python /opt/twinpanel-agent/agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now twinpanel-agent

echo "[5/5] Done."
echo
echo "TwinPanel Agent installed successfully."
echo "Node: {node.name}"
echo "Node ID: {node.id}"
echo
systemctl --no-pager --full status twinpanel-agent | head -n 15 || true
"""

    return PlainTextResponse(dedent(script).lstrip(), media_type="text/x-shellscript")
