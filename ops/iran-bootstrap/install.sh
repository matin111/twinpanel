#!/usr/bin/env bash
# Independent app bootstrap service; never replaces :443 VPN multiplexer.
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the IR node" >&2
  exit 1
fi
python3 -m py_compile connect_proxy.py
python3 -m unittest discover -p 'test_*.py' -v

if ss -ltnH 'sport = :80' | grep -q ':80'; then
  if ! systemctl is-active --quiet twinconnect-iran-bootstrap-connect; then
    echo "Port 80 belongs to another service: refusing takeover" >&2
    exit 1
  fi
fi

install -d -m 0755 /usr/local/libexec
install -m 0644 connect_proxy.py /usr/local/libexec/twinconnect_iran_connect_proxy.py
install -m 0644 twinconnect-iran-bootstrap-connect.service \
  /etc/systemd/system/twinconnect-iran-bootstrap-connect.service
systemctl daemon-reload
systemctl enable --now twinconnect-iran-bootstrap-connect
systemctl is-active --quiet twinconnect-iran-bootstrap-connect

# Validate using the host's own verified panel certificate, not a fake domain.
curl --noproxy '' --silent --fail --show-error --max-time 12 \
  -x http://127.0.0.1:80 https://panel.matindnspro.sbs/health >/dev/null
echo "Domestic CONNECT health verified; existing :443 remains unchanged"
