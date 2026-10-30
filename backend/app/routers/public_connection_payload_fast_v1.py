from __future__ import annotations

from copy import deepcopy
import sys
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
#
# TWINPANEL_PUBLIC_CONNECT_REQUEST_PAYLOAD_CACHE_V2
# Hub V5 and the V13/V14/V15/V16 presentation refiners consume the same payload
# during one HTTP request. Rebuilding _stored_info() for every refiner repeats DB
# reads, decrypt/filter work and endpoint normalization several times. FastAPI's
# get_db() creates one SQLAlchemy Session per request, so Session.info is a safe
# request-local cache boundary: no payload is shared across requests or workers.
# Keep a deep-copied canonical value in the cache because presentation refiners
# are allowed to transform their local payload without contaminating later stages.
_CACHE_PREFIX = "twinpanel_public_connect_payload_fast_v2"


def public_connection_payload_fast_v1(
    db: Session,
    sub: Subscription,
) -> dict[str, Any]:
    cache_key = (_CACHE_PREFIX, int(sub.id))
    cached = db.info.get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

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

    # Cache an isolated canonical copy. The first caller receives the freshly
    # built object, while later presentation stages receive their own deep copy.
    db.info[cache_key] = deepcopy(info)
    return info


# The active Public Connect page composes V13/V14/V15/V16 refiners after Hub V5.
# Those modules historically imported account_delivery._public_payload directly,
# causing four extra eager V2Ray/Xray QR-generation passes after the Hub payload
# had already been made lightweight. Rebind only the already-loaded presentation
# modules to this read-only payload. Their config/download paths consume the same
# credentials/items and do not depend on the omitted legacy V2Ray QR field.
def install_public_connection_fast_payload_refiners_v1() -> None:
    module_names = (
        "app.routers.public_connection_modern_delivery_v13",
        "app.routers.public_connection_modern_names_v14",
        "app.routers.public_connection_modern_import_v15",
        "app.routers.public_connection_modern_delivery_v16",
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "_public_payload"):
            module._public_payload = public_connection_payload_fast_v1


install_public_connection_fast_payload_refiners_v1()
