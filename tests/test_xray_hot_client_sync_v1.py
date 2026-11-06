"""A real subprocess smoke for atomic live Xray API user provisioning (no SSH)."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
HOT = ROOT / "backend/app/xray_hot_client_sync_v1.py"
RUNTIME = ROOT / "backend/app/xray_modern_runtime.py"
INSTALL = ROOT / "backend/app/self_hosted_runtime.py"


def make_script(client_id: str, email: str) -> str:
    tree = ast.parse(HOT.read_text(encoding="utf-8"))
    remote = next(
        ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_REMOTE" for t in node.targets)
    )
    func = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "hot_client_sync_script"
    )
    env = {"uuid": uuid, "_REMOTE": remote}
    exec(compile(ast.Module(body=[func], type_ignores=[]), str(HOT), "exec"), env)
    script = env["hot_client_sync_script"](client_id, email)
    compile(script, "<hot-vless-user-sync>", "exec")
    return script


FAKE_XRAY = textwrap.dedent('''\\
    #!/usr/bin/env python3
    import json, os, sys
    from pathlib import Path
    a=sys.argv[1:]
    state_path=Path(os.environ["FAKE_XRAY_STATE"])
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    if a[0]=="run" and "-test" in a:
        json.load(open(a[a.index("-config")+1]))
        print("Configuration OK.")
        sys.exit(0)
    if a[:2] == ["api","adu"]:
        payload=json.load(open(a[-1]))
        row=payload["inbounds"][0]
        tag=row["tag"]; c=row["settings"]["clients"][0]
        if not row.get("port") or os.environ.get("FAKE_XRAY_FAIL_TAG")==tag:
            print("Added 0 user(s) in total.");sys.exit(0)
        table=state.setdefault(tag,{})
        if c["email"] in table:
            print("Added 0 user(s) in total.");sys.exit(0)
        table[c["email"]]=c["id"]
        state_path.write_text(json.dumps(state))
        print("Added 1 user(s) in total.");sys.exit(0)
    if a[:2] == ["api","rmu"]:
        tag=next(z[5:] for z in a if z.startswith("-tag="))
        email=a[-1];table=state.setdefault(tag,{})
        if email not in table:
            print("Removed 0 user(s) in total.");sys.exit(0)
        del table[email];state_path.write_text(json.dumps(state))
        print("Removed 1 user(s) in total.");sys.exit(0)
    if a[:2] == ["api","inbounduser"]:
        tag=next(z[5:] for z in a if z.startswith("-tag="))
        email=next(z[7:] for z in a if z.startswith("-email="))
        if email in state.get(tag,{}):
            print("User ID:",state[tag][email]);sys.exit(0)
        sys.exit(1)
    sys.exit(2)
''').lstrip()
FAKE_SYSTEMCTL = '#!/bin/sh\n[ "$1" = is-active ] && exit 0\nexit 1\n'


class HotVlessClientSyncTest(unittest.TestCase):
    def test_applies_persists_and_rolls_back_without_restart(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            xray = root / "xray"
            systemctl = root / "systemctl"
            xray.write_text(FAKE_XRAY, encoding="utf-8")
            systemctl.write_text(FAKE_SYSTEMCTL, encoding="utf-8")
            xray.chmod(0o755)
            systemctl.chmod(0o755)
            path = root / "config.json"
            state = root / "runtime.json"
            lock = root / "hot.lock"
            email = "mv-test@example.invalid"
            tags = ["vless-in", "vless-ws-tls", "vless-xhttp-reality"]
            doc = {
                "inbounds": [
                    {
                        "tag": tag, "port": 8000+i, "protocol": "vless",
                        "settings": {"clients": [
                            {"id": str(uuid.uuid4()), "email": "unrelated@keep", "level": 0}
                        ], "decryption": "none"},
                    } for i,tag in enumerate(tags)
                ] + [{"tag": "api", "protocol": "dokodemo-door", "port": 10085}],
                "outbounds": [{"protocol": "freedom", "tag": "direct"}],
            }
            path.write_text(json.dumps(doc))
            path.chmod(0o640)
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ.get("PATH",""),
                   "FAKE_XRAY_STATE": str(state)}

            def execute(identifier, **changes):
                script = make_script(identifier, email)
                script = script.replace("/usr/local/etc/xray/config.json", str(path))
                script = script.replace("/run/twinpanel-xray-hot-user.lock", str(lock))
                script = script.replace("/usr/local/bin/xray", str(xray))
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    capture_output=True, text=True, timeout=15,
                    env={**env, **changes},
                )
                return result

            first_id = str(uuid.uuid4())
            first = execute(first_id)
            self.assertEqual(first.returncode,0,first.stderr[-650:])
            first_result = json.loads(first.stdout.strip().splitlines()[-1])
            self.assertTrue(first_result["changed"])
            self.assertTrue(first_result["hot_applied"])
            self.assertEqual(first_result["hot_updated"], 3)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(
                sorted([row["id"] for row in json.loads(path.read_text())["inbounds"][0]["settings"]["clients"] if row["email"]=="unrelated@keep"]),
                sorted([row["id"] for row in doc["inbounds"][0]["settings"]["clients"]]),
            )
            saved = path.read_bytes()
            mtime = path.stat().st_mtime_ns
            second = execute(first_id)
            self.assertEqual(second.returncode, 0, second.stderr[-650:])
            self.assertFalse(json.loads(second.stdout.strip())["changed"])
            self.assertEqual(path.read_bytes(), saved)
            self.assertEqual(path.stat().st_mtime_ns, mtime)

            second_id = str(uuid.uuid4())
            failed = execute(second_id, FAKE_XRAY_FAIL_TAG=tags[2])
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(path.read_bytes(), saved)
            self.assertEqual(json.loads(state.read_text()), {
                tag: {email: first_id} for tag in tags
            })
            success = execute(second_id)
            self.assertEqual(success.returncode, 0, success.stderr[-650:])
            self.assertEqual(json.loads(state.read_text()), {
                tag: {email: second_id} for tag in tags
            })
            current = json.loads(path.read_text())
            self.assertEqual(current["inbounds"][-1], doc["inbounds"][-1])
            self.assertEqual(current["outbounds"], doc["outbounds"])
            for inbound in current["inbounds"][:-1]:
                self.assertEqual(
                    [u["id"] for u in inbound["settings"]["clients"] if u["email"] == email],
                    [second_id],
                )

    def test_runtime_has_no_restart_for_credential_changes(self):
        runtime = RUNTIME.read_text(encoding="utf-8")
        callback = runtime[
            runtime.index("async def _xray_account_modern("):
            runtime.index("def _modern_item_present(")
        ]
        self.assertIn('if not bool(sync_result.get("hot_applied")):', callback)
        self.assertNotIn('systemctl restart xray', callback)
        install = INSTALL.read_text(encoding="utf-8")
        self.assertIn("apply_xray_hot_client_sync_v1()", install)


if __name__ == "__main__":
    unittest.main()
