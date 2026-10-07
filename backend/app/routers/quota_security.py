

from ..services.public_urls import api_base_url
from fastapi import Request
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..quota_models import QuotaUsageEvent
from ..quota_schemas import CommandAckIn, SessionCloseIn, SessionOpenIn, UsageEventIn
from ..quota_security import public_key_b64, require_node_identity
from ..services.quota_node_sync import sync_node_config
from ..quota_service import (
    acknowledge_command,
    apply_usage_event,
    close_session,
    open_session,
    pull_commands,
)


router = APIRouter(prefix="/v1", tags=["quota-security"])


def authenticate_node(
    node_id: int,
    db: Session,
    proxy_auth: str | None,
    client_certificate: str | None,
) -> None:
    require_node_identity(db, node_id, proxy_auth, client_certificate)


@router.get("/quota/health")
def quota_health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    event_count = int(db.scalar(select(func.count(QuotaUsageEvent.id))) or 0)
    return {
        "ok": True,
        "service": "TwinPanel Quota Core",
        "version": "1.0.0",
        "ledger": "postgresql-append-only",
        "usage_events": event_count,
        "enforcement": "ready-for-node-enrollment",
    }


@router.get("/node-agent/signing-key")
def signing_key():
    return {"algorithm": "Ed25519", "public_key_b64": public_key_b64()}


@router.post("/nodes/{node_id}/quota/usage-events", status_code=202)
def usage_event(
    node_id: int,
    data: UsageEventIn,
    db: Session = Depends(get_db),
    proxy_auth: str | None = Header(default=None, alias="X-TwinPanel-Proxy-Auth"),
    client_certificate: str | None = Header(default=None, alias="X-TwinPanel-Client-Cert"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate)
    try:
        result = apply_usage_event(db, node_id, data)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/nodes/{node_id}/quota/sessions/open", status_code=202)
def session_open(
    node_id: int,
    data: SessionOpenIn,
    db: Session = Depends(get_db),
    proxy_auth: str | None = Header(default=None, alias="X-TwinPanel-Proxy-Auth"),
    client_certificate: str | None = Header(default=None, alias="X-TwinPanel-Client-Cert"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate)
    try:
        result = open_session(db, node_id, data)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/nodes/{node_id}/quota/sessions/close", status_code=202)
def session_close(
    node_id: int,
    data: SessionCloseIn,
    db: Session = Depends(get_db),
    proxy_auth: str | None = Header(default=None, alias="X-TwinPanel-Proxy-Auth"),
    client_certificate: str | None = Header(default=None, alias="X-TwinPanel-Client-Cert"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate)
    try:
        result = close_session(db, node_id, data)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get("/nodes/{node_id}/quota/commands")
def commands(
    node_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    proxy_auth: str | None = Header(default=None, alias="X-TwinPanel-Proxy-Auth"),
    client_certificate: str | None = Header(default=None, alias="X-TwinPanel-Client-Cert"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate)
    try:
        result = pull_commands(db, node_id, limit)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/nodes/{node_id}/quota/commands/{command_id}/ack")
def command_ack(
    node_id: int,
    command_id: str,
    data: CommandAckIn,
    db: Session = Depends(get_db),
    proxy_auth: str | None = Header(default=None, alias="X-TwinPanel-Proxy-Auth"),
    client_certificate: str | None = Header(default=None, alias="X-TwinPanel-Client-Cert"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate)
    try:
        result = acknowledge_command(db, node_id, command_id, data)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get("/nodes/{node_id}/quota/config")
def get_quota_config(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return sync_node_config(
        db,
        node_id,
        api_base=api_base_url(
            db,
            request,
        ),
    )
