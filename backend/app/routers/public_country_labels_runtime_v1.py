from __future__ import annotations

import html
from typing import Any

from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..models import Node
from . import public_connection_hub_v5 as hub_v5
from . import public_connection_modern_names_v14 as modern_names_v14


_ORIGINAL_HUB = hub_v5.public_connection_hub_v5
_ORIGINAL_MODERN_REFINER = modern_names_v14.refine_public_connection_modern_names_v14


def public_node_label(node: Node) -> str:
    """Use the configured Node name for every customer-facing server label.

    Mother/Local Core is editable from Mother settings, so the public page must
    never replace its configured name with a hardcoded country or "Central"
    label. Normal Exit nodes keep their configured names exactly as before.
    """
    return str(getattr(node, "name", "") or f"Server {int(node.id)}").strip()


def refine_public_country_labels(source: str, db: Session) -> str:
    """Keep rendered server labels synchronized with the configured Node names."""
    for node in db.query(Node).filter(Node.retired_at.is_(None)).all():
        old = html.escape(str(node.name or ""), quote=True)
        new = html.escape(public_node_label(node), quote=True)
        if not old or old == new:
            continue
        source = source.replace(f"<span>{old}</span></button>", f"<span>{new}</span></button>")
        source = source.replace(f"<i></i>{old}</button>", f"<i></i>{new}</button>")
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
    hub_v5.public_connection_hub_v5 = public_connection_hub_country_labels
    modern_names_v14.refine_public_connection_modern_names_v14 = (
        refine_public_connection_modern_names_country_labels
    )


install_public_country_labels_runtime_v1()
