"""Authenticated, tenant-isolated appearance management for shared VPN app."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..central_app_appearance import (
    AppearanceIn, reset_appearance, resolve_appearance, save_appearance,
)
from ..database import get_db
from ..deps import require_admin, require_reseller
from ..models_reseller import Reseller

router = APIRouter(prefix="/v1/central-app", tags=["central-app-appearance"])


def _reseller(db: Session, reseller_id: int) -> Reseller:
    record = db.get(Reseller, int(reseller_id))
    if record is None:
        raise HTTPException(status_code=404, detail="RESELLER_NOT_FOUND")
    return record


@router.get("/admin/appearance")
def admin_appearance(
    _=Depends(require_admin), db: Session = Depends(get_db),
):
    return resolve_appearance(db, 0)


@router.put("/admin/appearance")
def admin_appearance_save(
    payload: AppearanceIn, _=Depends(require_admin), db: Session = Depends(get_db),
):
    return save_appearance(db, 0, payload)


@router.delete("/admin/appearance")
def admin_appearance_reset(
    _=Depends(require_admin), db: Session = Depends(get_db),
):
    return reset_appearance(db, 0)


@router.get("/admin/appearance-resellers")
def admin_appearance_resellers(
    _=Depends(require_admin), db: Session = Depends(get_db),
):
    rows = db.query(Reseller).order_by(Reseller.id.asc()).all()
    return [
        {"id": int(row.id), "name": row.brand_name or row.name or f"#{row.id}"}
        for row in rows
    ]


@router.get("/admin/resellers/{reseller_id}/appearance")
def admin_reseller_appearance(
    reseller_id: int, _=Depends(require_admin), db: Session = Depends(get_db),
):
    _reseller(db, reseller_id)
    return resolve_appearance(db, reseller_id)


@router.put("/admin/resellers/{reseller_id}/appearance")
def admin_reseller_appearance_save(
    reseller_id: int, payload: AppearanceIn,
    _=Depends(require_admin), db: Session = Depends(get_db),
):
    _reseller(db, reseller_id)
    return save_appearance(db, reseller_id, payload)


@router.delete("/admin/resellers/{reseller_id}/appearance")
def admin_reseller_appearance_reset(
    reseller_id: int, _=Depends(require_admin), db: Session = Depends(get_db),
):
    _reseller(db, reseller_id)
    return reset_appearance(db, reseller_id)


@router.get("/reseller/appearance")
def reseller_appearance(
    reseller: Reseller = Depends(require_reseller), db: Session = Depends(get_db),
):
    return resolve_appearance(db, int(reseller.id))


@router.put("/reseller/appearance")
def reseller_appearance_save(
    payload: AppearanceIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    return save_appearance(db, int(reseller.id), payload)


@router.delete("/reseller/appearance")
def reseller_appearance_reset(
    reseller: Reseller = Depends(require_reseller), db: Session = Depends(get_db),
):
    return reset_appearance(db, int(reseller.id))
