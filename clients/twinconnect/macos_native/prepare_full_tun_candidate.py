#!/usr/bin/env python3
"""Offline conversion of an entitled sing-box local proxy into a TUN candidate.

Never starts the engine, requests privileges or changes system networking.
Output is for an independently installed, root-owned local-console helper;
do not run the candidate on a remote VPS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ALLOWED = {"hysteria2", "tuic", "anytls", "socks", "socks5", "snell",
           "naive", "shadowtls", "shadowsocks", "vless", "vmess", "trojan"}
MAX_BYTES = 256 * 1024


def convert(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("CONFIG_NOT_OBJECT")
    current = profile.get("inbounds")
    if not isinstance(current, list) or len(current) != 1:
        raise ValueError("EXACTLY_ONE_LOCAL_INBOUND_REQUIRED")
    inbound = current[0]
    if not isinstance(inbound, dict) or inbound.get("type") not in (
        "mixed", "socks", "http"):
        raise ValueError("LOCAL_PROXY_INBOUND_REQUIRED")
    if inbound.get("listen") not in ("127.0.0.1", "::1"):
        raise ValueError("LOOPBACK_PROXY_REQUIRED")
    outbounds = profile.get("outbounds")
    route = profile.get("route")
    if not isinstance(outbounds, list) or not isinstance(route, dict):
        raise ValueError("REVIEWED_PROXY_ROUTE_REQUIRED")
    final = route.get("final")
    target = [o for o in outbounds if isinstance(o, dict) and o.get("tag") == final]
    if len(target) != 1 or target[0].get("type") not in ALLOWED:
        raise ValueError("ALLOWED_REMOTE_OUTBOUND_REQUIRED")
    if "rules" in route or "rule_set" in route or "auto_detect_interface" in route:
        raise ValueError("UNREVIEWED_ROUTING_RULES")
    if profile.get("experimental") or profile.get("ntp"):
        raise ValueError("UNREVIEWED_EXPERIMENTAL_OPTIONS")
    # Avoid writing a candidate with unverified DNS semantics; DNS leak
    # prevention will require dedicated configuration and live testing.
    if profile.get("dns"):
        raise ValueError("DNS_POLICY_REVIEW_REQUIRED")
    candidate = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "tun", "tag": "twinconnect-tun",
            # macOS allocates utunN; a custom interface name is invalid.
            "address": ["172.19.0.1/30"],
            "auto_route": True,
            "auto_redirect": False,
            "strict_route": False,
            "stack": "system"
        }],
        "outbounds": outbounds,
        "route": {"final": final, "auto_detect_interface": True}
    }
    # Fail closed on accidental direct fallback and mismatched route.
    from unsigned_tun_policy import validate_full_tun_config
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        f = Path(folder) / "candidate.json"
        f.write_text(json.dumps(candidate), encoding="utf-8")
        validate_full_tun_config(f)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if (args.source.is_symlink() or not args.source.is_file()
                or args.source.stat().st_size > MAX_BYTES):
            raise ValueError("UNTRUSTED_SOURCE")
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("OUTPUT_ALREADY_EXISTS")
        if not args.output.parent.is_dir() or args.output.parent.is_symlink():
            raise ValueError("OUTPUT_PARENT_INVALID")
        data = convert(json.loads(args.source.read_text(encoding="utf-8")))
        payload = json.dumps(data, indent=2).encode("utf-8")
        # Write using exclusive creation and owner-private permissions.
        import os
        fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(payload)
        except BaseException:
            args.output.unlink(missing_ok=True)
            raise
        print("TUN_CANDIDATE_CREATED_OFFLINE; NOT CONNECTED; NO_ROUTES_CHANGED")
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        code = str(exc)
        print(code if code.isupper() and len(code) < 80 else
              "TUN_CANDIDATE_REJECTED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())