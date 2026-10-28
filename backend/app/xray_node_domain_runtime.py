from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, String, inspect, text
from sqlalchemy.orm import Session

from . import xray_modern_admin, xray_modern_repair_runtime, xray_modern_runtime
from .database import engine, get_db
from .models import Node
from .routers import account_delivery


# TWINPANEL_XRAY_NODE_DOMAIN_RUNTIME_V3
#
# Xray TLS identity is independent from the Node's general/public domain.
# Existing installations remain compatible: when xray_domain is empty, Modern
# Xray still falls back to public_domain until an explicit Xray domain is saved.
#
# V2 closed the historical-subscription gap: preparing a dedicated TLS domain
# starts the existing V36/V41 reconcile pipeline in the background.
#
# V3 closes the direct-delivery authority gap. The dedicated Xray domain was
# already used for certificate/SNI preparation, but direct customer TLS links
# could still publish Node.public_domain or the Exit IP as their VLESS authority.
# Only direct TLS Xray authorities are converged to xray_domain. Iran-tunnel
# authorities and non-TLS/REALITY profiles intentionally remain unchanged.

_runtime_applied = False
_original_node_payload = None
_original_ensure_modern_xray = None
_original_profile_endpoint = None
_original_customer_profile_endpoint_v261 = None


class XrayDomainIn(BaseModel):
    domain: str | None = None


class XrayDomainPrepareIn(BaseModel):
    issue_certificate: bool = True


def _install_model_column() -> None:
    """Attach the new nullable column to the already-declared Node mapper."""

    if "xray_domain" in Node.__table__.c:
        return

    column = Column(
        "xray_domain",
        String(255),
        nullable=True,
    )

    Node.__table__.append_column(column)
    Node.__mapper__.add_property(
        "xray_domain",
        column,
    )


def _ensure_database_column() -> None:
    """Upgrade existing PostgreSQL installs without touching stored domains."""

    inspector = inspect(engine)

    # Fresh installations are handled by Base.metadata.create_all after this
    # runtime is applied. Existing installations need an idempotent ALTER.
    if not inspector.has_table("nodes"):
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE nodes "
                "ADD COLUMN IF NOT EXISTS xray_domain VARCHAR(255)"
            )
        )


def _stored_xray_domain(node: Node) -> str:
    return xray_modern_admin._clean_domain(
        getattr(node, "xray_domain", None)
    )


def _effective_xray_domain(node: Node) -> str:
    return (
        _stored_xray_domain(node)
        or xray_modern_admin._clean_domain(
            getattr(node, "public_domain", None)
        )
    )


def _profile_uses_tls(profile: str) -> bool:
    meta = xray_modern_runtime.PROFILE_META.get(str(profile))
    if not isinstance(meta, dict):
        return False

    return str(meta.get("security") or "").strip().lower() == "tls"


def _dedicated_direct_tls_authority(
    node: Node,
    profile: str,
    fallback_host: str,
) -> str:
    """Return xray_domain only for TLS profiles with an explicit dedicated domain."""

    if not _profile_uses_tls(profile):
        return str(fallback_host)

    domain = _stored_xray_domain(node)
    if not domain:
        return str(fallback_host)

    return domain


def _profile_endpoint_with_dedicated_domain(
    db: Session,
    node: Node,
    profile: str,
) -> tuple[str, int]:
    """Converge only direct TLS Xray authority; preserve Iran tunnel routing."""

    assert _original_profile_endpoint is not None

    host, port = _original_profile_endpoint(
        db,
        node,
        profile,
    )

    if not _profile_uses_tls(profile):
        return host, int(port)

    try:
        expected_public_port = xray_modern_runtime._public_port(
            int(node.id),
            profile,
        )
    except Exception:
        return host, int(port)

    # A public per-node profile port means the original resolver selected the
    # Iran ingress. Replacing that host with the Exit domain would bypass the
    # tunnel, so the authority must remain untouched.
    if int(port) == int(expected_public_port):
        return host, int(port)

    return (
        _dedicated_direct_tls_authority(
            node,
            profile,
            host,
        ),
        int(port),
    )


def _customer_profile_endpoint_with_dedicated_domain(
    db: Session,
    node: Node,
    profile: str,
    item: dict[str, Any],
) -> tuple[str, int]:
    """Keep explicit tunnel delivery intact while fixing explicit direct TLS."""

    assert _original_customer_profile_endpoint_v261 is not None

    host, port = _original_customer_profile_endpoint_v261(
        db,
        node,
        profile,
        item,
    )

    mode = str(item.get("delivery_mode") or "").strip().lower()

    if mode == "direct":
        host = _dedicated_direct_tls_authority(
            node,
            profile,
            host,
        )

    # Legacy/no-mode delivery delegates to xray_modern_runtime._profile_endpoint,
    # which is already wrapped above and therefore gets the same direct-only
    # behavior without duplicating tunnel detection here.
    return host, int(port)


