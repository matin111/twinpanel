#!/usr/bin/env bash
# Configure ONE-FILE (up to 2GB) backups using the official local Telegram
# Bot API server, exclusively for TwinPanel's dedicated backup bot.
# Must be run directly on the server by an operator. No secrets on CLI/Chat.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then echo 'Run as root'; exit 1; fi
BIN=/usr/local/bin/telegram-bot-api
ENV=/etc/twinpanel/backup-telegram-api.env
CONFIG=/etc/twinpanel/backup-telegram-local-api.json
SERVICE=/etc/systemd/system/twinpanel-backup-telegram-api.service
if [[ ! -x "$BIN" ]]; then
  echo 'Install the official TDLib telegram-bot-api binary at /usr/local/bin/telegram-bot-api first.'
  echo 'https://github.com/tdlib/telegram-bot-api'
  exit 2
fi
if ss -ltn 'sport = :8081' | grep -q 127.0.0.1; then
  echo 'Port 8081 is already in use. Inspect before installing.'
  exit 3
fi
echo 'Obtain your personal Telegram API ID and API Hash at https://my.telegram.org'
read -r -p 'Telegram API ID: ' API_ID
read -rs -p 'Telegram API Hash (hidden): ' API_HASH
echo
if [[ ! "$API_ID" =~ ^[0-9]+$ ]] || [[ ! "$API_HASH" =~ ^[A-Fa-f0-9]{32}$ ]]; then
  echo 'Invalid ID/Hash format'; exit 4
fi
install -d -m 0700 /etc/twinpanel
install -d -m 0700 /var/lib/twinpanel-telegram-bot-api
umask 077
printf 'TELEGRAM_API_ID=%s\nTELEGRAM_API_HASH=%s\n' "$API_ID" "$API_HASH" > "$ENV"
chmod 0600 "$ENV"
unset API_HASH API_ID

cat >"$SERVICE" <<'SERVICE_EOF'
[Unit]
Description=TwinPanel backup-only local Telegram Bot API (2GB sendDocument)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/twinpanel/backup-telegram-api.env
WorkingDirectory=/var/lib/twinpanel-telegram-bot-api
ExecStart=/usr/local/bin/telegram-bot-api --local --http-ip-address=127.0.0.1 --http-port=8081
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=/var/lib/twinpanel-telegram-bot-api

[Install]
WantedBy=multi-user.target
SERVICE_EOF
chmod 0644 "$SERVICE"
systemctl daemon-reload
systemctl enable --now twinpanel-backup-telegram-api.service

# Do NOT switch the backup bot automatically. Telegram officially requires
# logOut() from the cloud API before guaranteed successful local migration.
# Administrators must confirm the local API process is healthy and perform
# that handoff before writing the enable config.
if ! systemctl is-active --quiet twinpanel-backup-telegram-api.service; then
  echo 'Local Bot API failed to start. The existing multipart backup flow is unchanged.'
  exit 5
fi

echo 'Local Bot API is running on 127.0.0.1:8081.'
echo 'NEXT: migrate the dedicated backup bot from the cloud API using logOut'
echo 'and verify local getMe, then create the enable config:'
echo '  /etc/twinpanel/backup-telegram-local-api.json'
echo '  {"enabled":true,"base_url":"http://127.0.0.1:8081"}'
echo 'Only after that will TwinPanel upload one complete encrypted .tpbak.'
