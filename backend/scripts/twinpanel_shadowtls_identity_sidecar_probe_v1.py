#!/usr/bin/env python3
"""Exercise two generated ShadowTLS identities against the loopback-only canary.

No real subscriber credential is read into client profiles. Temporary synthetic
canary identities are appended ONLY to the separate canary config, used for
two short HTTPS checks, then removed in a finally block; original production
sing-box daemon, ports, customer configs, quotas and central DB are untouched.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path


BASE = Path("/etc/twinpanel/sing-box/shadowtls-identity-canary")
SERVICE = "twinpanel-shadowtls-identity-canary"
BINARY = "/usr/local/bin/twinpanel-sing-box"
PORT = 19448
API_PORT = 19096


def execute(args, *, timeout=20):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def atomic_write(path: Path, data: bytes) -> None:
    target = path.with_name(path.name + ".probe-" + secrets.token_hex(4))
    try:
        fd = os.open(str(target), os.O_EXCL | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(target, path)
        path.chmod(0o600)
    finally:
        target.unlink(missing_ok=True)


def load_identity_functions():
    path = Path(__file__).resolve().parents[1] / "app/services/shadowtls_2022_identity_v1.py"
    spec = importlib.util.spec_from_file_location("shadowtls_identity_pure", path)
    if not spec or not spec.loader:
        raise RuntimeError("IDENTITY_HELPERS_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reader_script(state_path: Path) -> str:
    source = Path(__file__).resolve().parents[1] / "app/services/singbox_native_accounting_v265.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_snapshot_script"
    )
    env = {
        "STATE_PATH": str(state_path),
        "SINGBOX_API_LISTEN": "127.0.0.1",
        "SINGBOX_API_PORT": API_PORT,
        "SERVICE_NAME": SERVICE,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])),
                 str(source), "exec"), env)
    return env["_snapshot_script"]()


def require_ready() -> None:
    for _ in range(40):
        a = execute(["systemctl", "is-active", SERVICE])
        if a.stdout.strip() != "active":
            raise RuntimeError("SIDECAR_NOT_ACTIVE")
        b = execute(["ss", "-H", "-ltn"])
        if b.returncode == 0 and ":19448 " in b.stdout and ":19096 " in b.stdout:
            return
        time.sleep(0.4)
    raise RuntimeError("SIDECAR_NOT_READY")


def probe() -> dict:
    cfg_path = BASE / "config.json"
    state_path = BASE / "identity_state.json"
    if not cfg_path.is_file() or not state_path.is_file():
        raise RuntimeError("CANARY_NOT_INSTALLED")
    original = cfg_path.read_bytes()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("delivery_enabled") or state.get("public_listener"):
        raise RuntimeError("PUBLIC_CANARY_PROBE_FORBIDDEN")
    module = load_identity_functions()
    config = json.loads(original)
    outer = next(r for r in config["inbounds"]
                 if r.get("tag") == module.NEW_OUTER_TAG)
    inner = next(r for r in config["inbounds"]
                 if r.get("tag") == module.NEW_INNER_TAG)
    if outer.get("listen") != "127.0.0.1" or len(inner.get("users") or []) < 500:
        raise RuntimeError("EXPECTED_LOCAL_AUTHENTICATED_LISTENER_MISSING")

    names = ["tp-canary-" + secrets.token_hex(9) for _ in range(2)]
    passwords = [secrets.token_urlsafe(30) for _ in range(2)]
    derived = [
        module.user_inner_key(name, pwd, state["derivation_secret"])
        for name,pwd in zip(names,passwords)
    ]
    changed = json.loads(original)
    # Test attribution independently of the node's upstream VLESS egress.
    # The entire original sidecar config is restored in the finally block.
    changed["outbounds"] = [{"type":"direct","tag":"direct"}]
    changed["route"] = {"final":"direct"}
    for row in changed["inbounds"]:
        if row.get("tag") == module.NEW_OUTER_TAG:
            row["users"].extend(
                {"name":name, "password":pwd} for name,pwd in zip(names,passwords)
            )
        if row.get("tag") == module.NEW_INNER_TAG:
            row["users"].extend(
                {"name":name, "password":key} for name,key in zip(names,derived)
            )

    # Validate before the isolated daemon's only restart.
    clients = []
    processes = []
    installed = False
    report = None
    with tempfile.TemporaryDirectory(prefix="tp-shadowtls-sidecar-probe-") as td:
        folder = Path(td)
        changed_path = folder/"updated.json"
        changed_path.write_text(json.dumps(changed), encoding="utf-8")
        changed_path.chmod(0o600)
        if execute([BINARY,"check","-c",str(changed_path)],timeout=35).returncode:
            raise RuntimeError("SYNTHETIC_CANARY_CONFIG_REJECTED")
        try:
            atomic_write(cfg_path, json.dumps(changed).encode())
            installed = True
            if execute(["systemctl","restart",SERVICE],timeout=24).returncode:
                raise RuntimeError("SIDECAR_CANARY_ONLY_RESTART_FAILED")
            require_ready()

            for idx,(name,password,key) in enumerate(zip(names,passwords,derived)):
                transport = {
                    "type":"shadowtls","tag":"transport",
                    "server":"127.0.0.1","server_port":PORT,
                    "version":3,"password":password,
                    "tls":{"enabled":True,
                           "server_name":str(outer["handshake"]["server"])},
                }
                outbounds=module.identity_client_outbounds(
                    transport, username=name, user_key=key,
                    listen_port=PORT, server_key=state["server_key"],
                )
                port = 31480+idx
                client={
                    "log":{"level":"warn"},
                    "inbounds":[{"type":"socks","tag":"local",
                                 "listen":"127.0.0.1","listen_port":port}],
                    "outbounds":outbounds,"route":{"final":outbounds[0]["tag"]},
                }
                path = folder/f"client{idx}.json"
                path.write_text(json.dumps(client),encoding="utf-8")
                path.chmod(0o600)
                if execute([BINARY,"check","-c",str(path)],timeout=12).returncode:
                    raise RuntimeError("SYNTHETIC_CLIENT_CONFIG_INVALID")
                log=open(folder/f"client{idx}.log","w")
                process=subprocess.Popen([BINARY,"run","-c",str(path)],
                                         stdout=log,stderr=subprocess.STDOUT)
                processes.append((process,log))
            time.sleep(1.5)
            checks=[]
            for idx in range(2):
                result = execute([
                    "curl","-sS","-x",f"socks5h://127.0.0.1:{31480+idx}",
                    "--connect-timeout","5","--max-time","20",
                    "-o","/dev/null","-w","%{http_code}",
                    "https://www.example.com/",
                ],timeout=24)
                checks.append(result.returncode==0 and result.stdout.strip()=="200")
            # The real API reader uses typed protobuf connection events.
            # Feed only an isolated service token from the root-only state.
            reader_state=folder/"reader.json"
            reader_state.write_text(json.dumps({"accounting_api":{"secret":state["api_secret"]}}))
            reader_state.chmod(0o600)
            result=execute([
                "/opt/twinpanel/venv/bin/python","-c",reader_script(reader_state)
            ],timeout=20)
            if result.returncode:
                raise RuntimeError("SIDECAR_CONNECTION_SNAPSHOT_FAILED")
            payload=json.loads(result.stdout.strip().splitlines()[-1])
            evidence=[
                [r for r in payload.get("rows",[])
                 if r.get("inbound")==module.NEW_INNER_TAG and r.get("user")==name]
                for name in names
            ]
            report={
                "ok":all(checks) and all(evidence)
                      and all(any(int(r.get("uplink_total") or 0)+int(r.get("downlink_total") or 0)>0
                                  for r in group) for group in evidence),
                "synthetic_clients":2,
                "test_route":"direct_only",
                "http_success":checks,
                "authenticated_inner_user_observed":[bool(group) for group in evidence],
                "positive_per_user_bytes":[any(
                    int(r.get("uplink_total") or 0)+int(r.get("downlink_total") or 0)>0
                    for r in group) for group in evidence],
                "customer_credentials_used":False,
                "central_quota_modified":False,
            }
        finally:
            for process,log in processes:
                process.terminate()
            for process,log in processes:
                try: process.wait(timeout=4)
                except subprocess.TimeoutExpired: process.kill()
                log.close()
            if installed:
                atomic_write(cfg_path,original)
                rollback=execute(["systemctl","restart",SERVICE],timeout=24)
                if rollback.returncode:
                    raise RuntimeError("SIDECAR_TEST_ROLLBACK_RESTART_FAILED")
                require_ready()
    if report is None:
        raise RuntimeError("SIDECAR_NO_REPORT")
    report["synthetic_accounts_removed"] = True
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(probe(),sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok":False,"reason":str(exc)},sort_keys=True))
        raise SystemExit(1)
