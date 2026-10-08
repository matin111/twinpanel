import base64
import shlex

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeType
from ..mother_access import (
    generate_l2tp_psk,
    get_l2tp_psk,
    get_or_create_l2tp_psk,
    set_l2tp_psk,
)
from .provision import cmd, ssh_connect_saved


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["vpn-settings"],
    dependencies=[Depends(require_admin)],
)


class L2tpPskUpdateIn(BaseModel):
    # TWINPANEL_FREE_L2TP_PSK_V1
    # Admin may choose letters, numbers and symbols.
    psk: str = Field(
        min_length=1,
        max_length=64,
    )

def _secret_file(psk: str) -> str:
    # TWINPANEL_L2TP_HEX_PSK_V1
    # strongSwan supports PSK as hexadecimal binary data.
    # This safely supports quotes, backslashes and other symbols
    # without breaking /etc/ipsec.secrets parsing.
    raw = str(psk).encode("utf-8")
    return f"%any %any : PSK 0x{raw.hex()}\n"


async def _apply_psk(
    db: Session,
    node: Node,
    psk: str,
) -> None:
    conn = None

    try:
        conn = await ssh_connect_saved(node, db)

        data = base64.b64encode(
            _secret_file(psk).encode()
        ).decode()

        await cmd(
            conn,
            (
                "tmp=$(mktemp); "
                f"printf '%s' {shlex.quote(data)} | "
                "base64 -d > \"$tmp\" && "
                "chmod 600 \"$tmp\" && "
                "cp -a /etc/ipsec.secrets "
                "/etc/ipsec.secrets.bak-twinpanel 2>/dev/null || true; "
                "cat \"$tmp\" > /etc/ipsec.secrets && "
                "rm -f \"$tmp\" && "
                "chmod 600 /etc/ipsec.secrets && "
                "(ipsec rereadsecrets || "
                "systemctl restart strongswan-starter || "
                "systemctl restart strongswan)"
            ),
            timeout=60,
        )

    finally:
        if conn:
            conn.close()
            await conn.wait_closed()


def _l2tp_exits(db: Session) -> list[Node]:
    return (
        db.query(Node).filter(Node.retired_at.is_(None))
        .filter(
            Node.node_type == NodeType.EXIT,
            Node.enable_l2tp.is_(True),
        )
        .order_by(Node.id.asc())
        .all()
    )


@router.get("/l2tp")
def get_l2tp_settings(
    db: Session = Depends(get_db),
):
    psk = get_or_create_l2tp_psk(db)
    nodes = _l2tp_exits(db)

    return {
        "psk": psk,
        "length": len(psk),
        "exit_count": len(nodes),
        "exit_nodes": [
            {
                "id": node.id,
                "name": node.name,
            }
            for node in nodes
        ],
    }


@router.post("/l2tp/generate")
def generate_l2tp_secret():
    psk = generate_l2tp_psk()

    return {
        "psk": psk,
        "length": len(psk),
    }


@router.put("/l2tp")
async def update_l2tp_settings(
    payload: L2tpPskUpdateIn,
    db: Session = Depends(get_db),
):
    new_psk = payload.psk.strip()

    if not new_psk:
        raise HTTPException(
            status_code=422,
            detail="IPsec Secret نمی‌تواند خالی باشد",
        )

    if "\n" in new_psk or "\r" in new_psk:
        raise HTTPException(
            status_code=422,
            detail="IPsec Secret نباید شامل خط جدید باشد",
        )
    old_psk = get_l2tp_psk(db)

    if not old_psk:
        old_psk = get_or_create_l2tp_psk(db)

    if new_psk == old_psk:
        return {
            "ok": True,
            "changed": False,
            "synced_nodes": [],
        }

    nodes = _l2tp_exits(db)

    succeeded: list[Node] = []
    failed: list[dict] = []

    for node in nodes:
        try:
            await _apply_psk(
                db,
                node,
                new_psk,
            )
            succeeded.append(node)

        except Exception as exc:
            failed.append({
                "id": node.id,
                "name": node.name,
                "error": str(exc),
            })

    if failed:
        rollback_failed: list[dict] = []

        for node in succeeded:
            try:
                await _apply_psk(
                    db,
                    node,
                    old_psk,
                )
            except Exception as exc:
                rollback_failed.append({
                    "id": node.id,
                    "name": node.name,
                    "error": str(exc),
                })

        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "اعمال Secret روی همه سرورها موفق نبود؛ تغییر لغو شد.",
                "failed_nodes": failed,
                "rollback_failed": rollback_failed,
            },
        )

    set_l2tp_psk(
        db,
        new_psk,
    )
    db.commit()

    return {
        "ok": True,
        "changed": True,
        "length": len(new_psk),
        "synced_nodes": [
            {
                "id": node.id,
                "name": node.name,
            }
            for node in succeeded
        ],
    }
