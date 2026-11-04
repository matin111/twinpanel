"""Idempotent fast backfill of desired protocol snapshots for eligible migrated users.

Does not provision runtime, modify live credentials, overwrite subscription
nodes, or expand non-imported subscriptions. Run after importing subscriptions.
Only ACTIVE, unexpired and quota-available imports are eligible. Zero traffic
limit is the established unlimited-plan representation.
"""
from __future__ import annotations

from sqlalchemy import text

from app.database import SessionLocal


SQL = text(
    """
    WITH eligible AS (
        SELECT DISTINCT s.id
        FROM subscriptions s
        JOIN migration_import_records m ON m.subscription_id = s.id
        WHERE m.source IN ('eylan', 'sanaei', 'marzban', 'pasargad')
          AND s.status = 'ACTIVE'
          AND (s.expires_at IS NULL OR s.expires_at > (now() AT TIME ZONE 'UTC'))
          AND (
              s.traffic_limit_bytes <= 0
              OR s.traffic_used_bytes < s.traffic_limit_bytes
          )
    ),
    desired(protocol) AS (
        VALUES ('cisco'), ('openvpn'), ('wireguard'), ('l2tp'), ('v2ray'),
               ('hysteria2'), ('tuic'), ('anytls'), ('naive'), ('shadowtls'),
               ('snell'), ('mieru'), ('trusttunnel'), ('amneziawg'), ('sudoku')
    ),
    inserted AS (
        INSERT INTO subscription_protocols(subscription_id, protocol, created_at)
        SELECT eligible.id, desired.protocol, (now() AT TIME ZONE 'UTC')
        FROM eligible CROSS JOIN desired
        ON CONFLICT (subscription_id, protocol) DO NOTHING
        RETURNING subscription_id
    )
    SELECT COUNT(*) AS added,
           COUNT(DISTINCT subscription_id) AS affected_subscriptions
    FROM inserted
    """
)


def main() -> None:
    with SessionLocal.begin() as db:
        result = db.execute(SQL).one()
        print(
            "MIGRATION_PROTOCOL_SNAPSHOTS_COMMITTED",
            {"new_rows": int(result.added), "subscriptions": int(result.affected_subscriptions)},
            flush=True,
        )


if __name__ == "__main__":
    main()
