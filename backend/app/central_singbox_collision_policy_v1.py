"""Deterministic new-Exit aliases for duplicate subscription-bound logins.

A duplicate Naive/ShadowTLS/SOCKS5 username must never abort the 7-protocol sing-box
bulk apply or overwrite another customer's live auth record. Existing mother
credentials and saved items on other nodes are never edited. Only the new
node's protocol-specific client record is assigned a stable alias.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from typing import Iterable

BOUND = frozenset({"naive", "shadowtls", "socks5"})


def resolve_node_login_collisions(
    work: list[tuple[int, str, object]],
    all_bound_logins: Iterable[tuple[int, str, str | None]],
) -> tuple[list[tuple[int, str, object]], int]:
    """A pure, idempotent transformation; no DB/SSH or identity rotation.

    Include inactive subscriptions in the supplied authority to keep alias
    selection stable when a duplicate subscription expires or renews.
    """
    owners: dict[tuple[str,str], set[int]] = defaultdict(set)
    reserved: dict[str,set[str]] = defaultdict(set)
    for sid,protocol,username in all_bound_logins:
        protocol=str(protocol or "").strip().lower()
        name=str(username or "").strip()
        if protocol not in BOUND or not name:
            continue
        if int(sid)<=0:
            raise RuntimeError("CENTRAL_SINGBOX_INVALID_SUBSCRIPTION_ID")
        key=name.casefold()
        owners[(protocol,key)].add(int(sid))
        reserved[protocol].add(key)

    # Include the work itself when a newly purchased account has not yet
    # appeared in the general subscription-protocol projection.
    for sid,protocol,secret in work:
        protocol=str(protocol).strip().lower()
        name=str(getattr(secret,"username","") or "").strip()
        if protocol in BOUND and name:
            owners[(protocol,name.casefold())].add(int(sid))
            reserved[protocol].add(name.casefold())

    changed=0
    output=[]
    assigned=set()
    for sid,protocol,secret in work:
        sid=int(sid)
        username=str(getattr(secret,"username","") or "").strip()
        if sid<=0 or not username:
            raise RuntimeError("CENTRAL_SINGBOX_INVALID_BOUND_IDENTITY")
        protocol=str(protocol).strip().lower()
        if protocol in BOUND and len(owners[(protocol,username.casefold())])>1:
            # Every member of the ambiguous group receives a stable alias;
            # never decide based on which account happens to be processed first.
            candidate=f"tp-central-{sid}-{protocol}"
            if candidate.casefold() in reserved[protocol]:
                digest=sha256(f"{sid}:{protocol}".encode()).hexdigest()[:12]
                candidate=f"tp-central-{sid}-{digest}-{protocol}"
            if candidate.casefold() in reserved[protocol]:
                raise RuntimeError("CENTRAL_SINGBOX_ALIAS_NAMESPACE_CONFLICT")
            secret=replace(secret,username=candidate)
            changed+=1
            username=candidate
        key=(protocol,username.casefold())
        if key in assigned:
            raise RuntimeError("CENTRAL_SINGBOX_DUPLICATE_NODE_IDENTITY")
        assigned.add(key)
        output.append((sid,protocol,secret))
    return output,changed
