"""Xray hot user revocation must not restart the daemon or touch other users."""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch


SRC=Path(__file__).resolve().parents[1] / "app/services/xray_hot_client_revoke_v1.py"
NS={"__name__":"test_pure_xray_revoke"}
exec(compile(SRC.read_text(),str(SRC),"exec"),NS)


def make_fixture(folder):
    p=Path(folder)/"config.json"
    rows=[
        {"tag":"vless-in","port":443,"protocol":"vless","settings":{"clients":[
            {"email":"mv-42@twinpanel","id":"uuid-a"},
            {"email":"mv-43@twinpanel","id":"unrelated"}]}},
        {"tag":"vless-xhttp","port":8080,"protocol":"vless","settings":{"clients":[
            {"email":"mv-42@twinpanel","id":"uuid-b"}]}},
        {"tag":"vless-no-target","port":80,"protocol":"vless","settings":{"clients":[
            {"email":"mv-44@twinpanel","id":"another"}]}},
        {"tag":"trojan-in","protocol":"trojan","settings":{"clients":[
            {"email":"mv-42@twinpanel","id":"trojan-untouched"}]}},
    ]
    data={"inbounds":rows,"outbounds":[{"tag":"direct","protocol":"freedom"}]}
    p.write_text(json.dumps(data),encoding="utf-8")
    return p,data


def execute(script,config,lock,handler):
    # Only the test fixture paths are substituted. No SSH or Xray is started.
    script=script.replace('CONFIG=Path("/usr/local/etc/xray/config.json")',
                          f'CONFIG=Path({str(config)!r})')
    script=script.replace('LOCK=Path("/run/twinpanel-xray-hot-user.lock")',
                          f'LOCK=Path({str(lock)!r})')
    def fake_run(args,**kwargs):
        return handler(args)
    with patch.object(subprocess,"run",side_effect=fake_run):
        exec(compile(script,"<hot-revoke-test>","exec"),{})


class XrayHotRevokeSafety(TestCase):
    def test_removes_matching_users_live_and_persisted_with_no_restart(self):
        with TemporaryDirectory() as directory:
            path, original = make_fixture(directory)
            original_bytes=path.read_bytes()
            live={("vless-in","mv-42@twinpanel"),("vless-xhttp","mv-42@twinpanel"),
                  ("vless-in","mv-43@twinpanel")}
            commands=[]
            def runner(args):
                commands.append(args)
                if args[1:3]==["run","-test"]:
                    return SimpleNamespace(returncode=0,stdout="",stderr="")
                if args[:2]==["systemctl","is-active"]:
                    return SimpleNamespace(returncode=0,stdout="",stderr="")
                if args[1:3]==["api","rmu"]:
                    tag=args[4].split("=",1)[1];email=args[5]
                    was=(tag,email) in live
                    live.discard((tag,email))
                    return SimpleNamespace(returncode=0,
                      stdout=f"Removed {int(was)} user(s) in total.",stderr="")
                raise AssertionError(args)
            script=NS["hot_revoke_script"](42)
            execute(script,path,Path(directory)/"lock",runner)
            changed=json.loads(path.read_text())
            self.assertNotEqual(original_bytes,path.read_bytes())
            for inbound in changed["inbounds"][:2]:
                self.assertFalse(any(c["email"]=="mv-42@twinpanel" for c in inbound["settings"]["clients"]))
            self.assertEqual(changed["inbounds"][0]["settings"]["clients"],
                             [original["inbounds"][0]["settings"]["clients"][1]])
            self.assertEqual(changed["inbounds"][2:],original["inbounds"][2:])
            self.assertEqual(live,{("vless-in","mv-43@twinpanel")})
            self.assertFalse(any(args[:2]==["systemctl","restart"] for args in commands))
            self.assertFalse(any("restart" in " ".join(args) for args in commands))
            # A second execution is idempotent and needs no Xray API call.
            commands.clear()
            execute(script,path,Path(directory)/"lock",runner)
            self.assertEqual(commands,[])

    def test_failure_after_first_live_remove_rolls_back_and_keeps_disk(self):
        with TemporaryDirectory() as directory:
            path,_=make_fixture(directory)
            before=path.read_bytes()
            live={("vless-in","mv-42@twinpanel"),("vless-xhttp","mv-42@twinpanel")}
            def runner(args):
                if args[1:3]==["run","-test"] or args[:2]==["systemctl","is-active"]:
                    return SimpleNamespace(returncode=0,stdout="",stderr="")
                if args[1:3]==["api","rmu"]:
                    tag=args[4].split("=",1)[1]
                    if tag=="vless-xhttp":
                        return SimpleNamespace(returncode=1,stdout="",stderr="simulated API error")
                    live.discard((tag,args[5]))
                    return SimpleNamespace(returncode=0,stdout="Removed 1 user(s) in total.",stderr="")
                if args[1:3]==["api","adu"]:
                    blob=json.loads(Path(args[4]).read_text())
                    inlet=blob["inbounds"][0]
                    live.add((inlet["tag"],inlet["settings"]["clients"][0]["email"]))
                    return SimpleNamespace(returncode=0,stdout="Added 1 user(s) in total.",stderr="")
                raise AssertionError(args)
            with self.assertRaisesRegex(RuntimeError,"HOT_REVOKE_API_FAILED"):
                execute(NS["hot_revoke_script"](42),path,Path(directory)/"lock",runner)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(live,{("vless-in","mv-42@twinpanel"),("vless-xhttp","mv-42@twinpanel")})

    def test_rejects_invalid_subscription(self):
        for value in (0,-3):
            with self.assertRaises(ValueError):
                NS["hot_revoke_script"](value)

if __name__=="__main__":
    main()
