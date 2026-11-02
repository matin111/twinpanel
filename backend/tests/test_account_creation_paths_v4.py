from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "backend/app/routers/account_creation_runtime_v4.py"
CENTRAL = ROOT / "backend/app/routers/central_account_delivery_runtime_v3.py"
FAST = ROOT / "backend/app/routers/subscription_create_fast_v1.py"
STORE = ROOT / "backend/app/routers/store.py"
RESELLER_BOT = ROOT / "backend/app/routers/reseller_bot_orders.py"
RESELLER = ROOT / "backend/app/routers/reseller_sale_v2.py"
UI = ROOT / "components/admin-manual-subscription-create.tsx"
ROUTER = ROOT / "components/routed-page-client.tsx"
CLIENT = ROOT / "lib/subscription-create-fast-api.ts"


def test_manual_fast_create_uses_degraded_preflight_runtime() -> None:
    runtime = RUNTIME.read_text(encoding="utf-8")
    central = CENTRAL.read_text(encoding="utf-8")
    fast = FAST.read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")

    assert "advisory_subscription_provisioning_preflight" in runtime
    assert '"degraded": bool(unavailable)' in runtime
    assert "if not ready_protocols:" in runtime
    assert "subscription_create_fast_v1.assert_subscription_provisioning_ready" in runtime
    assert "install_account_creation_runtime_v4()" in central

    assert '@router.post("/admin-create-fast-v1", status_code=202)' in fast
    assert "background_tasks.add_task(" in fast
    assert "_provision_subscription_background" in fast
    assert "_should_suspend_after_background_provisioning" in fast
    assert "createSubscriptionFastV1" in ui
    assert "/v1/subscriptions/admin-create-fast-v1" in client

    # The real admin/subscriptions route must keep the per-account protocol picker.
    assert 'AdminManualSubscriptionCreate=dynamic(' in router
    assert '<AdminManualSubscriptionCreate/>' in router
    assert 'const [protocols,setProtocols]=useState<string[]>([])' in ui
    assert 'setProtocols(catalogPayload.protocols.filter(item=>item.family==="classic").map(item=>item.key))' in ui
    assert 'انتخاب همه ۱۵ پروتکل' in ui
    assert 'پروتکل‌های کلاسیک' in ui
    assert 'پروتکل‌های جدید' in ui
    assert 'checked={protocols.includes(item.key)}' in ui
    assert 'protocols,' in ui


def test_direct_reseller_sale_provisions_real_account_and_uses_15_protocol_template() -> None:
    runtime = RUNTIME.read_text(encoding="utf-8")
    central = CENTRAL.read_text(encoding="utf-8")
    reseller = RESELLER.read_text(encoding="utf-8")

    assert '@router.post("/v1/reseller/subscriptions/sell")' in runtime
    assert "sale = reseller_sale_v2._sale_impl(" in runtime
    assert "provisioning = await provision_account_v1(" in runtime
    assert '"provisioning_complete": True' in runtime
    assert "plan_template_protocols(db, int(plan.id))" in runtime
    assert "normalize_protocols(" in runtime
    assert "reseller_sale_v2._resolve_protocols = reseller_plan_protocols_v4" in runtime
    assert "_runtime_endpoints.router.include_router(_account_creation_runtime_v4_router)" in central

    # Historical DB/accounting implementation remains the shared sale writer;
    # runtime V4 adds actual provisioning without duplicating accounting logic.
    assert "create_subscription_core(" in reseller


def test_store_and_reseller_bot_share_central_15_protocol_provisioner() -> None:
    central = CENTRAL.read_text(encoding="utf-8")
    store = STORE.read_text(encoding="utf-8")
    reseller_bot = RESELLER_BOT.read_text(encoding="utf-8")

    assert "store_fulfillment.provision_account = provision_account_v1" in central
    assert "reseller_fulfillment.provision_account = provision_account_v1" in central
    assert "provision_result = await provision_account(" in store
    assert "provision = await provision_account(" in reseller_bot


def test_release_must_not_hide_db_only_reseller_regression_again() -> None:
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert "direct panel endpoint previously stopped after" in runtime
    assert "create_subscription_core()" in runtime
    assert "Runtime route precedence" in runtime
