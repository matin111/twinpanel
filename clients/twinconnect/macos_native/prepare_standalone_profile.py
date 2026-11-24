#!/usr/bin/env python3
"""Produce a private loopback-only test profile from an existing client JSON.

No server address, transport, TLS settings or credentials are changed.
Input is never overwritten, logged or uploaded. Route/DNS/TUN configuration
is intentionally discarded for this separate, per-request proxy test.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import uuid

from standalone_connection_manager import SINGBOX, STATE, validate

# ShadowTLS is normally used as a transport for a Shadowsocks outbound.
EXPECTED = {"socks5": "socks", "shadowtls": "shadowtls"}


def prepare(protocol: str, source: Path, port: int = 10808) -> dict:
    if protocol != "v2ray" and protocol not in SINGBOX:
        raise ValueError("PROTOCOL_NOT_SUPPORTED_BY_LOCAL_PROXY_PREPARE")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("INVALID_LOCAL_PROXY_PORT")
    if source.is_symlink() or not source.is_file():
        raise ValueError("INPUT_MUST_BE_REGULAR_FILE")
    if source.stat().st_size > 262144:
        raise ValueError("CONFIG_TOO_LARGE")
    try:
        config = json.loads(source.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("CONFIG_INVALID_JSON")
    if not isinstance(config, dict) or not isinstance(config.get("outbounds"), list):
        raise ValueError("OUTBOUNDS_REQUIRED")
    outbounds = config["outbounds"]
    if not outbounds or not all(isinstance(o, dict) for o in outbounds):
        raise ValueError("OUTBOUNDS_INVALID")
    key = "protocol" if protocol == "v2ray" else "type"
    accepted = {"vless", "vmess", "trojan", "shadowsocks"} if protocol == "v2ray" else {EXPECTED.get(protocol, protocol)}
    matches = [o for o in outbounds if o.get(key) in accepted]
    if not matches:
        raise ValueError("PROTOCOL_OUTBOUND_MISSING")
    # For ShadowTLS the client-facing Shadowsocks outbound must detour
    # via the authenticated ShadowTLS transport, not bypass it.
    if protocol == "shadowtls":
        transports = {o.get("tag") for o in matches}
        primary = next((o for o in outbounds
                        if o.get("type") == "shadowsocks"
                        and o.get("detour") in transports), None)
        if primary is None:
            raise ValueError("SHADOWTLS_AUTHENTICATED_CHAIN_MISSING")
    else:
        primary = matches[0]
    # Strictly require an explicit tag for sing-box route selection.
    if protocol != "v2ray":
        target = primary.get("tag")
        if not isinstance(target, str) or not target or len(target) > 128:
            raise ValueError("OUTBOUND_TAG_REQUIRED")
        tags = [o.get("tag") for o in outbounds]
        if len(set(tags)) != len(tags):
            raise ValueError("OUTBOUND_TAGS_NOT_UNIQUE")
        # Keep the full outgoing chain (detour references may depend on it),
        # but do not keep routes, DNS rewrites or old TUN inbounds.
        cleaned = {
            "inbounds": [{"type": "mixed", "tag": "local-proxy",
                          "listen": "127.0.0.1", "listen_port": port}],
            "outbounds": outbounds,
            "route": {"final": target},
        }
    else:
        # Xray uses the first outbound when no routing rules are configured.
        ordered = [primary] + [o for o in outbounds if o is not primary]
        cleaned = {
            "inbounds": [{"listen": "127.0.0.1", "port": port,
                          "protocol": "socks", "settings": {"udp": False}}],
            "outbounds": ordered,
        }

    configs = STATE / "prepared"
    configs.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(configs, 0o700)
    output = configs / (uuid.uuid4().hex + ".json")
    data = (json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n").encode()
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        validate(protocol, output)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {"state": "prepared", "protocol": protocol,
            "path": str(output), "listen_port": port,
            "mode": "local_proxy_only", "source_unchanged": True,
            "credentials_redacted_from_output": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", choices=["v2ray", *sorted(SINGBOX)])
    parser.add_argument("source", type=Path)
    parser.add_argument("--port", type=int, default=10808)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.protocol, args.source, args.port),
                         ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"state": "error", "reason": str(exc)}),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
