[Unit]
Description=TwinPanel Public Release Updater
After=network-online.target twinpanel-api.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
EnvironmentFile=-/etc/twinpanel/install.env
ExecStart=/opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/twinpanel_public_updater.py
TimeoutStartSec=3600
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6

[Install]
WantedBy=multi-user.target
