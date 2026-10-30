from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_admin
from ..services.migration_center_v1 import SUPPORTED_SOURCES, dry_run_migration


MigrationSource = Literal["sanaei", "marzban", "pasargad"]


router = APIRouter(
    prefix="/v1/admin/migration-center",
    tags=["migration-center-v1"],
    dependencies=[Depends(require_admin)],
)


class MigrationDryRunIn(BaseModel):
    source: MigrationSource
    records: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)


@router.get("/sources")
def migration_sources():
    return {
        "dry_run_only": True,
        "writes_performed": False,
        "sources": list(SUPPORTED_SOURCES),
        "preservation_contract": {
            "credentials": "preserve_existing",
            "legacy_subscription_url": "preserve_existing",
        },
    }


@router.post("/dry-run")
def migration_dry_run(payload: MigrationDryRunIn):
    try:
        return dry_run_migration(payload.source, payload.records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
