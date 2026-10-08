#!/usr/bin/env bash
set -Eeuo pipefail

API_PORT="${API_PORT:-8095}"
PUBLIC_IP="${PUBLIC_IP:-}"

if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
fi

if [[ -z "$PUBLIC_IP" ]]; then
  echo "ERROR: public/server IPv4 could not be detected. Run with PUBLIC_IP=x.x.x.x" >&2
  exit 1
fi

CONF="/etc/nginx/sites-available/twinpanel-api-ip.conf"
ENABLED="/etc/nginx/sites-enabled/twinpanel-api-ip.conf"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

cat >"$TMP" <<EOF
# TWINPANEL_API_IP_FALLBACK_V1
# Public API works on the server IP until an API domain is configured.
server {
    listen 80;
    listen [::]:80;

    server_name ${PUBLIC_IP};

    location ^~ /v1/ {
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 900s;
        proxy_read_timeout 900s;
        proxy_buffering off;
    }

    location = /health {
        proxy_pass http://127.0.0.1:${API_PORT}/health;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        return 404;
    }
}
EOF

install -m 0644 "$TMP" "$CONF"
ln -sfn "$CONF" "$ENABLED"

nginx -t
systemctl reload nginx

echo "API_IP_BASE=http://${PUBLIC_IP}"
echo "HEALTH=http://${PUBLIC_IP}/health"
