"""Regression tests for the read-only, deferred public connection QR path."""
from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from app.routers import account_delivery as ad
from app.routers.public_connection_qr_deferred_v1 import (
    defer_public_connection_qr,
    public_connection_qr_image,
)


class DeferredPublicConnectionQrTests(TestCase):
    def test_page_defers_sensitive_qr_without_changing_value(self):
        private_config = "[Interface]\nPrivateKey = private_test_only\n"
        with defer_public_connection_qr("customer-sample"):
            url = ad._qr_data_uri(private_config)
            self.assertIn("/v1/connect/customer-sample/qr-image?v=", url)
            self.assertNotIn("private_test_only", url)

            parsed = urlsplit(url)
            encrypted = parse_qs(parsed.query)["v"][0]
            self.assertEqual(
                ad._fernet().decrypt(encrypted.encode()).decode(),
                private_config,
            )

        # Other endpoints retain the established inline-PNG QR contract.
        direct = ad._qr_data_uri(private_config)
        self.assertTrue(direct.startswith("data:image/png;base64,"))
        self.assertTrue(
            base64.b64decode(direct.partition(",")[2]).startswith(
                b"\x89PNG\r\n\x1a\n"
            )
        )

    def test_endpoint_returns_real_png_only_for_active_share(self):
        with defer_public_connection_qr("customer-sample"):
            url = ad._qr_data_uri("vless://test@test.invalid:443?type=tcp")
        encrypted = parse_qs(urlsplit(url).query)["v"][0]
        with patch.object(
            ad,
            "_subscription_from_share_token",
            return_value=SimpleNamespace(status="active"),
        ):
            image = public_connection_qr_image("customer-sample", encrypted, object())
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.media_type, "image/png")
            self.assertEqual(image.headers["cache-control"], "private, no-store")
            self.assertTrue(image.body.startswith(b"\x89PNG\r\n\x1a\n"))

        with patch.object(
            ad,
            "_subscription_from_share_token",
            return_value=SimpleNamespace(status="suspended"),
        ):
            with self.assertRaises(HTTPException) as cm:
                public_connection_qr_image("customer-sample", encrypted, object())
            self.assertEqual(cm.exception.status_code, 404)

    def test_invalid_ciphertext_is_rejected(self):
        with patch.object(
            ad,
            "_subscription_from_share_token",
            return_value=SimpleNamespace(status="active"),
        ):
            with self.assertRaises(HTTPException) as cm:
                public_connection_qr_image("customer-sample", "not-a-valid-token", object())
            self.assertEqual(cm.exception.status_code, 404)
