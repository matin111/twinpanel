from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
import re
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node
from ..local_core_runtime import ensure_local_core_node
from ..mother_access import (
    admin_can_use_mother,
    get_bool,
    reseller_can_use_mother,
    set_bool,
)


router = APIRouter(
    prefix="/v1/mother-access",
    tags=["mother-access"],
)


class MotherGlobalSettingsIn(BaseModel):
    admin_enabled: bool
    reseller_enabled: bool
    mother_name: str | None = None
    public_domain: str | None = None


class MotherResellerAccessIn(BaseModel):
    enabled: bool


def _mother_node(db: Session) -> Node:
    node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.agent_url == "local://core",
        )
        .order_by(Node.id.asc())
        .first()
    )
    return node or ensure_local_core_node(db)


def _normalize_public_domain(value: str) -> str:
    domain = str(value or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/", 1)[0].strip()
    if domain.count(":") == 1:
        domain = domain.rsplit(":", 1)[0].strip()
    if not domain:
        return ""
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain):
        raise HTTPException(status_code=422, detail="دامنه عمومی سرور مادر معتبر نیست")
    return domain


@router.get(
    "/admin",
    dependencies=[Depends(require_admin)],
)
def get_mother_access_settings(
    db: Session = Depends(get_db),
):

    rows = db.execute(
        text(
            """
            SELECT setting_key, setting_value
            FROM vpnshop_runtime_settings
            WHERE setting_key LIKE 'mother.reseller.%'
            """
        )
    ).all()

    overrides: dict[str, bool] = {}

    for key, value in rows:

        reseller_id = str(key).split(".")[-1]

        overrides[reseller_id] = (
            str(value).strip().lower()
            in {"1", "true", "yes", "on"}
        )

    mother = _mother_node(db)

    return {
        "admin_enabled":
            admin_can_use_mother(db),

        "reseller_enabled":
            get_bool(
                db,
                "mother.reseller_enabled",
                False,
            ),

        "reseller_overrides":
            overrides,
        "mother_node_id": int(mother.id),
        "mother_name": str(mother.name or "سرور مادر"),
        "mother_public_domain": str(mother.public_domain or ""),
        "mother_public_ip": str(mother.public_ip or ""),
    }


@router.put(
    "/admin",
    dependencies=[Depends(require_admin)],
)
def update_mother_access_settings(
    payload: MotherGlobalSettingsIn,
    db: Session = Depends(get_db),
):

    set_bool(
        db,
        "mother.admin_enabled",
        payload.admin_enabled,
    )

    set_bool(
        db,
        "mother.reseller_enabled",
        payload.reseller_enabled,
    )

    mother = _mother_node(db)

    if payload.mother_name is not None:
        name = str(payload.mother_name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="نام سرور مادر نمی‌تواند خالی باشد")
        if len(name) > 120:
            raise HTTPException(status_code=422, detail="نام سرور مادر حداکثر ۱۲۰ کاراکتر است")
        duplicate = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                Node.id != mother.id,
                Node.name == name,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="این نام قبلاً برای یک نود دیگر استفاده شده است")
        mother.name = name

    if payload.public_domain is not None:
        mother.public_domain = _normalize_public_domain(payload.public_domain) or None

    # Mother is always an internal provisioning target. These toggles control
    # only High Availability / Multi-Link inclusion; disabling HA must never
    # delete SubscriptionNode membership or stored Mother credentials.
    db.commit()

    return {
        "ok": True,
        "admin_enabled":
            payload.admin_enabled,
        "reseller_enabled":
            payload.reseller_enabled,
        "mother_node_id": int(mother.id),
        "mother_name": str(mother.name or ""),
        "mother_public_domain": str(mother.public_domain or ""),
        "mother_public_ip": str(mother.public_ip or ""),
        # Kept for API compatibility with V109. V110 intentionally performs no
        # destructive membership cleanup.
        "removed_mother_memberships": 0,
        "provisioning_preserved": True,
    }


@router.put(
    "/admin/resellers/{reseller_id}",
    dependencies=[Depends(require_admin)],
)
def update_reseller_mother_access(
    reseller_id: int,
    payload: MotherResellerAccessIn,
    db: Session = Depends(get_db),
):

    exists = db.execute(
        text(
            """
            SELECT id
            FROM resellers
            WHERE id = :id
            """
        ),
        {"id": reseller_id},
    ).first()

    if not exists:
        raise HTTPException(
            status_code=404,
            detail="نماینده پیدا نشد",
        )

    set_bool(
        db,
        f"mother.reseller.{reseller_id}",
        payload.enabled,
    )

    db.commit()

    return {
        "ok": True,
        "reseller_id": reseller_id,
        "enabled": payload.enabled,
        "effective":
            reseller_can_use_mother(
                db,
                reseller_id,
            ),
    }
