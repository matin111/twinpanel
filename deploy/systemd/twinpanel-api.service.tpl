[Unit]
Description=TwinPanel API
After=network-online.target postgresql.service redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
EnvironmentFile=/etc/twinpanel/twinpanel.env
ExecStart=/opt/twinpanel/current/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port __API_PORT__
Restart=always
RestartSec=4
TimeoutStartSec=60
TimeoutStopSec=30
KillSignal=SIGINT
PrivateTmp=true
NoNewPrivileges=false
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
