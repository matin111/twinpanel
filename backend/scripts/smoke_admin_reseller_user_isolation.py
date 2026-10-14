from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(path: Path, *markers: str) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"missing marker {marker!r} in {path}")


require(
    ROOT / "app" / "routers" / "admin_user_isolation.py",
    "TWINPANEL_ADMIN_RESELLER_USER_ISOLATION_V1",
    "ResellerCustomer.user_id",
    "Reseller.owner_user_id",
    '@router.get("/users-page")',
    '@router.get("/users", response_model=list[UserOut])',
    '@router.patch("/users/{user_id}"',
    '@router.delete("/users/{user_id}")',
    '@router.post("/users/{user_id}/toggle-active")',
    '@router.post("/users/{user_id}/reset-password")',
    'payload["total_users"]',
)

require(
    ROOT / "app" / "main.py",
    "admin_user_isolation_router",
    "app.include_router(admin_user_isolation_router)",
    "app.include_router(admin.router)",
)

main_text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
if main_text.index("app.include_router(admin_user_isolation_router)") > main_text.index(
    "app.include_router(admin.router)"
):
    raise SystemExit("isolation router must be registered before legacy admin router")

require(
    ROOT / "app" / "routers" / "wallet_admin_v2.py",
    "_is_reseller_scoped_user",
    "ResellerCustomer.user_id",
    "Reseller.owner_user_id",
    'raise HTTPException(status_code=404, detail="کاربر پیدا نشد")',
)

print("admin reseller user isolation smoke: OK")
