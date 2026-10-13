import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from redis import Redis
from sqlalchemy import text

from .config import settings
from .database import Base, engine
from . import store_models
from . import payment_models
from . import support_models
from . import user_notification_models
from . import telegram_models
from . import renewal_models
from . import models_reseller
from . import domain_models
from . import branding_models  # register reseller tables
from . import storefront_settings_models  # TWINPANEL_STOREFRONT_CMS_V74
from . import two_factor_models
from . import runtime_settings_model
from . import download_asset_models
from .routers import admin, auth, nodes, plans, provision, subscriptions, tunnels, resellers, reseller_portal, domains, branding
from .routers import bootstrap as bootstrap_router_module
from .routers.two_factor import router as two_factor_router  # TWINPANEL_REAL_2FA_REGISTER_V1
from .routers import quota_security, account_delivery
from .routers.store import router as store_router
from .routers.general_settings import router as general_settings_router
from .routers.storefront_settings import router as storefront_settings_router
from .routers.notification_settings import router as notification_settings_router
from .routers.runtime_endpoints import router as runtime_endpoints_router
from .routers.node_recovery import router as node_recovery_router
from .routers.tunnel_managed import router as tunnel_managed_router
from .routers.modern_transports import router as modern_transports_router
from .routers.download_assets import admin_router as download_assets_admin_router, public_router as download_assets_public_router
from .routers.public_connection_v3 import router as public_connection_v3_router
from .self_hosted_runtime import apply_self_hosted_runtime
from .admin_notification_service import notification_watch_loop
from .services.customer_maintenance import customer_maintenance_loop
# TWINPANEL_REAL_ADMIN_NOTIFICATION_REGISTER_V1
# TWINPANEL_USERNAME_SETTINGS_REGISTER_V2
from .routers.payments import router as payments_router
from .routers.payment_automation import router as payment_automation_router
from .routers.payment_receipts_local import router as payment_receipts_local_router
from .routers.sms_reader_dashboard import router as sms_reader_dashboard_router
from .routers.sms_reader import router as sms_reader_router
from .routers.support import router as support_router, admin_router as support_admin_router
# TWINPANEL_USER_NOTIFICATION_REGISTER_V1
from .routers.user_notifications import (
    router as user_notification_router,
    admin_router as user_notification_admin_router,
)
from .routers.telegram_bot import router as telegram_bot_router
from .routers.telegram_manager import router as telegram_manager_router
from .routers.customer_wallet import router as customer_wallet_router, admin_router as customer_wallet_admin_router
from .routers.customer_subscription_management import router as customer_subscription_management_router
from .routers.subscription_admin_v2 import router as subscription_admin_v2_router

# Product/self-hosted compatibility must be applied before requests or
# background workers can invoke migrated tunnel/node helpers.
apply_self_hosted_runtime()

# TWINPANEL_PAYMENT_TABLE_BOOTSTRAP_V1
# Payment/store models must be registered before create_all.
_ = store_models
_ = payment_models
_ = support_models
_ = telegram_models
_ = renewal_models
_ = two_factor_models
_ = storefront_settings_models
_ = runtime_settings_model
_ = download_asset_models


# TWINPANEL_ADMIN_PANEL_NOTIFICATION_REGISTER_V1
from .admin_panel_notification_models import AdminPanelNotification
from .routers.admin_panel_notifications import (
    router as admin_panel_notifications_router,
)


# TWINPANEL_RESELLER_NOTIFICATION_MODEL_BEFORE_CREATE_ALL_V1
from . import reseller_notification_models


Base.metadata.create_all(bind=engine)


# TWINPANEL_TUNNEL_WATCHDOG_LIFESPAN_V1
@asynccontextmanager
async def lifespan(app: FastAPI):
    watchdog_task = asyncio.create_task(
        tunnels.tunnel_watchdog_loop(),
        name="tunnel-watchdog",
    )
    notification_task = asyncio.create_task(
        notification_watch_loop(),
        name="admin-notification-watch",
    )
    customer_maintenance_task = asyncio.create_task(
        customer_maintenance_loop(),
        name="customer-maintenance",
    )

    try:
        yield

    finally:
        watchdog_task.cancel()
        notification_task.cancel()
        customer_maintenance_task.cancel()

        for task in (
            watchdog_task,
            notification_task,
            customer_maintenance_task,
        ):
            try:
                await task
            except asyncio.CancelledError:
                pass


