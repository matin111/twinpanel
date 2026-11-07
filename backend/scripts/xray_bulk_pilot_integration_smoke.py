"""Isolated integration test for bulk Xray pilot; never contacts live nodes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.xray_bulk_hot_sync_pilot_v1 import bulk_hot_sync_script

FAKE_XRAY = """#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
state_path=Path(os.environ['FAKE_XRAY_STATE'])
state=json.loads(state_path.read_text()) if state_path.exists() else {}
if args[0]=='run':
 json.load(open(args[-1]))
 sys.exit(0)
if args[:2]==['api','adu']:
 doc=json.load(open(args[-1]))
 item=doc['inbounds'][0]
 tag=item['tag'];clients=item['settings']['clients']
 if tag==os.environ.get('FAKE_FAIL_ON_TAG'):
  sys.exit(1)
 for c in clients:
  key=tag+':'+c['email']
  if key in state and state[key]!=c['id']:sys.exit(1)
  state[key]=c['id']
 state_path.write_text(json.dumps(state))
 print('Added %d user(s) in total.' % len(clients))
 sys.exit(0)
if args[:2]==['api','inbounduser']:
 tag=next(x[5:] for x in args if x.startswith('-tag='))
 email=next(x[7:] for x in args if x.startswith('-email='))
 key=tag+':'+email
 if key not in state:sys.exit(1)
 print(state[key]);sys.exit(0)
if args[:2]==['api','rmu']:
 tag=next(x[5:] for x in args if x.startswith('-tag='))
 state.pop(tag+':'+args[-1],None)
 state_path.write_text(json.dumps(state))
 print('Removed 1 user(s) in total.')
 sys.exit(0)
sys.exit(2)
"""

def run():
    ids = [(str(uuid4()), "mv-3001@twinpanel"),
           (str(uuid4()), "mv-3002@twinpanel")]
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        path = base / "config.json"
        state = base / "state.json"
        executable = base / "xray_mock.py"
        executable.write_text(FAKE_XRAY)
        executable.chmod(0o700)
        bindir = base / "bin"
        bindir.mkdir()
        ctl = bindir / "systemctl"
        ctl.write_text("#!/bin/sh\nexit 0\n")
        ctl.chmod(0o700)
        doc = {"inbounds": [
            {"tag": name, "port": port, "protocol": "vless",
             "settings": {"clients": []}}
            for name, port in (("a", 8443), ("b", 9447), ("c", 9448))
        ]}
        path.write_text(json.dumps(doc))
        original = path.read_bytes()
        script = bulk_hot_sync_script(ids)
        script = script.replace(
            'CONF = Path("/usr/local/etc/xray/config.json")',
            f"CONF = Path({str(path)!r})",
        ).replace(
            'LOCK = Path("/run/twinpanel-xray-hot-user.lock")',
            f"LOCK = Path({str(base / 'lock')!r})",
        ).replace(
            'XRAY = "/usr/local/bin/xray"',
            f"XRAY = {str(executable)!r}",
        )
        env = os.environ.copy()
        env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
        env["FAKE_XRAY_STATE"] = str(state)
        def execute(extra=None):
            return subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=22,
                env={**env, **(extra or {})},
            )
        result = execute({"FAKE_FAIL_ON_TAG": "b"})
        assert result.returncode != 0
        assert path.read_bytes() == original
        assert json.loads(state.read_text()) == {}, "rollback must remove all attempted users"
        result = execute()
        assert result.returncode == 0, result.stderr[-800:]
        report = json.loads(result.stdout.strip().splitlines()[-1])
        assert report["hot_applied"] is True
        assert report["users_added"] == 6
        assert all(len(x["settings"]["clients"]) == 2
                   for x in json.loads(path.read_text())["inbounds"])
        assert len(json.loads(state.read_text())) == 6
        result = execute()
        assert result.returncode == 0, result.stderr[-800:]
        report = json.loads(result.stdout.strip().splitlines()[-1])
        assert report["changed"] is False
        assert report["users_added"] == 0
        assert len(json.loads(state.read_text())) == 6

if __name__ == "__main__":
    run()
    print("XRAY_BULK_PILOT_INTEGRATION_PASS")
