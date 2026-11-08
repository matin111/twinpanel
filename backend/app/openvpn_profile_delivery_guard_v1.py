"""OpenVPN customer download invariant and same-country filename disambiguation.

The OpenVPN Connect app rejects a malformed .ovpn with the error
"option_error: remote option not specified". Never ship such content under
an .ovpn name, including legacy routes, ZIPs and browser-native sharing.

The profile, client certificate, and keys are read-only. Only the HTTP
attachment's public filename is disambiguated for duplicate country names.
"""
from __future__ import annotations

from collections import Counter
import re
from typing import Any

_REMOTE = re.compile(
    r"^remote[ \t]+(\S+)[ \t]+([0-9]{1,5})"
    r"(?:[ \t]+(?:udp|udp4|udp6|tcp|tcp-client|tcp4-client|tcp6-client))?[ \t]*$",
    re.IGNORECASE,
)
_PROTO = re.compile(
    r"^proto[ \t]+(udp|udp4|udp6|tcp-client|tcp4-client|tcp6-client)[ \t]*$",
    re.IGNORECASE,
)
_FORBIDDEN_HOSTS = frozenset({
    "0.0.0.0", "::", "[::]", "127.0.0.1", "localhost",
    "none", "null", "undefined", "nan", "false", "true", "—",
})


def validate_openvpn_profile(config: Any) -> None:
    """Raise a stable nonsecret error code on invalid delivery bytes.

    Does not rely on the filename, saved port, or browser JS. Only a real
    remote hostname port line is accepted, not a comment or HTML.
    """
    if not isinstance(config, str) or not config.strip():
        raise ValueError("OPENVPN_PROFILE_EMPTY")
    if not any(line.strip().lower()=="client" for line in config.splitlines()):
        raise ValueError("OPENVPN_PROFILE_CLIENT_MISSING")
    proto = [line.strip() for line in config.splitlines()
             if line.lstrip().lower().startswith("proto ")]
    if not proto or not all(_PROTO.fullmatch(line) for line in proto):
        raise ValueError("OPENVPN_PROFILE_PROTO_INVALID")
    remote_lines = [
        line.strip() for line in config.splitlines()
        if line.lstrip().lower().startswith("remote ")
        or line.strip().lower()=="remote"
    ]
    if not remote_lines:
        raise ValueError("OPENVPN_PROFILE_REMOTE_MISSING")
    for line in remote_lines:
        matched = _REMOTE.fullmatch(line)
        if not matched:
            raise ValueError("OPENVPN_PROFILE_REMOTE_INVALID")
        host, port = matched.groups()
        if (host.lower() in _FORBIDDEN_HOSTS
                or any(c in host for c in '<>"\\')
                or not 1 <= int(port) <= 65535):
            raise ValueError("OPENVPN_PROFILE_REMOTE_INVALID")
    if "<html" in config.lower() or "<!doctype html" in config.lower():
        raise ValueError("OPENVPN_PROFILE_HTML_NOT_CONFIG")


def disambiguate_openvpn_filenames(payload: dict[str, Any]) -> dict[str, Any]:
    """Mutate a request-local payload only, never DB/PKI or stored credentials.

    Multiple Exits in the same country can create identical filenames.
    Phone file managers may import an older same-named file on new imports.
    """
    credentials = payload.get("credentials")
    if not isinstance(credentials, list):
        return payload
    for cred in credentials:
        if not isinstance(cred, dict) or str(cred.get("protocol") or "").lower()!="openvpn":
            continue
        items = cred.get("items")
        if not isinstance(items, list):
            continue
        filenames = []
        for index,item in enumerate(items):
            raw = str(item.get("filename") or f"openvpn-{index+1}.ovpn") if isinstance(item,dict) else f"openvpn-{index+1}.ovpn"
            filenames.append(raw)
        duplicate_counts = Counter(filename.casefold() for filename in filenames)
        used: set[str] = set()
        for index,item in enumerate(items):
            if not isinstance(item,dict):
                continue
            filename = filenames[index]
            if duplicate_counts[filename.casefold()]<=1:
                used.add(filename.casefold())
                continue
            base,ext = (filename.rsplit(".",1) if "." in filename else (filename,"ovpn"))
            try:
                node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                node_id = 0
            node_suffix = f"-n{node_id}" if node_id>0 else f"-profile{index+1}"
            variant = f"{base}{node_suffix}.{ext}"
            if variant.casefold() in used:
                mode = str(item.get("delivery_mode") or "").strip().lower()
                variant = f"{base}{node_suffix}-{mode or index+1}.{ext}"
            if variant.casefold() in used:
                variant = f"{base}{node_suffix}-profile{index+1}.{ext}"
            item["filename"] = variant
            used.add(variant.casefold())
    return payload
