from __future__ import annotations

BADVPN_REPOSITORY = "https://github.com/ambrop72/badvpn.git"
BADVPN_COMMIT = "07268f02706e78e282e19641b5d1d41e8e89bf31"
NETMOD_UDPGW_PORT = 7300
NETMOD_UDPGW_LISTEN = "127.0.0.1:7300"
NETMOD_UDPGW_SERVICE = "twinpanel-netmod-udpgw.service"
NETMOD_UDPGW_BINARY = "/usr/local/bin/twinpanel-netmod-udpgw"
NETMOD_SSH_SERVICE = "twinpanel-netmod-ssh.service"
NETMOD_SSH_DROPIN_DIR = f"/etc/systemd/system/{NETMOD_SSH_SERVICE}.d"
NETMOD_SSH_UDPGW_DROPIN = f"{NETMOD_SSH_DROPIN_DIR}/20-udpgw.conf"
NETMOD_DNSTT_PERFORMANCE_DROPIN = "/etc/systemd/system/twinpanel-netmod-dnstt.service.d/10-performance.conf"
NETMOD_DNSTT_SAFE_MTU = 1232


def udpgw_health_shell() -> str:
    return (
        f"udpgw_service=$(systemctl is-active {NETMOD_UDPGW_SERVICE} 2>/dev/null || true)\n"
        "udpgw_listener=no\n"
        f"ss -H -ltnp 2>/dev/null | grep -F '{NETMOD_UDPGW_LISTEN} ' >/dev/null 2>&1 && udpgw_listener=yes || true\n"
        "printf 'UDPGW_SERVICE=%s\\n' \"$udpgw_service\"\n"
        "printf 'UDPGW_LISTENER=%s\\n' \"$udpgw_listener\"\n"
    )
