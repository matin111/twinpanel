"""Synchronize SSH-verified Cisco certificate pins for current/future nodes.

Fail closed: no SSH trust => no new trust pin. No user credentials are touched.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/twinpanel/current/backend")

from app.database import SessionLocal
from app.models import Node, NodeType, NodeProtocolConfig
from app.runtime_settings_model import RuntimeSetting
from app.routers.provision import ssh_connect_saved, cmd

log = logging.getLogger("cisco-cert-pin-sync")
PIN = re.compile(r"pin-sha256:[A-Za-z0-9+/]{43}=")
REMOTE = r"""python3 - <<'NODEPY'
from pathlib import Path
import base64, hashlib, re, subprocess
config = Path('/etc/ocserv/ocserv.conf')
if config.is_file():
    for line in config.read_text(errors='replace').splitlines():
        match = re.match(r'^\s*server-cert\s*=\s*(\S+)', line)
        if not match:
            continue
        cert = Path(match.group(1))
        if cert.is_file():
            pub = subprocess.run(
                ['openssl', 'x509', '-in', str(cert), '-pubkey', '-noout'],
                capture_output=True, check=False, timeout=5)
            if pub.returncode == 0:
                spki = subprocess.run(
                    ['openssl', 'pkey', '-pubin', '-outform', 'DER'],
                    input=pub.stdout, capture_output=True, check=False, timeout=5)
                if spki.returncode == 0 and spki.stdout:
                    print('pin-sha256:' + base64.b64encode(
                        hashlib.sha256(spki.stdout).digest()).decode('ascii'))
        break
NODEPY"""

async def read_pin(node, db):
    conn = await asyncio.wait_for(ssh_connect_saved(node, db), timeout=12)
    try:
        output = await cmd(conn, REMOTE, timeout=15, check=False)
    finally:
        conn.close()
        await conn.wait_closed()
    candidates = [line.strip() for line in output.splitlines()
                  if PIN.fullmatch(line.strip())]
    return candidates[0] if len(candidates) == 1 else None

async def main():
    ok, skipped = 0, 0
    with SessionLocal() as db:
        nodes = (db.query(Node).filter(
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
            Node.enable_cisco.is_(True)).order_by(Node.id).limit(200).all())
        for node in nodes:
            cfg = db.query(NodeProtocolConfig).filter_by(
                node_id=node.id, protocol='cisco').first()
            if cfg is None or str(cfg.status).lower() != 'online':
                skipped += 1
                continue
            try:
                pin = await read_pin(node, db)
                if not pin:
                    skipped += 1
                    log.warning("node=%d missing verified certificate", node.id)
                    continue
                key = f"cisco.trusted_servercert.node.{int(node.id)}"
                row = db.get(RuntimeSetting, key)
                if row is None:
                    db.add(RuntimeSetting(setting_key=key, setting_value=pin))
                    db.commit()
                    log.info("node=%d registered", node.id)
                elif row.setting_value != pin:
                    # Prevent unexpected identity swaps; operator must review
                    # cert rotations or changed nodes before customers trust it.
                    skipped += 1
                    log.error("node=%d certificate identity CHANGED; not overwritten", node.id)
                    continue
                ok += 1
            except Exception as exc:
                db.rollback()
                skipped += 1
                log.warning("node=%d sync failed: %s", node.id, type(exc).__name__)
    log.info("sync finished: validated=%d skipped=%d", ok, skipped)

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