class _XrayDomainNodeProxy:
    """Read-only Node proxy exposing the dedicated domain as public_domain.

    The existing Xray V2 implementation reads node.public_domain internally.
    Keeping that implementation untouched minimizes production risk while this
    narrow proxy gives only Xray reconciliation the dedicated TLS domain.
    """

    def __init__(self, node: Node, domain: str):
        self._node = node
        self.public_domain = domain

    def __getattr__(self, name: str) -> Any:
        return getattr(self._node, name)


async def _ensure_modern_xray_with_dedicated_domain(
    conn,
    base_port: int,
    node=None,
    *,
    bootstrap_done: bool = False,
):
    assert _original_ensure_modern_xray is not None

    target = node

    if node is not None:
        domain = _effective_xray_domain(node)

        if domain:
            target = _XrayDomainNodeProxy(
                node,
                domain,
            )

    return await _original_ensure_modern_xray(
        conn,
        base_port,
        target,
        bootstrap_done=bootstrap_done,
    )


def _node_payload_with_xray_domain(
    db: Session,
    node: Node,
) -> dict[str, Any]:
    assert _original_node_payload is not None

    payload = dict(
        _original_node_payload(
            db,
            node,
        )
    )

    stored = _stored_xray_domain(node)
    effective = _effective_xray_domain(node)

    payload["xray_domain"] = stored or None
    payload["effective_xray_domain"] = effective or None
    payload["xray_domain_uses_legacy_fallback"] = bool(
        not stored
        and effective
    )

    return payload


def _node_or_404(
    db: Session,
    node_id: int,
) -> Node:
    return xray_modern_admin._node_or_404(
        db,
        node_id,
    )


