"""Optional, fail-closed, DNS-independent HTTPS transport for Node Agents.

The controller operator provisions a dedicated TLS endpoint with an IP-address
SAN and a private certificate authority. Only its PUBLIC CA certificate is
embedded into rendered Agents; the signing and server private keys stay on
the controller. Without an opt-in config, existing domain-based installations
continue working unchanged.
"""
from __future__ import annotations

import ipaddress
import json
import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_CONFIG = Path("/etc/twinpanel/controller-ip/node-agent.json")
CONFIG_ENV = "TWINPANEL_AGENT_CONTROLLER_IP_CONFIG"


def resolve_agent_controller_connection(
    original_api_base: str,
    *,
    config_path: Path | None = None,
) -> tuple[str, str]:
    """Return (controller HTTPS URL, public CA PEM), or legacy URL with no pin.

    Fail closed when an opt-in configuration exists but is invalid. Falling
    back to filtered DNS in that case would quietly strand installed nodes.
    """
    path = (
        Path(config_path)
        if config_path is not None
        else Path(os.environ.get(CONFIG_ENV) or str(DEFAULT_CONFIG))
    )
    legacy = str(original_api_base or "").strip().rstrip("/")
    if not path.is_file():
        return legacy, ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        url = str(data["api_url"]).strip().rstrip("/")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or not parsed.hostname
            or parsed.port is None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("expected an HTTPS IP URL with an explicit port")
        ipaddress.ip_address(parsed.hostname)
        ca_path = Path(str(data["ca_cert_path"]))
        if not ca_path.is_absolute() or not ca_path.is_file():
            raise ValueError("controller CA file missing")
        ca_pem = ca_path.read_text(encoding="ascii")
        if "-----BEGIN CERTIFICATE-----" not in ca_pem:
            raise ValueError("controller CA PEM not found")
        # Validate the PEM before embedding it. Runtime Agent SSLContext trusts
        # ONLY this CA and requires normal HTTPS hostname/IP validation.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=ca_pem)
        return url, ca_pem
    except Exception as exc:
        raise RuntimeError(
            "node_agent_controller_ip_config_invalid"
        ) from exc
