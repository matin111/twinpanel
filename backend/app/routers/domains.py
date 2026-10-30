from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..services.ssl_manager import create_nginx_config
from ..services.domain_ssl_runtime_v1 import issue_ssl
from ..services.domain_router import resolve_domain_route
import subprocess
import os
import re
from ..database import get_db
from ..domain_models import Domain, DomainType, SSLStatus
from ..models import User, UserRole
from .auth import get_current_user


router = APIRouter(
    prefix="/v1/admin/domains",
    tags=["domains"]
)


def admin_only(user: User):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="admin_only"
        )


# TWINPANEL_DOMAIN_MANAGER_V4
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)


def _normalize_domain(value) -> str:
    domain = str(value or "").strip().lower().rstrip(".")

    if (
        not domain
        or "://" in domain
        or "/" in domain
        or ":" in domain
        or any(ch.isspace() for ch in domain)
        or not _DOMAIN_RE.fullmatch(domain)
    ):
        raise HTTPException(
            status_code=400,
            detail="invalid_domain"
        )

    return domain


def _normalize_domain_type(value) -> DomainType:
    if isinstance(value, DomainType):
        return value

    try:
        return DomainType(
            str(value or DomainType.SHOP.value)
            .strip()
            .lower()
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="invalid_domain_type"
        )


def _remove_nginx_domain(domain: str):
    filename = f"{domain}.conf"

    available = os.path.join(
        "/etc/nginx/sites-available",
        filename
    )

    enabled = os.path.join(
        "/etc/nginx/sites-enabled",
        filename
    )

    if os.path.lexists(enabled):
        os.unlink(enabled)

    if os.path.exists(available):
        os.unlink(available)

    test = subprocess.run(
        ["nginx", "-t"],
        capture_output=True,
        text=True
    )

    if test.returncode != 0:
        raise RuntimeError(test.stderr)

    subprocess.run(
        ["systemctl", "reload", "nginx"],
        check=False
    )


@router.get("")
def list_domains(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    admin_only(user)

    return (
        db.query(Domain)
        .order_by(Domain.id.asc())
        .all()
    )


@router.post("")
def create_domain(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Register the domain and activate its plain-HTTP Nginx route only.

    SSL issuance is intentionally a separate action. Package installation,
    ACME validation and certificate deployment must not keep this API request
    open long enough for the reverse proxy to return 504.
    """
    admin_only(user)

    domain = _normalize_domain(
        payload.get("domain")
    )

    exists = (
        db.query(Domain)
        .filter(Domain.domain == domain)
        .first()
    )

    if exists:
        raise HTTPException(
            status_code=400,
            detail="domain_exists"
        )

    domain_type = _normalize_domain_type(
        payload.get(
            "domain_type",
            DomainType.SHOP.value
        )
    )

    route = resolve_domain_route(
        domain_type
    )

    item = Domain(
        domain=domain,
        domain_type=domain_type,
        target_host=route["host"],
        target_port=route["port"]
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    try:
        create_nginx_config(
            item.domain,
            item.target_host or "127.0.0.1",
            item.target_port,
            item.domain_type
        )

        item.nginx_status = "active"
        item.nginx_file = (
            f"/etc/nginx/sites-available/"
            f"{item.domain}.conf"
        )
        item.ssl_status = SSLStatus.NONE
        item.ssl_error = None

    except Exception as exc:
        item.nginx_status = "failed"
        item.ssl_error = str(exc)

    db.commit()
    db.refresh(item)

    return item


@router.put("/{domain_id}")
def update_domain(
    domain_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    admin_only(user)

    item = (
        db.query(Domain)
        .filter(Domain.id == domain_id)
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="domain_not_found"
        )

    old_domain = item.domain

    if "domain" in payload:
        new_domain = _normalize_domain(
            payload["domain"]
        )

        duplicate = (
            db.query(Domain)
            .filter(
                Domain.domain == new_domain,
                Domain.id != domain_id
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="domain_exists"
            )

        item.domain = new_domain

    if "domain_type" in payload:
        item.domain_type = (
            _normalize_domain_type(
                payload["domain_type"]
            )
        )

    route = resolve_domain_route(
        item.domain_type
    )

    item.target_host = route["host"]
    item.target_port = route["port"]

    try:
        create_nginx_config(
            item.domain,
            item.target_host,
            item.target_port,
            item.domain_type
        )

        if old_domain != item.domain:
            _remove_nginx_domain(
                old_domain
            )

            # SSL دامنه قبلی برای دامنه جدید معتبر نیست.
            item.ssl_status = SSLStatus.NONE
            item.ssl_expires_at = None
            item.ssl_error = None

        item.nginx_status = "active"
        item.nginx_file = (
            f"/etc/nginx/sites-available/"
            f"{item.domain}.conf"
        )

    except Exception as exc:
        item.nginx_status = "failed"
        item.ssl_error = str(exc)

        db.commit()
        db.refresh(item)

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )

    db.commit()
    db.refresh(item)

    return item


@router.delete("/{domain_id}")
def delete_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    admin_only(user)

    item = (
        db.query(Domain)
        .filter(Domain.id == domain_id)
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="domain_not_found"
        )

    domain = item.domain

    try:
        _remove_nginx_domain(
            domain
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"nginx_cleanup_failed: {exc}"
        )

    db.delete(item)
    db.commit()

    return {
        "ok": True,
        "domain": domain
    }


@router.post("/{domain_id}/ssl")
def request_ssl(
    domain_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    admin_only(user)

    item = (
        db.query(Domain)
        .filter(Domain.id == domain_id)
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="domain_not_found"
        )

    try:
        host = item.target_host or "127.0.0.1"
        nginx_path = f"/etc/nginx/sites-available/{item.domain}.conf"

        # Existing and newly-created rows normally already have their HTTP
        # config. Recreate it only when the file is missing so a 443 conflict
        # cannot make a harmless retry reload an existing SSL server block.
        if not os.path.exists(nginx_path):
            create_nginx_config(
                item.domain,
                host,
                item.target_port,
                item.domain_type
            )

        item.nginx_status = "active"
        item.nginx_file = nginx_path

        result = issue_ssl(
            item.domain,
            timeout_seconds=180,
        )

        if result["ok"]:
            item.ssl_status = SSLStatus.ACTIVE
            item.ssl_error = None

            create_nginx_config(
                item.domain,
                host,
                item.target_port,
                item.domain_type
            )

            db.commit()
            db.refresh(item)

            return {
                "ok": True,
                "domain": item.domain,
                "ssl_status": item.ssl_status,
                "nginx_status": item.nginx_status,
                "detail": result,
            }

        item.ssl_status = SSLStatus.FAILED
        item.ssl_error = result.get("error", "")
        db.commit()
        db.refresh(item)

        code = str(result.get("code") or "ssl_failed")
        status_code = 409 if code in {
            "https_port_conflict",
            "certbot_not_installed",
        } else 502

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": code,
                "message": result.get("error") or code,
                "owners": result.get("owners") or [],
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        item.ssl_status = SSLStatus.FAILED
        item.ssl_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )
