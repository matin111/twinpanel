[Unit]
Description=TwinPanel Modern Accounting Worker
After=network-online.target postgresql.service redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
ExecStart=/opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/twinpanel_modern_accounting_worker.py
Restart=always
RestartSec=4
TimeoutStartSec=90
TimeoutStopSec=15
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
