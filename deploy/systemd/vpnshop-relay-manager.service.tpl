[Unit]
Description=TwinPanel Generic SSH Relay Failover Manager
After=network-online.target twinpanel-api.service
Wants=network-online.target
Requires=twinpanel-api.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONPATH=/opt/twinpanel/current/backend
EnvironmentFile=/etc/twinpanel/twinpanel.env
ExecStart=/opt/twinpanel/current/backend/venv/bin/python -m app.tunnel_relay_manager
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
