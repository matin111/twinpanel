[Unit]
Description=TwinPanel Reseller Telegram Bot Supervisor
After=network-online.target postgresql.service redis-server.service twinpanel-api.service
Wants=network-online.target
Requires=twinpanel-api.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
ExecStart=/opt/twinpanel/venv/bin/python -m app.reseller_bot_runtime
Restart=always
RestartSec=5
TimeoutStartSec=60
TimeoutStopSec=30
KillSignal=SIGINT
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
