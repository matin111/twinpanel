#!/usr/bin/env bash
# Secure DNS-independent Node Agent control, on a dedicated HTTPS IP port.
# Usage: sudo bash scripts/enable-agent-ip-controller-v1.sh PUBLIC_IPV4 [PORT]
set -euo pipefail
umask 077
IP="$1"
PORT=2053
if (( $# > 1 )); then PORT="$2"; fi
ROOT=/etc/twinpanel/controller-ip
CONF="$ROOT/node-agent.json"
SITE="/etc/nginx/sites-available/twinpanel-controller-ip$PORT.conf"
LINK="/etc/nginx/sites-enabled/twinpanel-controller-ip$PORT.conf"

if (( EUID != 0 )); then echo "Run as root on the controller" >&2; exit 2; fi
if ! command -v nginx >/dev/null || ! command -v openssl >/dev/null; then
  echo "Nginx and OpenSSL must be installed first" >&2; exit 2
fi
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  echo "Choose a free TLS port from 1024 to 65535" >&2; exit 2
fi
if ! IP="$IP" python3 - <<'PY'
import os,ipaddress
ipaddress.IPv4Address(os.environ["IP"])
PY
then echo "A public IPv4 address is required" >&2; exit 2; fi

API_URL="https://$IP:$PORT"
if [[ -e "$CONF" ]]; then
  if ! CONF="$CONF" API_URL="$API_URL" python3 - <<'PY'
import json,os
v=json.load(open(os.environ["CONF"]))
assert v["api_url"] == os.environ["API_URL"]
assert v["ca_cert_path"] == "/etc/twinpanel/controller-ip/ca.crt"
PY
  then echo "Existing controller IP differs; refusing to rotate live agent trust" >&2; exit 3; fi
  curl -fsS --cacert "$ROOT/ca.crt" --connect-timeout 4 --max-time 8 "$API_URL/health" >/dev/null
  echo "Controller IP HTTPS already healthy: $API_URL"
  exit 0
fi
if [[ -e "$SITE" || -e "$ROOT/ca.key" || -e "$ROOT/server.key" ]]; then
  echo "Incomplete or conflicting setup found; inspect before retry" >&2; exit 3
fi
if ss -lnt | awk '{print $4}' | grep -Eq ":$PORT$"; then
  echo "TCP/$PORT is occupied; choose another port" >&2; exit 3
fi

install -d -m 700 "$ROOT"
openssl req -x509 -new -nodes -days 3650 \
  -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -sha256 \
  -subj "/CN=TwinPanel Private Controller CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -keyout "$ROOT/ca.key" -out "$ROOT/ca.crt" >/dev/null 2>&1
openssl req -new -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -sha256 -subj "/CN=$IP" -keyout "$ROOT/server.key" \
  -out "$ROOT/server.csr" >/dev/null 2>&1
cat > "$ROOT/server.ext" <<EOF
subjectAltName=IP:$IP
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF
openssl x509 -req -in "$ROOT/server.csr" \
  -CA "$ROOT/ca.crt" -CAkey "$ROOT/ca.key" -CAcreateserial \
  -out "$ROOT/server.crt" -days 825 -sha256 -extfile "$ROOT/server.ext" >/dev/null 2>&1
chmod 600 "$ROOT"/*.key
chmod 644 "$ROOT"/*.crt

cat > "$SITE" <<EOF
# Node-Agent-only IP TLS endpoint; never change VPN TCP/443 SNI forwarding.
server {
  listen $PORT ssl;
  server_name _;
  ssl_certificate $ROOT/server.crt;
  ssl_certificate_key $ROOT/server.key;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_session_tickets off;
  client_max_body_size 1m;

  location = /health {
    proxy_pass http://127.0.0.1:8095/health;
  }
  location ~ ^/v1/nodes/[0-9]+/heartbeat\$ {
    proxy_pass http://127.0.0.1:8095;
    proxy_set_header X-Real-IP \$remote_addr;
  }
  location ~ ^/v1/tunnels/node/[0-9]+/desired\$ {
    proxy_pass http://127.0.0.1:8095;
    proxy_set_header X-Real-IP \$remote_addr;
  }
  location ~ ^/v1/tunnels/[0-9]+/node/[0-9]+/report\$ {
    proxy_pass http://127.0.0.1:8095;
    proxy_set_header X-Real-IP \$remote_addr;
  }
  location / { return 404; }
}
EOF
ln -s "$SITE" "$LINK"
if ! nginx -t >/dev/null 2>&1; then
  rm -f "$LINK"
  echo "Nginx configuration failed; original config remains active" >&2
  exit 4
fi
systemctl reload nginx
CONF="$CONF" API_URL="$API_URL" python3 - <<'PY'
import json,os
with open(os.environ["CONF"],"x") as f:
    json.dump({
        "api_url":os.environ["API_URL"],
        "ca_cert_path":"/etc/twinpanel/controller-ip/ca.crt",
    },f,indent=2)
    f.write("\n")
os.chmod(os.environ["CONF"],0o600)
PY
curl -fsS --cacert "$ROOT/ca.crt" --connect-timeout 4 --max-time 8 "$API_URL/health" >/dev/null
echo "Pinned Node Agent IP controller ready: $API_URL"
echo "Keep the controller CA private key outside repositories and backups shared with agents."
