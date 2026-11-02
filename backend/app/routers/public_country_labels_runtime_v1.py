from __future__ import annotations

import html
from typing import Any

from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..models import Node
from . import public_connection_hub_v5 as hub_v5
from . import public_connection_modern_names_v14 as modern_names_v14


_COUNTRY_LABELS_FA = {
    "DE": "آلمان",
    "NL": "هلند",
    "FR": "فرانسه",
    "GB": "بریتانیا",
    "UK": "بریتانیا",
    "US": "آمریکا",
    "CA": "کانادا",
    "FI": "فنلاند",
    "SE": "سوئد",
    "NO": "نروژ",
    "DK": "دانمارک",
    "CH": "سوئیس",
    "AT": "اتریش",
    "BE": "بلژیک",
    "PL": "لهستان",
    "CZ": "جمهوری چک",
    "RO": "رومانی",
    "BG": "بلغارستان",
    "HU": "مجارستان",
    "IT": "ایتالیا",
    "ES": "اسپانیا",
    "PT": "پرتغال",
    "GR": "یونان",
    "TR": "ترکیه",
    "AE": "امارات",
    "SG": "سنگاپور",
    "JP": "ژاپن",
    "KR": "کره جنوبی",
    "HK": "هنگ‌کنگ",
    "IN": "هند",
    "AU": "استرالیا",
    "IR": "ایران",
}

_ORIGINAL_HUB = hub_v5.public_connection_hub_v5
_ORIGINAL_MODERN_REFINER = modern_names_v14.refine_public_connection_modern_names_v14


def public_node_label(node: Node) -> str:
    # Only the mother/local-core node gets a customer-facing country label.
    # Normal Exit nodes must keep their configured node.name exactly as before.
    if not getattr(node, "is_mother", False):
        return str(getattr(node, "name", "") or f"Server {int(node.id)}").strip()

    code = str(getattr(node, "country_code", "") or "").strip().upper()
    if code in _COUNTRY_LABELS_FA:
        return _COUNTRY_LABELS_FA[code]
    if code and code not in {"XX", "CORE"}:
        return code
    return "سرور مرکزی"


def refine_public_country_labels(source: str, db: Session) -> str:
    """Replace only the mother node's customer-facing label; keep Exit names intact."""
    for node in db.query(Node).filter(Node.retired_at.is_(None)).all():
        old = html.escape(str(node.name or ""), quote=True)
        new = html.escape(public_node_label(node), quote=True)
        if not old or old == new:
            continue
        # Hub V5 server tabs.
        source = source.replace(f"<span>{old}</span></button>", f"<span>{new}</span></button>")
        # Legacy/compact server chips still used by some protocol refiners.
        source = source.replace(f"<i></i>{old}</button>", f"<i></i>{new}</button>")
        # Smart-connect server subtitle.
        source = source.replace(f"<p>{old} · آماده اتصال</p>", f"<p>{new} · آماده اتصال</p>")
        source = source.replace(f"<p>{old} · ready to connect</p>", f"<p>{new} · ready to connect</p>")
    return source


def public_connection_hub_country_labels(token: str, db: Session):
    base = _ORIGINAL_HUB(token, db)
    raw = base.body.decode("utf-8", errors="replace")
    source = refine_public_country_labels(raw, db)
    return HTMLResponse(
        content=source,
        status_code=base.status_code,
        headers={"Cache-Control": "no-store"},
    )


def refine_public_connection_modern_names_country_labels(
    source: str,
    token: str,
    db: Session,
) -> str:
    source = _ORIGINAL_MODERN_REFINER(source, token, db)
    return refine_public_country_labels(source, db)


def install_public_country_labels_runtime_v1() -> None:
    # public_connection_hub_live_v5 imports these symbols after routers package
    # initialization. Replace module attributes first so the live hub receives
    # the country-aware functions without changing route ordering.
    hub_v5.public_connection_hub_v5 = public_connection_hub_country_labels
    modern_names_v14.refine_public_connection_modern_names_v14 = (
        refine_public_connection_modern_names_country_labels
    )


install_public_country_labels_runtime_v1()
