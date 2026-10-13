from __future__ import annotations

from app.customer_wallet_models import CustomerWalletTopup
from app.main import app


def first_endpoint(path: str, method: str) -> str | None:
    wanted = method.upper()
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        methods = {
            str(value).upper()
            for value in (getattr(route, "methods", None) or set())
        }
        if wanted not in methods:
            continue
        endpoint = getattr(route, "endpoint", None)
        return str(getattr(endpoint, "__name__", "") or "")
    return None


def main() -> None:
    assert "receipt_file_marker" in CustomerWalletTopup.__table__.c

    expected = {
        ("/v1/wallet/topups/{topup_id}/receipt-upload", "POST"):
            "upload_wallet_topup_receipt",
        ("/v1/wallet/topups/{topup_id}/receipt-status", "GET"):
            "wallet_topup_receipt_status",
        ("/v1/admin/wallet/topups/{topup_id}/receipt", "GET"):
            "admin_wallet_topup_receipt",
    }

    for (path, method), endpoint_name in expected.items():
        actual = first_endpoint(path, method)
        assert actual == endpoint_name, (
            f"wallet receipt route mismatch {method} {path}: "
            f"expected={endpoint_name} actual={actual}"
        )

    print("WALLET_RECEIPT_ROUTES_OK")


if __name__ == "__main__":
    main()
