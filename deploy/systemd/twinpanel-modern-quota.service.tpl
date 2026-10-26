[Unit]
Description=TwinPanel Modern Protocol Accounting Worker
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
ExecStart=/opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/modern_quota_worker_v257.py
Restart=always
RestartSec=2
TimeoutStopSec=20
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
