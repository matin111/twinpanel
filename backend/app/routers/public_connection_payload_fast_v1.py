from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Subscription
from .account_delivery import _qr_data_uri, _share_url, _stored_info


# TWINPANEL_PUBLIC_CONNECT_PAYLOAD_FAST_V1
#
# Public Connection no longer renders the retired per-profile V2Ray QR inventory,
# so generating an SVG QR for every V2Ray/Xray profile before the first byte of
# HTML is wasted CPU on the single API worker. Keep WireGuard QR compatibility,
# because that file-oriented surface can still render its QR, but leave V2Ray QR
# generation to explicit/on-demand surfaces instead of the initial page request.
def public_connection_payload_fast_v1(
    db: Session,
    sub: Subscription,
) -> dict[str, Any]:
    info = _stored_info(db, sub)

    for cred in info.get("credentials", []):
        if not isinstance(cred, dict):
            continue
        if str(cred.get("protocol") or "").strip().lower() != "wireguard":
            continue
        for item in cred.get("items", []):
            if isinstance(item, dict) and item.get("config"):
                item["qr"] = _qr_data_uri(item["config"])

    info["subscription_link"] = _share_url(db, sub)
    info["expires_at"] = sub.expires_at.isoformat() if sub.expires_at else None
    info["traffic_limit_gb"] = round(
        (sub.traffic_limit_bytes or 0) / 1024 / 1024 / 1024,
        2,
    )
    return info
