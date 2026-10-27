[Unit]
Description=TwinPanel Public Release Updater
# IMPORTANT: do not order this oneshot unit After=twinpanel-api.service or
# twinpanel-web.service. The updater restarts both services while its own
# ExecStart job is still running. Ordering the updater after either service can
# keep the replacement start job queued behind the still-active updater job,
# while the updater waits for the new health/version and eventually rolls back.
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
EnvironmentFile=-/etc/twinpanel/install.env
# V69 preserves the proven updater core but replaces the single shared 45s
# health deadline with staged API -> Web health windows. This avoids false
# rollback when a bounded API shutdown plus Python import/startup consumes most
# of the legacy shared deadline.
ExecStart=/opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/twinpanel_public_updater_v69.py
TimeoutStartSec=3600
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6

[Install]
WantedBy=multi-user.target