# TWINPANEL_RESELLER_NOTIFICATION_REGISTER_V1
from .reseller_notification_models import ResellerNotification
from .routers.reseller_notifications import (
    router as reseller_notifications_router,
)


app = FastAPI(
    title=settings.app_name,
    version="0.9.7",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "version": "0.9.7",
    }


@app.get("/health/ready")
def readiness():
    checks = {
        "database": False,
        "redis": False,
    }
    errors: dict[str, str] = {}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        errors["database"] = str(exc)[:300]

    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        checks["redis"] = bool(client.ping())
        client.close()
    except Exception as exc:
        errors["redis"] = str(exc)[:300]

    payload = {
        "ok": all(checks.values()),
        "service": settings.app_name,
        "version": "0.9.7",
        "checks": checks,
    }

    if errors:
        payload["errors"] = errors

    if not payload["ok"]:
        raise HTTPException(
            status_code=503,
            detail=payload,
        )

    return payload


app.include_router(runtime_endpoints_router)
app.include_router(bootstrap_router_module.router)
app.include_router(auth.router)
app.include_router(two_factor_router)
app.include_router(plans.router)
app.include_router(storefront_settings_router)
app.include_router(store_router)
app.include_router(general_settings_router)
app.include_router(notification_settings_router)
# Payment automation overrides the legacy payment methods/settings/submit
# routes while delegating all unchanged behavior back to the legacy handlers.
# It must be registered before the legacy payments router.
app.include_router(payment_automation_router)
# Register local receipt handling before the legacy payments router so the
# admin receipt path can transparently serve both local and Telegram receipts.
app.include_router(payment_receipts_local_router)
app.include_router(payments_router)
# Restore the proven SMS Reader operational dashboard before the legacy
# SMS Reader route so /admin/sms-reader includes devices, pair codes and events.
app.include_router(sms_reader_dashboard_router)
app.include_router(sms_reader_router)
app.include_router(support_router)
app.include_router(support_admin_router)
app.include_router(user_notification_router)
app.include_router(user_notification_admin_router)
app.include_router(telegram_bot_router)
app.include_router(telegram_manager_router)
app.include_router(customer_wallet_router)
app.include_router(customer_wallet_admin_router)
app.include_router(customer_subscription_management_router)
app.include_router(download_assets_admin_router)
app.include_router(download_assets_public_router)
app.include_router(nodes.router)
app.include_router(node_recovery_router)
app.include_router(subscriptions.router)
app.include_router(subscription_admin_v2_router, prefix="/v1")
app.include_router(tunnels.router)
app.include_router(tunnel_managed_router)
app.include_router(modern_transports_router)
app.include_router(admin.router)
app.include_router(resellers.router)
app.include_router(reseller_portal.router)
app.include_router(domains.router)
app.include_router(branding.router)
app.include_router(provision.router)
app.include_router(quota_security.router)
app.include_router(account_delivery.router)
# Register the redesigned exact /v1/connect/{token} page before the legacy
# public router. Legacy sub-routes such as /usage and /qr remain available.
app.include_router(public_connection_v3_router)
app.include_router(account_delivery.public_router)
app.include_router(account_delivery.customer_router)

# TWINPANEL_VPN_SETTINGS_V1
from .routers.vpn_settings import router as vpn_settings_router
app.include_router(vpn_settings_router)


# Mother server access policy
from .routers.mother_access import router as mother_access_router
app.include_router(mother_access_router)


# TWINPANEL_RESELLER_BOT_API_V1
from .routers.reseller_bot import (
    router as reseller_bot_router,
)
app.include_router(reseller_bot_router)


# TWINPANEL_RESELLER_BOT_COMMERCE_V1
from .routers.reseller_bot_orders import (
    router as reseller_bot_orders_router,
)
app.include_router(reseller_bot_orders_router)


# TWINPANEL_DISCOUNT_CORE_V1
from .routers.discounts import router as discounts_router
app.include_router(discounts_router)

app.include_router(admin_panel_notifications_router)

app.include_router(reseller_notifications_router)


# TWINPANEL_ADMIN_BACKUP_ROUTER_V1
from .routers.backups import router as backups_router
app.include_router(backups_router)
