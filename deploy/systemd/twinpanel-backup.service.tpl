[Unit]
Description=TwinPanel Automatic Backup
After=network-online.target twinpanel-api.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONPATH=/opt/twinpanel/current/backend
EnvironmentFile=/etc/twinpanel/twinpanel.env
ExecStart=/opt/twinpanel/current/backend/venv/bin/python -m app.backup_worker
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
