"""Regression: sing-box node enumeration must not hold a transaction over SSH."""
from __future__ import annotations

import inspect
from app.services.singbox_native_accounting_v265 import reconcile_singbox_quota_once


def main() -> None:
    source = inspect.getsource(reconcile_singbox_quota_once)
    enumeration = source.index(".order_by(Node.id.asc())")
    boundary = source.index("db.commit()", enumeration)
    iteration = source.index("for node in nodes:", enumeration)
    network = source.index("await connect_protocol_runtime", iteration)
    assert enumeration < boundary < iteration < network
    # SQLAlchemy rollback expires mapped attributes even when
    # expire_on_commit=False; commit keeps loaded Node instances available.
    assert "db.rollback()" not in source[enumeration:iteration]
    print("PASS: node enumeration transaction closed before network I/O")


if __name__ == "__main__":
    main()
