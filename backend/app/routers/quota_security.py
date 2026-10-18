import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Node
from ..quota_models import QuotaUsageEvent
from ..quota_schemas import CommandAckIn, SessionCloseIn, SessionOpenIn, UsageEventIn
from ..quota_security import public_key_b64, require_node_identity
from ..quota_service import acknowledge_command, close_session, pull_commands
from ..services.public_urls import api_base_url
from ..services.quota_node_sync import sync_node_config
from ..services.reseller_traffic_pool import apply_usage_event, open_session
from .subscription_admin_v2 import router as subscription_admin_v2_router


router = APIRouter(prefix="/v1", tags=["quota-security"])
router.include_router(subscription_admin_v2_router)


def authenticate_node(
    node_id: int,
    db: Session,
    proxy_auth: str | None,
    client_certificate: str | None,
    node_secret: str | None = None,
) -> None:
    """Authenticate either enrolled mTLS quota agents or the installed node agent.

    TwinPanel's production node agent already authenticates heartbeats and
    tunnel desired-state calls with X-Node-Secret.  Quota V1 originally only
    accepted the separate mTLS proxy identity, while the shipped node agent had
    no quota mTLS material.  That made real session/usage telemetry impossible
    on ordinary installations.

    mTLS remains supported and preferred.  The shared-secret compatibility path
    is intentionally limited to an existing, non-retired node and uses the same
    secret already required by the node control-plane.
    """

    expected = str(settings.node_agent_shared_secret or "")
    supplied = str(node_secret or "")

    if (
        expected
        and supplied
        and hmac.compare_digest(supplied, expected)
    ):
        node = (
            db.query(Node)
            .filter(
                Node.id == int(node_id),
                Node.retired_at.is_(None),
            )
            .first()
        )
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return

    require_node_identity(db, node_id, proxy_auth, client_certificate)


def _auth_headers(
    proxy_auth: str | None,
    client_certificate: str | None,
    node_secret: str | None,
):
    return proxy_auth, client_certificate, node_secret


@router.get("/quota/health")
def quota_health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    event_count = int(db.scalar(select(func.count(QuotaUsageEvent.id))) or 0)
    return {
        "ok": True,
        "service": "TwinPanel Quota Core",
        "version": "1.1.0",
        "ledger": "postgresql-append-only",
        "usage_events": event_count,
        "enforcement": "node-agent-telemetry",
        "reseller_pool": "usage-based",
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
    node_secret: str | None = Header(default=None, alias="X-Node-Secret"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate, node_secret)
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
    node_secret: str | None = Header(default=None, alias="X-Node-Secret"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate, node_secret)
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
    node_secret: str | None = Header(default=None, alias="X-Node-Secret"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate, node_secret)
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
    node_secret: str | None = Header(default=None, alias="X-Node-Secret"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate, node_secret)
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
    node_secret: str | None = Header(default=None, alias="X-Node-Secret"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate, node_secret)
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
    proxy_auth: str | None = Header(default=None, alias="X-TwinPanel-Proxy-Auth"),
    client_certificate: str | None = Header(default=None, alias="X-TwinPanel-Client-Cert"),
    node_secret: str | None = Header(default=None, alias="X-Node-Secret"),
):
    authenticate_node(node_id, db, proxy_auth, client_certificate, node_secret)
    result = sync_node_config(
        db,
        node_id,
        api_base=api_base_url(db, request),
    )
    # build_node_devices may lazily backfill QuotaDevice rows for upgrades.
    db.commit()
    return result
