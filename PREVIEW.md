# TwinPanel UI Preview

The UI preview should bind only to `127.0.0.1:3010`.

## Server

```bash
git clone git@github.com:matin111/twinpanel.git /opt/twinpanel-preview
cd /opt/twinpanel-preview
chmod +x scripts/preview-ui.sh
PORT=3010 ./scripts/preview-ui.sh
```

## Windows SSH tunnel

From PowerShell:

```powershell
ssh -L 3010:127.0.0.1:3010 root@YOUR_SERVER_IP
```

Then open:

```text
http://127.0.0.1:3010
```

Useful pages:

- `/login`
- `/store`
- `/admin`
- `/admin/users`
- `/admin/subscriptions`
- `/admin/plans`
- `/admin/nodes`
- `/admin/tunnels`
- `/admin/payments`
- `/admin/support`
- `/admin/notifications`
- `/admin/settings`
- `/panel`
- `/reseller`

Use the `FA / EN` switch in the UI to test RTL and LTR modes.
