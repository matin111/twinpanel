from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import (
    Node,
    NodeType,
    SubscriptionNode,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[2]
)

BOOTSTRAP = (
    PROJECT_ROOT / "quota_bootstrap_v1.py"
)

PYTHON = (
    PROJECT_ROOT / "venv" / "bin" / "python"
)


async def sync_subscription_quota_nodes(
    db: Session,
    subscription_id: int,
    extra_node_ids=None,
):
    """
    Refresh quota-agent config only on Exit nodes
    related to one subscription.

    extra_node_ids is used for removed Exit nodes so
    stale devices are removed from their config too.
    """

    rows = (
        db.query(Node.id)
        .join(
            SubscriptionNode,
            SubscriptionNode.node_id == Node.id,
        )
        .filter(
            SubscriptionNode.subscription_id
            == int(subscription_id),
            Node.node_type == NodeType.EXIT,
        )
        .all()
    )

    node_ids = {
        int(row[0])
        for row in rows
    }

    for value in (extra_node_ids or []):
        try:
            node_ids.add(int(value))
        except Exception:
            pass

    results = []

    for node_id in sorted(node_ids):

        node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()

        if (
            node is None
            or node.node_type != NodeType.EXIT
        ):
            continue

        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                [
                    str(PYTHON),
                    str(BOOTSTRAP),
                    str(node_id),
                ],
                cwd=str(PROJECT_ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=300,
                check=False,
            )

            output = (
                proc.stdout or ""
            )[-3000:]

            results.append({
                "node_id": node_id,
                "node_name": node.name,
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "output": output,
            })

        except Exception as exc:
            results.append({
                "node_id": node_id,
                "node_name": node.name,
                "ok": False,
                "error": str(exc)[:500],
            })

    return {
        "ok": all(
            item.get("ok")
            for item in results
        ) if results else True,

        "subscription_id":
            int(subscription_id),

        "nodes":
            results,
    }
