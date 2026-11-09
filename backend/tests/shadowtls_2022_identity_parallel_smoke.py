"""Safe additive migration tests, including real local sing-box end-to-end.

All canary listeners bind loopback only. Production nodes/configurations and
customer secrets are never written or altered.
"""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from app.services.shadowtls_2022_identity_v1 import (
    NEW_INNER_TAG, NEW_OUTER_TAG, INNER_METHOD,
    identity_client_outbounds, stage_parallel_identity_inbounds, user_inner_key,
)


def canary():
    secret_a = secrets.token_urlsafe(32)
    secret_b = secrets.token_urlsafe(32)
    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    legacy = {
        "log": {"level": "info"},
        "inbounds": [
            {"type": "shadowtls", "tag": "twinpanel-shadowtls-in",
             "listen": "127.0.0.1", "listen_port": 18448,
             "version": 3, "strict_mode": True,
             "users": [
                 {"name": "tp-sub-17", "password": secret_a},
                 {"name": "tp-sub-18", "password": secret_b},
                 {"name": "twinpanel-bootstrap", "password": secrets.token_urlsafe(22)},
             ],
             "handshake": {"server": "www.microsoft.com", "server_port": 443},
             "detour": "twinpanel-shadowtls-inner"},
            {"type": "shadowsocks", "tag": "twinpanel-shadowtls-inner",
             "listen": "127.0.0.1", "method": "aes-256-gcm",
             "password": secrets.token_urlsafe(24)},
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }
    original = copy.deepcopy(legacy)
    modern = stage_parallel_identity_inbounds(legacy, listen_port=30448, server_key=key)
    assert legacy == original
    assert modern["inbounds"][:2] == original["inbounds"]
    modern_inner = next(x for x in modern["inbounds"] if x["tag"] == NEW_INNER_TAG)
    assert modern_inner["method"] == INNER_METHOD
    assert [x["name"] for x in modern_inner["users"]] == ["tp-sub-17", "tp-sub-18"]
    assert modern_inner["users"][0]["password"] != modern_inner["users"][1]["password"]
    assert modern_inner["users"][0]["password"] == user_inner_key("tp-sub-17", secret_a)
    for kwargs in ({"listen_port":18448,"server_key":key},
                   {"listen_port":30448,"server_key":"invalid"}):
        try:
            stage_parallel_identity_inbounds(legacy, **kwargs)
            raise AssertionError("unsafe stage was accepted")
        except ValueError:
            pass
    try:
        stage_parallel_identity_inbounds(modern, listen_port=30448, server_key=key)
        raise AssertionError("duplicate modern inbound accepted")
    except ValueError:
        pass

    # Use ephemeral loopback ports, not live customer listeners.
    with tempfile.TemporaryDirectory(prefix="tp-shadowtls-identity-check-") as td:
        folder = Path(td)
        server = {
            "log": {"level": "info"},
            "inbounds": [x for x in modern["inbounds"] if x["tag"] in (NEW_OUTER_TAG, NEW_INNER_TAG)],
            "outbounds": [{"type": "direct", "tag": "direct"}],
        }
        clients = []
        for port, username, password in ((30480, "tp-sub-17", secret_a), (30481, "tp-sub-18", secret_b)):
            transport = {
                "type":"shadowtls","tag":"old-shadowtls",
                "server":"127.0.0.1","server_port":18448,
                "version":3,"password":password,
                "tls":{"enabled":True,"server_name":"www.microsoft.com"},
            }
            outs = identity_client_outbounds(
                transport, username=username, outer_password=password,
                listen_port=30448,server_key=key,
            )
            assert outs[0]["password"] == key+":"+user_inner_key(username,password)
            clients.append({
                "log":{"level":"warn"},
                "inbounds":[{"type":"socks","tag":"local","listen":"127.0.0.1","listen_port":port}],
                "outbounds":outs,"route":{"final":outs[0]["tag"]},
            })
        files = {"server":server,"client-a":clients[0],"client-b":clients[1]}
        for name,conf in files.items():
            path=folder/(name+".json")
            path.write_text(json.dumps(conf))
            path.chmod(0o600)
            check=subprocess.run(["/usr/bin/sing-box","check","-c",str(path)],
                                 capture_output=True,text=True,timeout=10)
            assert check.returncode == 0, (name,check.stderr[-400:])
        procs = []
        try:
            for name in files:
                log=open(folder/(name+".log"),"w",encoding="utf-8")
                proc=subprocess.Popen(["/usr/bin/sing-box","run","-c",str(folder/(name+".json"))],
                                      stdout=log,stderr=subprocess.STDOUT)
                procs.append((proc,log))
                time.sleep(0.6)
            for port in (30480,30481):
                response=subprocess.run([
                    "curl","-sS","-x",f"socks5h://127.0.0.1:{port}",
                    "--connect-timeout","8","--max-time","18",
                    "-o","/dev/null","-w","%{http_code}",
                    "https://www.example.com/",
                ],capture_output=True,text=True,timeout=22)
                assert response.returncode == 0 and response.stdout.strip()=="200", (
                    port,response.returncode,response.stderr[:120])
            time.sleep(0.5)
            output=(folder/"server.log").read_text(errors="replace")
            for username in ("tp-sub-17","tp-sub-18"):
                assert f"[{username}] inbound connection to" in output, (
                    "missing authenticated inner user",username)
            assert "inbound/shadowsocks" in output
            print("SHADOWTLS_2022_TWO_USER_IDENTITY_E2E_PASS")
        finally:
            for proc,log in procs:
                proc.terminate()
            for proc,log in procs:
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired: proc.kill()
                log.close()


if __name__ == "__main__":
    canary()
