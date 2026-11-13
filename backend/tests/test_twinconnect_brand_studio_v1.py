"""Protect TwinConnect tenant-scoped uploads and live brand discovery."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/"backend/app/routers/central_app_assets_v1.py"
BRAND=ROOT/"backend/app/routers/central_app_v1.py"
CREDS=ROOT/"backend/app/routers/central_app_credentials_v1.py"
MAIN=ROOT/"backend/app/main.py"
UI=ROOT/"components/central-app-brand-manager.tsx"

class TwinConnectBrandStudioContract(unittest.TestCase):
    def test_router_mounted_and_python_parses(self):
        for item in (ASSETS,BRAND,CREDS,MAIN):
            ast.parse(item.read_text(encoding="utf-8"))
        source=MAIN.read_text(encoding="utf-8")
        self.assertIn("app.include_router(central_app_assets_v1_router)",source)

    def test_logo_upload_is_tenant_scoped_and_validated(self):
        source=ASSETS.read_text(encoding="utf-8")
        for route in ('/admin/assets/logo','/admin/resellers/{reseller_id}/assets/logo','/reseller/assets/logo'):
            self.assertIn(route,source)
        self.assertIn("Depends(require_reseller)",source)
        self.assertIn("Depends(require_admin)",source)
        self.assertIn("int(reseller.id)",source)
        self.assertIn("MAX_LOGO_BYTES",source)
        self.assertIn("hashlib.sha256(blob)",source)
        self.assertIn("record.logo_url = logo_url",source)
        self.assertNotIn("file.filename",source)

    def test_app_brand_reads_saved_logo_and_is_available_on_session_refresh(self):
        brand=BRAND.read_text(encoding="utf-8")
        credentials=CREDS.read_text(encoding="utf-8")
        self.assertIn('"logo_url": info["logo_url"]',brand)
        self.assertIn('info["logo_url"] or getattr(branding',brand)
        self.assertIn('@router.get("/session/brand")',credentials)
        self.assertIn("subscription_app_brand_preview(",credentials)
        self.assertIn('"Cache-Control": "private, no-store',credentials)

    def test_brand_studio_uses_new_owner_editable_defaults_and_live_flow_preview(self):
        ui=UI.read_text(encoding="utf-8")
        css=(ROOT/"components/central-app-brand-studio.css").read_text(encoding="utf-8")
        for color in ("#5CC8B7", "#81BDD4", "#479E9B", "#0E1E2B", "#193641"):
            self.assertIn(color,ui)
        self.assertIn("setAppearance(current=>current?{...current,",ui)
        self.assertIn("background_color:preset.background",ui)
        self.assertNotIn('["#7C3AED","#4F46E5"]',ui)
        self.assertIn("tbs-data-flow",ui)
        self.assertNotIn('className="tbs-connect-orb"',ui)
        self.assertIn("tbs-dark-only",css)
        self.assertNotIn('<option value="light">',ui)
        self.assertNotIn('<option value="system">',ui)
        self.assertIn('theme_mode:"dark"',ui)
        self.assertIn('background:appearance?.background_color',ui)

    def test_brand_studio_has_real_logo_upload_and_reseller_scope(self):
        ui=UI.read_text(encoding="utf-8")
        self.assertIn('body.append("file",file)',ui)
        self.assertIn('role==="reseller"?"reseller/assets/logo"',ui)
        self.assertIn('role==="reseller"?"reseller/profile"',ui)
        self.assertIn('appearanceApi.save(role,{...appearance,theme_mode:"dark"},resellerId)',ui)
        self.assertIn("tbs-device",ui)

if __name__=="__main__":
    unittest.main()
