from __future__ import annotations

import base64
import ipaddress
import shlex


def install_masterdnsvpn_port53_v221_hooks() -> None:
    """Narrow rc.221 compatibility hook for MasterDnsVPN Direct Exit.

    Root cause addressed here:
    - rc.220 treated wildcard UDP/53 listeners (for example dnsmasq on 0.0.0.0:53)
      as an unconditional conflict even when MasterDnsVPN can bind the Exit's exact
      public IP safely.
    - a previous failed/manual MasterDnsVPN process using TwinPanel's own binary and
      config can remain outside systemd ownership and make Repair fail forever.

    This hook keeps unrelated DNS services untouched. It only terminates a stale
    process when /proc proves both the executable path and config path are exactly
    TwinPanel's MasterDnsVPN runtime. Exact-IP foreign listeners still fail closed.
    """

    from .routers import dns_emergency_masterdnsvpn as target

    def _install_script_v221(
        *,
        node,
        domain: str,
        protocol_type: str,
        forward_ip: str | None,
        forward_port: int | None,
        encryption_method: int,
    ) -> str:
        public_ip = str(ipaddress.ip_address(str(node.public_ip)))
        listen_addr = target._listen_addr(public_ip)
        config = target._server_config(
            public_ip=public_ip,
            domain=domain,
            protocol_type=protocol_type,
            forward_ip=forward_ip,
            forward_port=forward_port,
            encryption_method=encryption_method,
        )
        encoded_config = base64.b64encode(config.encode("utf-8")).decode("ascii")
        q_public_ip = shlex.quote(public_ip)
        q_listen = shlex.quote(listen_addr)
        q_commit = shlex.quote(target.MASTERDNSVPN_COMMIT)
        q_config = shlex.quote(encoded_config)
        q_binary = shlex.quote(target.BINARY_PATH)
        q_config_path = shlex.quote(target.CONFIG_PATH)
        q_state_dir = shlex.quote(target.STATE_DIR)
        q_key_path = shlex.quote(target.KEY_PATH)
        q_service = shlex.quote(target.SERVICE_NAME)

        tcp_probe = ""
        if protocol_type == "TCP" and forward_ip and forward_port:
            tcp_probe = f"""
python3 - <<'PY'
import socket
s = socket.create_connection(({forward_ip!r}, {int(forward_port)}), timeout=4.0)
s.close()
PY
"""

        return f"""set -Eeuo pipefail
install -d -m 0700 {q_state_dir}
test -x {q_binary} || {{ echo "MASTERDNSVPN_ARTIFACT_MISSING" >&2; exit 34; }}
printf '%s' {q_config} | base64 -d > {q_config_path}
chmod 0600 {q_config_path}
printf '%s\n' {q_commit} > {q_state_dir}/source.commit
chmod 0600 {q_state_dir}/source.commit

# Repair is allowed to stop only TwinPanel's own systemd unit.
systemctl stop {q_service} >/dev/null 2>&1 || true

# Clean only a proven stale TwinPanel-owned MasterDnsVPN process. Never touch
# dnsmasq/systemd-resolved/other DNS daemons or another MasterDnsVPN install.
BINARY_PATH={q_binary} CONFIG_PATH={q_config_path} python3 - <<'PY'
import glob
import os
import signal
import sys
import time

binary = os.environ["BINARY_PATH"]
config = os.environ["CONFIG_PATH"]


def owned(pid: int) -> bool:
    try:
        exe = os.path.realpath(f"/proc/{{pid}}/exe")
        if exe != binary:
            return False
        raw = open(f"/proc/{{pid}}/cmdline", "rb").read().split(b"\\0")
        args = [item.decode("utf-8", "replace") for item in raw if item]
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return False
    return config in args

pids = []
for path in glob.glob("/proc/[0-9]*"):
    try:
        pid = int(path.rsplit("/", 1)[-1])
    except ValueError:
        continue
    if pid != os.getpid() and owned(pid):
        pids.append(pid)

for pid in pids:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

if pids:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not any(owned(pid) for pid in pids):
            break
        time.sleep(0.1)

stuck = [pid for pid in pids if owned(pid)]
if stuck:
    print("MASTERDNSVPN_OWNED_PROCESS_STUCK=" + ",".join(map(str, stuck)), file=sys.stderr)
    raise SystemExit(53)

print(f"OWNED_STALE_PROCESSES_CLEANED={{len(pids)}}")
PY

# Exact-IP foreign listeners remain a hard conflict. Wildcard listeners are not
# killed and are not pre-rejected: Linux may permit an exact-IP bind alongside
# a wildcard DNS listener. The real systemd start below is the authoritative
# bind test and fails closed if this host/kernel configuration cannot coexist.
PUBLIC_IP={q_public_ip} python3 - <<'PY'
import ipaddress
import os
import subprocess
import sys

public_ip = str(ipaddress.ip_address(os.environ["PUBLIC_IP"]))
output = subprocess.run(
    ["ss", "-H", "-lunp"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    check=False,
).stdout


def host_from_endpoint(token: str):
    token = token.strip()
    if not token.endswith(":53"):
        return None
    host = token[:-3]
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host.split("%", 1)[0]

exact = []
wildcard = []
for line in output.splitlines():
    endpoints = [host_from_endpoint(part) for part in line.split()]
    hosts = {{value for value in endpoints if value is not None}}
    if public_ip in hosts:
        exact.append(line)
    elif hosts.intersection({{"0.0.0.0", "::", "*"}}):
        wildcard.append(line)

if exact:
    print("UDP53_EXACT_IP_CONFLICT", file=sys.stderr)
    for line in exact[:8]:
        print(line, file=sys.stderr)
    raise SystemExit(52)

print("UDP53_WILDCARD_PRESENT=" + ("yes" if wildcard else "no"))
PY

if [ ! -s {q_key_path} ]; then
  umask 077
  {q_binary} -config {q_config_path} -genkey -nowait >/dev/null 2>&1
fi
test -s {q_key_path}
chmod 0600 {q_key_path}
{tcp_probe}
cat > /etc/systemd/system/{target.SERVICE_NAME} <<'UNIT'
[Unit]
Description=TwinPanel MasterDnsVPN Direct Exit
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={target.BINARY_PATH} -config {target.CONFIG_PATH} -nowait
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
LockPersonality=true
MemoryDenyWriteExecute=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable {q_service} >/dev/null 2>&1 || true
systemctl restart {q_service}
sleep 1
if ! systemctl is-active --quiet {q_service}; then
  systemctl --no-pager --full status {q_service} || true
  journalctl -u {q_service} -n 40 --no-pager || true
  exit 41
fi

main_pid="$(systemctl show {q_service} -p MainPID --value)"
if ! ss -H -lunp 2>/dev/null \
  | grep -F "pid=$main_pid," \
  | grep -F {q_listen} >/dev/null 2>&1; then
  echo "MASTERDNSVPN_EXACT_UDP53_LISTENER_MISSING" >&2
  ss -H -lunp 2>/dev/null | grep -F "pid=$main_pid," >&2 || true
  exit 42
fi

printf 'SERVICE=active\n'
printf 'LISTENER=yes\n'
printf 'DOMAIN=%s\n' {shlex.quote(domain)}
printf 'MODE=%s\n' {shlex.quote(protocol_type)}
printf 'LISTEN=%s\n' {q_listen}
printf 'SOURCE_COMMIT=%s\n' {q_commit}
"""

    target._install_script = _install_script_v221
