"""Idempotent, non-destructive sing-box identity staging on central Exits.

When a stale account with the same login but different credentials already
exists on a node, preserve that account and install the desired credential
under a deterministic node-only alias. Never overwrite or rotate the existing
record. This is a pure transformation of in-memory work items only.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from hashlib import sha256
from typing import Any

from ..modern_protocol_runtime_v2 import SINGBOX_PROTOCOLS
from ..singbox_subscription_accounts import _user_record


def _alias(node_id: int, subscription_id: int, protocol: str, secret: Any) -> str:
    if int(node_id) <= 0 or int(subscription_id) <= 0:
        raise ValueError("CENTRAL_SINGBOX_INVALID_ALIAS_SCOPE")
    # A rotated canonical credential must never collide with an old alias.
    fingerprint = sha256(
        (str(node_id) + ":" + str(subscription_id) + ":" + protocol + ":" +
         str(secret.password) + ":" + str(secret.uuid or "") + ":" +
         str(secret.userkey or "")).encode("utf-8")
    ).hexdigest()[:12]
    result = f"tp-central-{subscription_id}-{protocol}-{node_id}-{fingerprint}"
    if len(result) > 128:
        raise RuntimeError("CENTRAL_SINGBOX_ALIAS_TOO_LONG")
    return result


def resolve_remote_identity_collisions(
    work: list[tuple[int, str, Any]],
    inbound_users: dict[str, list[dict[str, Any]]],
    node_id: int,
) -> tuple[list[tuple[int, str, Any]], dict[str, int]]:
    """Return a stable staged set without modifying remote users or secrets."""
    if not set(inbound_users).issuperset({protocol for _, protocol, _ in work}):
        raise RuntimeError("CENTRAL_SINGBOX_REMOTE_SNAPSHOT_INCOMPLETE")

    installed: dict[str, dict[str, dict[str, Any]]] = {}
    for protocol, rows in inbound_users.items():
        if protocol not in SINGBOX_PROTOCOLS or not isinstance(rows, list):
            raise RuntimeError("CENTRAL_SINGBOX_REMOTE_SNAPSHOT_INVALID")
        key = "username" if protocol in {"naive", "socks5"} else "name"
        entries: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise RuntimeError("CENTRAL_SINGBOX_REMOTE_USER_INVALID")
            username = row.get(key)
            if not isinstance(username, str) or not username:
                raise RuntimeError("CENTRAL_SINGBOX_REMOTE_USER_INVALID")
            if username in entries:
                raise RuntimeError("CENTRAL_SINGBOX_REMOTE_DUPLICATE_USER")
            entries[username] = row
        installed[protocol] = entries

    output: list[tuple[int, str, Any]] = []
    count = Counter()
    assigned = set()
    for subscription_id, protocol, secret in work:
        if protocol not in SINGBOX_PROTOCOLS:
            raise RuntimeError("CENTRAL_SINGBOX_PROTOCOL_INVALID")
        username = str(secret.username or "")
        expected = _user_record(secret)
        current = installed[protocol].get(username)
        if current is not None and current != expected:
            alias = _alias(node_id, subscription_id, protocol, secret)
            secret = replace(secret, username=alias)
            username = alias
            expected = _user_record(secret)
            existing_alias = installed[protocol].get(alias)
            if existing_alias is not None and existing_alias != expected:
                raise RuntimeError("CENTRAL_SINGBOX_NODE_ALIAS_CONFLICT")
            count["alias_on_conflict"] += 1
        elif current == expected:
            count["reused_identical"] += 1
        else:
            count["new_identity"] += 1

        pair = (protocol, username)
        if pair in assigned:
            raise RuntimeError("CENTRAL_SINGBOX_DUPLICATE_STAGED_USER")
        assigned.add(pair)
        output.append((int(subscription_id), protocol, secret))

    return output, dict(count)
