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
# Canonical updater authority remains backend/scripts/twinpanel_public_updater.py.
# V69 is preferred when the active release ships it. A rollback can legally move
# /opt/twinpanel/current to a pre-V69 release while this newer unit is still on
# disk, so ExecStart must fall back to the canonical core instead of hard-failing
# on a missing wrapper.
ExecStart=/bin/bash -lc 'if [ -f /opt/twinpanel/current/backend/scripts/twinpanel_public_updater_v69.py ]; then exec /opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/twinpanel_public_updater_v69.py; else exec /opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/twinpanel_public_updater.py; fi'
TimeoutStartSec=3600
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6

[Install]
WantedBy=multi-user.target
