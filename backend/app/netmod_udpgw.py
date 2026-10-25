from __future__ import annotations

NETMOD_UDPGW_PORT = 7300
NETMOD_UDPGW_LISTEN = "127.0.0.1:7300"
NETMOD_UDPGW_SERVICE = "twinpanel-netmod-udpgw.service"
NETMOD_UDPGW_BINARY = "/usr/local/bin/twinpanel-netmod-udpgw"


def udpgw_health_shell() -> str:
    return (
        "udpgw_service=$(systemctl is-active twinpanel-netmod-udpgw.service 2>/dev/null || true)\n"
        "udpgw_listener=no\n"
        "ss -H -ltnp 2>/dev/null | grep -F '127.0.0.1:7300 ' >/dev/null 2>&1 && udpgw_listener=yes || true\n"
        "printf 'UDPGW_SERVICE=%s\\n' \"$udpgw_service\"\n"
        "printf 'UDPGW_LISTENER=%s\\n' \"$udpgw_listener\"\n"
    )
