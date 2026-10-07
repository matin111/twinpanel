[Unit]
Description=TwinPanel Telegram Bot
After=network-online.target twinpanel-api.service
Wants=network-online.target
Requires=twinpanel-api.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
Environment=TWINPANEL_API_BASE=http://127.0.0.1:__API_PORT__
EnvironmentFile=/etc/twinpanel/twinpanel.env
EnvironmentFile=-/etc/twinpanel-telegram-api.env
ExecStart=/opt/twinpanel/current/backend/venv/bin/python -m app.telegram_runtime_bot
Restart=always
RestartSec=4

[Install]
WantedBy=multi-user.target
