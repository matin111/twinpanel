[Unit]
Description=TwinPanel Transport Manager
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
Environment=PATH=/opt/twinpanel/current/backend/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=/opt/twinpanel/current/backend/venv/bin/python -m app.tunnel_transport_manager
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
