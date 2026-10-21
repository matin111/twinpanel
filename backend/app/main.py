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
from . import reseller_bot_order_models
from . import reseller_pool_models
from . import reseller_owned_plan_models
from . import domain_models
from . import branding_models  # register reseller tables
from . import storefront_settings_models  # TWINPANEL_STOREFRONT_CMS_V74
from . import two_factor_models
from . import runtime_settings_model
from . import download_asset_models
from .payment_crypto_schema import ensure_payment_crypto_schema
from .wallet_crypto_schema import ensure_wallet_crypto_schema
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
from .routers.public_connection_hub_live_v5 import router as public_connection_hub_live_v5_router
from .routers.public_connection_live_v4 import router as public_connection_live_v4_router
from .routers.public_connection_v3 import router as public_connection_v3_router
from .routers.reseller_admin_v2 import router as reseller_admin_v2_router
from .routers.reseller_traffic_admin_v2 import router as reseller_traffic_admin_v2_router
from .routers.reseller_traffic_purchase_v3 import router as reseller_traffic_purchase_v3_router
from .routers.reseller_owned_plans import router as reseller_owned_plans_router
from .routers.reseller_sale_v2 import router as reseller_sale_v2_router
from .routers.reseller_profile_v2 import router as reseller_profile_v2_router
from .routers.reseller_subscription_volume_v2 import router as reseller_subscription_volume_v2_router
from .routers.admin_user_isolation import router as admin_user_isolation_router
from .routers.system_release import router as system_release_router
from .self_hosted_runtime import apply_self_hosted_runtime
from .xray_modern_runtime import router as xray_modern_router
from .xray_modern_admin import router as xray_modern_admin_router
from .admin_notification_service import notification_watch_loop
from .services.customer_maintenance import customer_maintenance_loop
from .services.payment_fulfillment_fast_path import payment_fulfillment_recovery_loop
from .services.payment_market_rates import payment_market_loop
from .services.wallet_payment_automation import wallet_payment_automation_loop
from .license_guard import LicenseMutationGuardMiddleware
from .system_release import current_version, license_validation_loop
# TWINPANEL_REAL_ADMIN_NOTIFICATION_REGISTER_V1
# TWINPANEL_USERNAME_SETTINGS_REGISTER_V2
from .routers.payment_approval_fast import router as payment_approval_fast_router
from .routers.payments import router as payments_router
from .routers.payment_crypto_discount import router as payment_crypto_discount_router
from .routers.payment_native_gateways import router as payment_native_gateways_router
from .routers.payment_market_rates import router as payment_market_rates_router
from .routers.payment_automation import router as payment_automation_router
from .routers.payment_receipts_local import router as payment_receipts_local_router
from .routers.sms_reader_dashboard import router as sms_reader_dashboard_router
from .routers.wallet_sms_reader import router as wallet_sms_reader_router
from .routers.sms_reader import router as sms_reader_router
from .routers.support import router as support_router, admin_router as support_admin_router
# TWINPANEL_USER_NOTIFICATION_REGISTER_V1
from .routers.user_notifications import (
    router as user_notification_router,
    admin_router as user_notification_admin_router,
)
from .routers.telegram_bot import router as telegram_bot_router
from .routers.telegram_manager import router as telegram_manager_router
from .routers.wallet_payment_v2 import router as wallet_payment_v2_router, admin_router as wallet_payment_v2_admin_router
from .routers.wallet_admin_v2 import router as wallet_admin_v2_router
from .routers.customer_wallet import router as customer_wallet_router, admin_router as customer_wallet_admin_router
from .routers.customer_subscription_management import router as customer_subscription_management_router
from .routers.subscription_admin_v2 import router as subscription_admin_v2_router

# Product/self-hosted compatibility must be applied before requests or
# background workers can invoke migrated tunnel/node helpers.
apply_self_hosted_runtime()

# TWINPANEL_PAYMENT_TABLE_BOOTSTRAP_V1
# Payment/store/reseller-bot models must be registered before create_all.
_ = store_models
_ = payment_models
_ = support_models
_ = telegram_models
_ = renewal_models
_ = two_factor_models
_ = storefront_settings_models
_ = runtime_settings_model
_ = download_asset_models
_ = reseller_bot_order_models
_ = reseller_pool_models
_ = reseller_owned_plan_models

# TWINPANEL_ADMIN_PANEL_NOTIFICATION_REGISTER_V1
from .admin_panel_notification_models import AdminPanelNotification
from .routers.admin_panel_notifications import (
    router as admin_panel_notifications_router,
)

# TWINPANEL_RESELLER_NOTIFICATION_MODEL_BEFORE_CREATE_ALL_V1
from . import reseller_notification_models

