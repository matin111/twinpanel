[Unit]
Description=TwinPanel Reseller Telegram Bots
After=network-online.target twinpanel-api.service
Wants=network-online.target
Requires=twinpanel-api.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/twinpanel.env
ExecStart=/opt/twinpanel/current/backend/venv/bin/python -m app.reseller_bot_runtime
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
