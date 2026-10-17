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
ExecStart=/bin/bash -lc 'if [ -f /opt/twinpanel/current/.next/standalone/server.js ]; then cd /opt/twinpanel/current/.next/standalone && exec env HOSTNAME=127.0.0.1 PORT=__WEB_PORT__ /usr/bin/node server.js; else cd /opt/twinpanel/current && exec /usr/bin/node /opt/twinpanel/current/node_modules/next/dist/bin/next start -H 127.0.0.1 -p __WEB_PORT__; fi'
Restart=always
RestartSec=4
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
