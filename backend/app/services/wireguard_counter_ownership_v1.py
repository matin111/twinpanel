"""Non-invasive, fail-closed WireGuard/AWG telemetry attribution.

Use only authenticated live public-key and cumulative counter observations.
Do not infer usage from addresses when two subscriptions share that address.
This module does not touch credentials, quota cursors, peers or VPN processes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


def select_proven_peer_devices(
    devices: list[dict[str, Any]],
    peers: list[dict[str, Any]],
    *,
    protocol: str,
    match_address: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    match_public_key: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    load_stored_public_key: Callable[[int], str | None] | None = None,
    cursor_owners: dict[str, Any] | None = None,
    counter_epoch: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Choose only sources that have one proven device owner across the node.

    For collided WG addresses, an independently persisted node-specific public
    key can resolve ownership without changing customer configs. If the key
    cannot be proven against the LIVE runtime, that device is not billed.
    """
    if protocol not in ("wireguard", "amneziawg"):
        raise ValueError("UNSUPPORTED_PEER_PROTOCOL")
    counters = {
        "original_ambiguous_sources": 0,
        "original_ambiguous_devices": 0,
        "verified_key_candidates": 0,
        "verified_key_recovered": 0,
        "unproven_identity_skipped": 0,
        "shared_peer_skipped": 0,
        "cursor_owner_conflict_skipped": 0,
        "counter_regression_skipped": 0,
        "safe_devices": 0,
    }
    observed = []
    source_owners: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for device in devices:
        identity = str(device.get("telemetry_identity") or device.get("identity") or "").strip()
        peer = (
            match_public_key(peers, identity) if protocol == "amneziawg"
            else match_address(peers, identity)
        ) if identity else None
        key = str(peer.get("public_key") or "").strip() if peer else ""
        source = (f"{protocol}:{key}"[:220] if key else None)
        owner = (int(device["subscription_id"]), int(device["device_id"]))
        if source:
            source_owners[source].add(owner)
        observed.append((device, source, peer))
    ambiguous = {key for key, users in source_owners.items() if len(users) > 1}
    counters["original_ambiguous_sources"] = len(ambiguous)
    counters["original_ambiguous_devices"] = sum(
        1 for _, source, _ in observed if source in ambiguous
    )
    staged: list[tuple[dict[str, Any], str | None, dict[str, Any] | None]] = []
    for device, source, peer in observed:
        if source in ambiguous:
            # A repeated address alone is NOT proof of who owns peer bytes.
            if protocol != "wireguard" or load_stored_public_key is None:
                counters["unproven_identity_skipped"] += 1
                continue
            try:
                stored = load_stored_public_key(int(device["subscription_id"]))
            except (Exception):
                # Corrupt/missing encrypted identity must never charge a peer.
                stored = None
            verified = (
                match_public_key(peers, stored)
                if isinstance(stored, str) and stored else None
            )
            verified_key = str(verified.get("public_key") or "").strip() if verified else ""
            if not verified_key or stored != verified_key:
                counters["unproven_identity_skipped"] += 1
                continue
            replacement = dict(device)
            replacement["verified_runtime_public_key"] = verified_key
            source = f"wireguard:{verified_key}"[:220]
            peer = verified
            device = replacement
            counters["verified_key_candidates"] += 1
        staged.append((device, source, peer))

    final_owners: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for device, source, _ in staged:
        if source:
            final_owners[source].add((
                int(device["subscription_id"]), int(device["device_id"])
            ))
    shared = {key for key, owners in final_owners.items() if len(owners) > 1}
    safe: list[dict[str, Any]] = []
    for device, source, peer in staged:
        if source in shared:
            counters["shared_peer_skipped"] += 1
            continue
        # Never continue with a cursor that was already bound to somebody else.
        # This prevents expensive failing 64-device batch retries and forbids
        # changing historical accounting ownership without an explicit repair.
        cursor = (cursor_owners or {}).get(source) if source else None
        if cursor is not None:
            old_owner = (
                int(cursor["subscription_id"]), int(cursor["device_id"])
            )
            new_owner = (
                int(device["subscription_id"]), int(device["device_id"])
            )
            if (old_owner != new_owner
                    or str(cursor.get("protocol")) != protocol):
                counters["cursor_owner_conflict_skipped"] += 1
                continue
            # Same-epoch cumulative decreases have no reliable restart proof.
            # Never charge a reset as new traffic or move the baseline blindly.
            if (counter_epoch is not None
                    and cursor.get("counter_epoch") == counter_epoch
                    and peer is not None
                    and (int(peer.get("rx") or 0) < int(cursor["last_uplink_value"])
                         or int(peer.get("tx") or 0) < int(cursor["last_downlink_value"]))):
                counters["counter_regression_skipped"] += 1
                continue
        safe.append(device)
        if device.get("verified_runtime_public_key"):
            counters["verified_key_recovered"] += 1
    counters["safe_devices"] = len(safe)
    return safe, counters
