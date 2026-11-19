"""Offline contracts for secure TwinConnect panel-origin changes."""
import ast
import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "app/services/central_app_origin_sync.py").read_text()
DOMAINS = (ROOT / "app/routers/domains.py").read_text()
APP = (ROOT / "app/routers/central_app_v1.py").read_text()


def load_sync(scope):
    tree = ast.parse(SERVICE)
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "sync_app_origin")
    local = dict(scope)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<sync>", "exec"), local)
    return local["sync_app_origin"]


class HttpFailure(Exception):
    def __init__(self, status):
        self.response = SimpleNamespace(status_code=status)


class OriginSyncContracts(unittest.TestCase):
    def test_ssl_route_and_read_only_identity_proof_are_wired(self):
        self.assertIn('"/public/directory-proof"', APP)
        self.assertIn('"namespace": installation_namespace(ensure_installation_id())', APP)
        self.assertIn("sync_app_origin_safely(db, force=True)", DOMAINS)
        self.assertIn("item.domain_type == DomainType.API", DOMAINS)
        self.assertIn("sync_app_origin_background", APP)
        self.assertIn('"/v1/app/origin/sync"', SERVICE)
        self.assertIn('"/v1/app/register"', SERVICE)

    def test_new_address_is_committed_only_after_vendor_confirmation(self):
        events = []
        vendor_failed = [True]
        def vendor(path, payload):
            events.append(("vendor", path, payload["api_origin"]))
            if vendor_failed[0]:
                raise RuntimeError("network unavailable")
            return {
                "namespace": "TP" + "A" * 16,
                "short_namespace": "TP" + "A" * 6,
                "api_origin": payload["api_origin"],
            }
        scope = {
            "Session": object, "central_app_entitled": lambda: True,
            "_domain_origin": lambda db, kind: "https://new.example.org",
            "DomainType": SimpleNamespace(API="api"), "urlsplit": urlsplit, "ensure_installation_id": lambda: "install-one",
            "load_license_state": lambda: {"signed_entitlement": "signed-app"},
            "hashlib": hashlib, "_last_synced": lambda: {},
            "_save_synced": lambda *args: events.append(("saved", args)),
            "_vendor_post": vendor, "installation_namespace": lambda value: "TP" + "A" * 16,
            "save_app_directory_alias": lambda *args: events.append(("alias", args)),
            "httpx": SimpleNamespace(HTTPStatusError=HttpFailure),
        }
        sync = load_sync(scope)
        with self.assertRaises(RuntimeError):
            sync(object())
        self.assertEqual([e[0] for e in events], ["vendor"])
        vendor_failed[0] = False
        result = sync(object())
        self.assertEqual(result["status"], "synced")
        self.assertEqual([e[0] for e in events[-3:]], ["vendor", "alias", "saved"])

    def test_first_registration_only_on_missing_directory(self):
        paths = []
        def vendor(path, payload):
            paths.append(path)
            if path.endswith("/sync"):
                raise HttpFailure(404)
            return {"namespace": "TP" + "B" * 16,
                    "short_namespace": "TP" + "B" * 6}
        sync = load_sync({
            "Session": object, "central_app_entitled": lambda: True,
            "_domain_origin": lambda db, kind: "https://panel.example.org",
            "DomainType": SimpleNamespace(API="api"), "urlsplit": urlsplit, "ensure_installation_id": lambda: "install-two",
            "load_license_state": lambda: {"signed_entitlement": "signed"},
            "hashlib": hashlib, "_last_synced": lambda: {},
            "_save_synced": lambda *args: None,
            "_vendor_post": vendor, "installation_namespace": lambda value: "TP" + "B" * 16,
            "save_app_directory_alias": lambda *args: None,
            "httpx": SimpleNamespace(HTTPStatusError=HttpFailure),
        })
        self.assertEqual(sync(object())["status"], "synced")
        self.assertEqual(paths, ["/v1/app/origin/sync", "/v1/app/register"])

    def test_http_candidate_never_contacts_vendor(self):
        calls = []
        sync = load_sync({
            "Session": object, "central_app_entitled": lambda: True,
            "_domain_origin": lambda db, kind: "http://pending.example.org",
            "DomainType": SimpleNamespace(API="api"), "urlsplit": urlsplit, "_vendor_post": lambda *args: calls.append(args),
        })
        self.assertEqual(sync(object())["status"], "waiting_for_https")
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
