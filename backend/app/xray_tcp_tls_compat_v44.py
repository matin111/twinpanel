from __future__ import annotations

from . import xray_tcp_tls_v39


# TWINPANEL_XRAY_TCP_TLS_COMPAT_V44
#
# Xray 26.3.x determines the candidate config format from the filename
# extension. V39 wrote the temporary file as:
#   /usr/local/etc/xray/config.json.tcp-tls-v39
# so `xray run -test -config ...` rejected it with:
#   Failed to get format of ...config.json.tcp-tls-v39
#
# Keep the proven V39 builder unchanged and patch only the temporary candidate
# path so it ends with `.json`. The final production config path, listener port,
# UUIDs, certificate/key, and rollback behavior remain unchanged.

_runtime_applied = False
_original_tcp_tls_config_script = None


def _tcp_tls_config_script_v44(
    *,
    port: int,
    domain: str,
    cert: str,
    key: str,
) -> str:
    assert _original_tcp_tls_config_script is not None

    script = _original_tcp_tls_config_script(
        port=port,
        domain=domain,
        cert=cert,
        key=key,
    )

    old = 'Path("/usr/local/etc/xray/config.json.tcp-tls-v39")'
    new = 'Path("/usr/local/etc/xray/config.tcp-tls-v44.json")'

    if old not in script:
        raise RuntimeError("V44 cannot locate the V39 TCP TLS candidate path")

    return script.replace(old, new, 1)


def apply_xray_tcp_tls_compat_v44() -> None:
    global _runtime_applied
    global _original_tcp_tls_config_script

    if _runtime_applied:
        return

    _original_tcp_tls_config_script = xray_tcp_tls_v39._tcp_tls_config_script
    xray_tcp_tls_v39._tcp_tls_config_script = _tcp_tls_config_script_v44

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_TCP_TLS_COMPAT_V44_ACTIVE "
        "candidate_json_extension=1 "
        "xray_26_3_compatible=1 "
        "ports_unchanged=1 uuid_preserved=1",
        flush=True,
    )
