"""Regression safeguards for the public Connection fast-render contract.

No live credentials, network, database or third-party services are used.
Run: python3 -m unittest discover -s backend/tests -p test_connection_render_fast_v103.py -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def get(rel: str) -> str:
    path = APP / rel
    code = path.read_text(encoding="utf-8")
    compile(code, str(path), "exec")
    return code


class ConnectionFastRender(unittest.TestCase):
    def test_only_this_request_memoizes_public_credentials(self):
        p = get("routers/public_connection_payload_fast_v1.py")
        self.assertIn('db.info["_tp_public_connect_node_refs_v102"]', p)
        self.assertIn('db.info.setdefault("_tp_public_delivery_tunnels", {})', p)
        self.assertIn('db.info["_tp_public_connection_cfg_cache_v102"]', p)
        self.assertIn('db.info["_tp_public_connection_cfg_prefetched_v103"] = True', p)
        self.assertIn("NodeProtocolConfig.node_id.in_(ids)", p)
        self.assertNotIn("@lru_cache", p)

    def test_node_readiness_cache_is_opt_in_not_global(self):
        a = get("routers/account_delivery.py")
        m = get("mother_subscription_delivery_policy_v108.py")
        self.assertIn('cache = info.get("_tp_public_connection_cfg_cache_v102")', a)
        self.assertIn('info = getattr(db, "info", {})', a)
        self.assertIn('info.get("_tp_public_connection_cfg_prefetched_v103")', a)
        self.assertIn('getattr(db, "info", {}).get("_tp_public_connection_cfg_prefetched_v103")', m)
        self.assertIn('def _modern_direct_item_is_usable_uncached(', m)
        self.assertIn('getattr(db, "info", {}).get("_tp_public_connection_item_cache_v102")', m)
        self.assertIn("return _modern_direct_item_is_usable_uncached(db, protocol, item)", m)

    def test_qr_png_remains_scannable_and_keeps_original_data(self):
        code = get("routers/account_delivery.py")
        self.assertIn("image_factory=qrcode.image.pil.PilImage", code)
        self.assertIn('return "data:image/png;base64,"', code)
        self.assertIn('image.save(out, format="PNG")', code)
        self.assertIn("value,", code)
        self.assertNotIn("mask_pattern=0", code)
        try:
            from PIL import Image
            from app.routers.account_delivery import _qr_data_uri
        except ImportError:
            return
        import base64
        import io
        data = _qr_data_uri("vless://sample@example.org:443?type=tcp#test")
        self.assertTrue(data.startswith("data:image/png;base64,"))
        payload = base64.b64decode(data.split(",", 1)[1])
        with Image.open(io.BytesIO(payload)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 80)
            image.verify()

    def test_quota_and_live_numbers_stay_dynamic(self):
        fast = get("routers/public_connection_payload_fast_v1.py")
        hub = get("routers/public_connection_hub_live_v5.py")
        self.assertNotIn("functools.lru_cache", fast)
        self.assertIn("_public_connection_hub_v5_module._public_payload", hub)
        self.assertIn('headers={"Cache-Control": "no-store"}', hub)
        self.assertIn('const response=await fetch(endpoint', hub)


if __name__ == "__main__":
    unittest.main()
