[Unit]
Description=TwinPanel 2027 Web
After=network-online.target twinpanel-api.service
Wants=network-online.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/twinpanel/current
Environment=NODE_ENV=production
Environment=NEXT_TELEMETRY_DISABLED=1
EnvironmentFile=/etc/twinpanel/frontend.env
ExecStart=/usr/bin/node /opt/twinpanel/current/node_modules/next/dist/bin/next start -H 127.0.0.1 -p __WEB_PORT__
Restart=always
RestartSec=4
TimeoutStartSec=60
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/twinpanel/current/.next
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