async def _schedule_subscription_reconcile(
    exit_node_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Start the existing UUID-preserving migration without blocking prepare.

    Import lazily because xray_node_domain_runtime is applied before the V36/V41
    reconciliation wrappers during process startup. By the time an HTTP request
    reaches this function the complete self-hosted runtime has been composed.
    """

    try:
        from . import xray_profile_reconcile_v36

        job = await xray_profile_reconcile_v36.start_xray_reconcile_job(
            int(exit_node_id)
        )
        return dict(job), None
    except Exception as exc:
        # TLS preparation already succeeded. Do not turn a background scheduling
        # problem into a false 500/502 for the admin mutation; expose it as a
        # bounded warning so the operation is truthful and retryable.
        return None, str(exc)[:1000]


@xray_modern_admin.router.get(
    "/nodes/{node_id}/xray-domain"
)
def get_xray_domain(
    node_id: int,
    db: Session = Depends(get_db),
):
    node = _node_or_404(
        db,
        node_id,
    )

    stored = _stored_xray_domain(node)
    effective = _effective_xray_domain(node)

    return {
        "ok": True,
        "node_id": int(node.id),
        "xray_domain": stored or None,
        "effective_xray_domain": effective or None,
        "legacy_public_domain_fallback": bool(
            not stored
            and effective
        ),
    }


@xray_modern_admin.router.put(
    "/nodes/{node_id}/xray-domain"
)
def save_dedicated_xray_domain(
    node_id: int,
    payload: XrayDomainIn,
    db: Session = Depends(get_db),
):
    node = _node_or_404(
        db,
        node_id,
    )

    domain = xray_modern_admin._clean_domain(
        payload.domain
    )

    node.xray_domain = domain or None

    db.commit()
    db.refresh(node)

    return {
        "ok": True,
        "node_id": int(node.id),
        "xray_domain": _stored_xray_domain(node) or None,
        "effective_xray_domain": _effective_xray_domain(node) or None,
        "public_domain": (
            str(getattr(node, "public_domain", None) or "").strip()
            or None
        ),
    }


@xray_modern_admin.router.post(
    "/nodes/{node_id}/xray-domain/prepare"
)
async def prepare_dedicated_xray_domain(
    node_id: int,
    payload: XrayDomainPrepareIn,
    db: Session = Depends(get_db),
):
    node = _node_or_404(
        db,
        node_id,
    )

    domain = _effective_xray_domain(node)

    if not domain:
        raise HTTPException(
            status_code=409,
            detail="دامنه Xray برای این نود ثبت نشده است",
        )

    cfg = xray_modern_admin._xray_cfg(
        db,
        node.id,
    )

    if (
        not cfg
        or xray_modern_runtime._enum_value(
            getattr(cfg, "status", None)
        ) != "online"
    ):
        raise HTTPException(
            status_code=409,
            detail="Xray پایه روی این نود آنلاین نیست",
        )

    conn = await account_delivery.ssh_connect_saved(
        node,
        db,
    )

    try:
        if payload.issue_certificate:
            if not await xray_modern_admin._certificate_available(
                conn,
                domain,
            ):
                await xray_modern_admin._issue_certificate(
                    conn,
                    node,
                    domain,
                )

        base_port = int(
            getattr(cfg, "port", None)
            or account_delivery.DEFAULT_PORTS["v2ray"]
        )

        state = await xray_modern_runtime._ensure_modern_xray(
            conn,
            base_port,
            node,
        )

        runtime = await xray_modern_admin._status_remote(
            conn,
            base_port,
        )

    finally:
        conn.close()
        await conn.wait_closed()

    tls_enabled = bool(runtime.get("tls_enabled"))
    reconcile_job: dict[str, Any] | None = None
    reconcile_error: str | None = None

    if tls_enabled:
        reconcile_job, reconcile_error = await _schedule_subscription_reconcile(
            int(node.id)
        )

    if reconcile_job is not None:
        message = (
            "دامنه و پروفایل‌های Xray آماده شدند؛ "
            "همگام‌سازی اشتراک‌های موجود در پس‌زمینه شروع شد"
        )
    elif reconcile_error:
        message = (
            "دامنه و پروفایل‌های Xray آماده شدند؛ "
            "شروع همگام‌سازی اشتراک‌های موجود ناموفق بود"
        )
    elif tls_enabled:
        message = "دامنه و پروفایل‌های Xray آماده شدند"
    else:
        message = (
            "دامنه ثبت شد اما TLS هنوز آماده نیست؛ "
            "همگام‌سازی اشتراک‌ها شروع نشد"
        )

    return {
        "ok": True,
        "node_id": int(node.id),
        "xray_domain": _stored_xray_domain(node) or None,
        "effective_xray_domain": domain,
        "tls_enabled": tls_enabled,
        "available_profiles": state.get("available_profiles") or [],
        "runtime": runtime,
        "reconcile_job": reconcile_job,
        "reconcile_error": reconcile_error,
        "message": message,
    }


def apply_xray_node_domain_runtime() -> None:
    global _runtime_applied
    global _original_node_payload
    global _original_ensure_modern_xray
    global _original_profile_endpoint
    global _original_customer_profile_endpoint_v261

    if _runtime_applied:
        return

    _install_model_column()
    _ensure_database_column()

    # Capture the final production wrappers AFTER JSON-temp, Modern and Repair
    # runtimes have been applied. Our wrapper therefore composes with them
    # instead of replacing any repair/self-heal behavior.
    _original_ensure_modern_xray = (
        xray_modern_runtime._ensure_modern_xray
    )

    xray_modern_runtime._ensure_modern_xray = (
        _ensure_modern_xray_with_dedicated_domain
    )

    # These modules imported the function by name, so update their local
    # bindings too. That keeps admin prepare and repair flows on the same domain.
    xray_modern_admin._ensure_modern_xray = (
        _ensure_modern_xray_with_dedicated_domain
    )
    xray_modern_repair_runtime._ensure_modern_xray = (
        _ensure_modern_xray_with_dedicated_domain
    )

    _original_profile_endpoint = (
        xray_modern_runtime._profile_endpoint
    )
    xray_modern_runtime._profile_endpoint = (
        _profile_endpoint_with_dedicated_domain
    )

    # V30/V261 is intentionally imported lazily. self_hosted_runtime imports
    # all runtime modules before composing them, so this avoids introducing a
    # module-cycle while still patching the final customer delivery resolver.
    from . import xray_customer_profile_policy_v30

    _original_customer_profile_endpoint_v261 = (
        xray_customer_profile_policy_v30._profile_endpoint_v261
    )
    xray_customer_profile_policy_v30._profile_endpoint_v261 = (
        _customer_profile_endpoint_with_dedicated_domain
    )

    _original_node_payload = (
        xray_modern_admin._node_payload
    )
    xray_modern_admin._node_payload = (
        _node_payload_with_xray_domain
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_NODE_DOMAIN_RUNTIME_V3_ACTIVE "
        "dedicated_domain=1 legacy_public_domain_fallback=1 "
        "direct_tls_authority=dedicated_domain tunnel_authority=preserved "
        "reality_authority=preserved subscription_reconcile_after_tls=1 "
        "background=1 uuid_preserved=1",
        flush=True,
    )
