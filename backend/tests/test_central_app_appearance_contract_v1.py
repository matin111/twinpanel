"""No-database regression tests for scoped app colors and background policies."""
import ast
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress

ROOT = Path(__file__).resolve().parents[2]
APPEARANCE = ROOT / "backend/app/central_app_appearance.py"
API = ROOT / "backend/app/routers/central_app_appearance_v1.py"
PUBLIC = ROOT / "backend/app/routers/central_app_v1.py"
MAIN = ROOT / "backend/app/main.py"
ADMIN_UI = ROOT / "components/branding-settings.tsx"
RESELLER_UI = ROOT / "components/reseller-portal-parity-v2.tsx"


class FakeHTTPException(Exception):
    def __init__(self, *, status_code, detail):
        self.status_code = status_code
        self.detail = detail


def validators():
    tree = ast.parse(APPEARANCE.read_text())
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ("_validate_background_url", "validate_appearance")]
    module = ast.Module(body=funcs, type_ignores=[])
    env = {
        "re": re, "urlsplit": urlsplit, "ipaddress": ipaddress,
        "HTTPException": FakeHTTPException,
        "AppearanceIn": object,
        "LABEL": re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"),
        "COLOR": re.compile(r"^#[0-9A-Fa-f]{6}$"),
    }
    exec(compile(module, str(APPEARANCE), "exec"), env)
    return env


class AppearanceContractTests(unittest.TestCase):
    def test_safe_https_image_and_explicit_colors(self):
        env = validators()
        self.assertEqual(
            env["_validate_background_url"]("https://cdn.good-domain.com/hero.webp"),
            "https://cdn.good-domain.com/hero.webp",
        )
        for url in (
            "javascript:alert(1)", "http://cdn.good-domain.com/a.png",
            "file:///etc/passwd", "data:text/html;base64,AA",
            "https://127.0.0.1/p.png", "https://192.168.1.1/p.png",
            "https://localhost/test.png", "https://site.local/image.png",
            "https://user:pass@cdn.good-domain.com/image.png",
            "https://cdn.good-domain.com:8080/a.png",
        ):
            with self.subTest(url=url), self.assertRaises(FakeHTTPException):
                env["_validate_background_url"](url)

        class Payload:
            def __init__(self, **values): self.values = values
            def model_dump(self): return dict(self.values)

        values = {
            "primary_color": "#abcdef", "secondary_color": "#123456",
            "button_color": "#abcdef", "background_color": "#010203",
            "surface_color": "#123456", "background_style": "gradient",
            "background_image_url": None, "theme_mode": "dark",
        }
        clean = env["validate_appearance"](Payload(**values))
        self.assertEqual(clean["primary_color"], "#ABCDEF")
        with self.assertRaises(FakeHTTPException):
            env["validate_appearance"](Payload(**{**values, "background_style": "image"}))
        with self.assertRaises(FakeHTTPException):
            env["validate_appearance"](Payload(**{**values, "button_color": "not-a-color"}))

    def test_admin_and_reseller_ownership_scopes_are_distinct(self):
        code = API.read_text()
        self.assertIn("save_appearance(db, 0, payload)", code)
        self.assertIn("save_appearance(db, int(reseller.id), payload)", code)
        self.assertIn("reset_appearance(db, int(reseller.id))", code)
        self.assertIn("reseller: Reseller = Depends(require_reseller)", code)
        self.assertIn("_=Depends(require_admin)", code)
        self.assertIn('_reseller(db, reseller_id)', code)
        self.assertNotIn('get_current_user', code)

    def test_brand_lookup_resolves_real_subscription_owner(self):
        code = PUBLIC.read_text()
        self.assertIn("ResellerSubscription.subscription_id == sub.id", code)
        self.assertIn("resolve_appearance(db, reseller.id)", code)
        self.assertIn("resolve_appearance(db, 0)", code)
        self.assertIn("central_app_entitled()", code)

    def test_app_theme_is_additive_and_connected_to_both_panels(self):
        main = MAIN.read_text()
        self.assertIn("central_app_appearance_models", main)
        self.assertIn("app.include_router(central_app_appearance_v1_router)", main)
        self.assertIn('<CentralAppAppearanceStudio role="admin"/>', ADMIN_UI.read_text())
        self.assertIn('<CentralAppAppearanceStudio role="reseller"/>', RESELLER_UI.read_text())


if __name__ == "__main__":
    unittest.main()
