[Unit]
Description=TwinPanel Quota Agent
After=network-online.target xray.service
Wants=network-online.target
ConditionPathExists=/opt/twinpanel/current/quota-agent/agent.py
ConditionPathExists=/etc/twinpanel-quota-agent/config.json

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/quota-agent
ExecStart=/usr/bin/python3 /opt/twinpanel/current/quota-agent/agent.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=/var/lib/twinpanel-quota-agent

[Install]
WantedBy=multi-user.target