Base.metadata.create_all(bind=engine)
# Existing installations need idempotent ALTERs because create_all does not add
# newly introduced columns to existing tables.
ensure_payment_crypto_schema()
ensure_wallet_crypto_schema()


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
    payment_fulfillment_task = asyncio.create_task(
        payment_fulfillment_recovery_loop(),
        name="payment-fulfillment-recovery",
    )
    payment_market_task = asyncio.create_task(
        payment_market_loop(),
        name="payment-market-rates",
    )
    wallet_payment_task = asyncio.create_task(
        wallet_payment_automation_loop(),
        name="wallet-payment-automation",
    )
    license_validation_task = asyncio.create_task(
        license_validation_loop(),
        name="license-validation",
    )

    try:
        yield

    finally:
        watchdog_task.cancel()
        notification_task.cancel()
        customer_maintenance_task.cancel()
        payment_fulfillment_task.cancel()
        payment_market_task.cancel()
        wallet_payment_task.cancel()
        license_validation_task.cancel()

        for task in (
            watchdog_task,
            notification_task,
            customer_maintenance_task,
            payment_fulfillment_task,
            payment_market_task,
            wallet_payment_task,
            license_validation_task,
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

APP_VERSION = current_version()

app = FastAPI(
    title=settings.app_name,
    version=APP_VERSION,
    lifespan=lifespan,
)
app.add_middleware(LicenseMutationGuardMiddleware)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "version": APP_VERSION,
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
        "version": APP_VERSION,
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
# Crypto purchase discount overrides the exact gateway /methods and /intents
# routes. It must be first so the discounted immutable quote is the route FastAPI
# resolves for new crypto plan purchases.
app.include_router(payment_crypto_discount_router)
# Exact crypto payment router removes USDT-TRC20 and exposes USDT-BEP20 +
# native TRX + native BNB with immutable live-rate quotes.
app.include_router(payment_native_gateways_router)
# Resilient market-rate and automation-status API must precede the older
# payment automation router because it overrides /admin/live-rate.
app.include_router(payment_market_rates_router)
# Payment automation keeps legacy SMS Reader and historical crypto behavior.
app.include_router(payment_automation_router)
# Register local receipt handling before the legacy payments router so the
# admin receipt path can transparently serve both local and Telegram receipts.
app.include_router(payment_receipts_local_router)
# Canonical approval fast path must precede the legacy payments router. All
# other payment endpoints continue to come from the existing router unchanged.
app.include_router(payment_approval_fast_router)
app.include_router(payments_router)
# Operational SMS dashboard stays available, while the wallet-aware event
# endpoints come before the legacy reader so the same bank SMS can safely match
# either a plan payment or a wallet top-up, never both.
app.include_router(sms_reader_dashboard_router)
app.include_router(wallet_sms_reader_router)
app.include_router(sms_reader_router)
app.include_router(support_router)
app.include_router(support_admin_router)
app.include_router(user_notification_router)
app.include_router(user_notification_admin_router)
app.include_router(telegram_bot_router)
app.include_router(telegram_manager_router)
# Modern customer wallet payment routes come first. Admin V2 then overrides
# wallet listing, idempotent approval and manual balance adjustment with
# notifications. The legacy admin router remains after it for reject and other
# compatibility endpoints that V2 intentionally does not redefine.
app.include_router(wallet_payment_v2_router)
app.include_router(wallet_payment_v2_admin_router)
app.include_router(wallet_admin_v2_router)
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
# Central admin user-management routes must win before the legacy admin router.
# They hide reseller owners/customers while leaving reseller subscriptions visible.
app.include_router(admin_user_isolation_router)
app.include_router(admin.router)
# Simplified volume-only reseller admin routes override legacy create/list/stats
# and traffic adjustment while keeping the older detail/plan endpoints available.
app.include_router(reseller_admin_v2_router)
app.include_router(reseller_traffic_admin_v2_router)
app.include_router(resellers.router)
# Reseller-owned plans and traffic purchase routes must win before legacy portal
# routes. Sales/account creation are unlimited; the shared pool is charged only
# from accepted real usage events.
app.include_router(reseller_owned_plans_router)
app.include_router(reseller_traffic_purchase_v3_router)
# Correct reseller profile/edit/renewal flows must precede legacy routes.
app.include_router(reseller_sale_v2_router)
app.include_router(reseller_profile_v2_router)
app.include_router(reseller_subscription_volume_v2_router)
app.include_router(reseller_portal.router)
app.include_router(domains.router)
app.include_router(branding.router)
app.include_router(provision.router)
app.include_router(quota_security.router)
# Preserve the modern Xray migration/provisioning routes that landed on main
# while keeping the stable release/account-delivery ordering intact.
app.include_router(xray_modern_router)
app.include_router(xray_modern_admin_router)
app.include_router(account_delivery.router)
# Public Connection Hub V5 owns the exact /v1/connect/{token} page while the
# existing V4 router continues to own /live telemetry. V3 and legacy stay as
# compatibility fallbacks and rollback references.
app.include_router(public_connection_hub_live_v5_router)
app.include_router(public_connection_live_v4_router)
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
from .routers.reseller_bot_orders_volume_v2 import (
    router as reseller_bot_orders_volume_v2_router,
)
from .routers.reseller_bot_orders_owned_v3 import (
    router as reseller_bot_orders_owned_v3_router,
)
from .routers.reseller_bot_wallet_topups import (
    router as reseller_bot_wallet_topups_router,
)
# Wallet top-up review and owned-plan approval win first, then usage-only renewal
# compatibility, then legacy endpoints for receipts/payment methods/history.
app.include_router(reseller_bot_wallet_topups_router)
app.include_router(reseller_bot_orders_owned_v3_router)
app.include_router(reseller_bot_orders_volume_v2_router)
app.include_router(reseller_bot_orders_router)

# TWINPANEL_DISCOUNT_CORE_V1
from .routers.discounts import router as discounts_router
app.include_router(discounts_router)

app.include_router(admin_panel_notifications_router)
app.include_router(reseller_notifications_router)
app.include_router(system_release_router)

# TWINPANEL_ADMIN_BACKUP_ROUTER_V1
from .routers.backups import router as backups_router
app.include_router(backups_router)
