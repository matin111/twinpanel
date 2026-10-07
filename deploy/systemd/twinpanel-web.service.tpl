[Unit]
Description=TwinPanel 2027 Web
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/twinpanel/current
Environment=NODE_ENV=production
EnvironmentFile=/etc/twinpanel/frontend.env
ExecStart=/usr/bin/node /opt/twinpanel/current/node_modules/next/dist/bin/next start -H 127.0.0.1 -p __WEB_PORT__
Restart=always
RestartSec=4
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
[Install]
WantedBy=multi-user.target
