[Unit]
Description=TwinPanel API
After=network-online.target postgresql.service redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
ExecStart=/opt/twinpanel/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port __API_PORT__ --workers 1
Restart=always
RestartSec=4
TimeoutStartSec=90
TimeoutStopSec=30
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
