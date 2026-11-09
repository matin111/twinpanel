"""Idempotent live repair of the missing WS TLS Xray inbound.

Modern Xray historically returned early when its base XHTTP listener existed,
even if the dedicated certificate had become valid *after* installation.
Rebuilds/restarts would disconnect other customers. This routine adds only
vless-ws-tls with Xray HandlerService and preserves existing identities.
It does nothing to domainless nodes, existing inbound ports or other services.
"""
from __future__ import annotations

import base64
import json
import shlex

from .routers import provision

TAG = "vless-ws-tls"

_REMOTE = r'''
import copy
import fcntl
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

PORT=__WS_PORT__
CONFIG=Path("/usr/local/etc/xray/config.json")
STATE=Path("/usr/local/etc/xray/twinpanel-modern-state.json")
LOCK=Path("/run/twinpanel-xray-ws-tls-v1.lock")
XRAY="/usr/local/bin/xray"
API="--server=127.0.0.1:10085"
TAG="vless-ws-tls"


def run(args, timeout=20):
    return subprocess.run(args, text=True, capture_output=True,
                          check=False, timeout=timeout)


def tags():
    result=run([XRAY,"api","lsi",API,"-isOnlyTags=true","-timeout=6"],
               timeout=10)
    if result.returncode:
        raise RuntimeError("XRAY_WS_API_TAG_QUERY_FAILED")
    try:
        response=json.loads(result.stdout)
        return {str(entry["tag"]) for entry in response["inbounds"]
                if isinstance(entry,dict)}
    except (ValueError,KeyError,TypeError):
        raise RuntimeError("XRAY_WS_API_TAG_RESPONSE_INVALID")


def listening():
    result=run(["ss","-H","-ltn",f"sport = :{PORT}"],timeout=8)
    return result.returncode==0 and bool(result.stdout.strip())


def valid_certificate(state):
    domain=str(state.get("tls_domain") or "").strip()
    cert=str(state.get("managed_cert") or "").strip()
    key=str(state.get("managed_key") or "").strip()
    if not domain or not cert or not key or not Path(cert).is_file() or not Path(key).is_file():
        raise RuntimeError("XRAY_WS_CERTIFICATE_NOT_READY")
    if run(["openssl","x509","-checkend","86400","-noout","-in",cert],
           timeout=9).returncode:
        raise RuntimeError("XRAY_WS_CERTIFICATE_EXPIRED")
    if run(["openssl","x509","-checkhost",domain,"-noout","-in",cert],
           timeout=9).returncode:
        raise RuntimeError("XRAY_WS_CERTIFICATE_DOMAIN_MISMATCH")
    return domain,cert,key


def verify_ws(item, *, domain):
    stream=item.get("streamSettings") or {}
    if (item.get("protocol")!="vless" or item.get("port")!=PORT
            or stream.get("network")!="ws" or stream.get("security")!="tls"):
        raise RuntimeError("XRAY_WS_EXISTING_INBOUND_MISMATCH")
    certs=(stream.get("tlsSettings") or {}).get("certificates") or []
    if not certs or not isinstance(certs[0],dict):
        raise RuntimeError("XRAY_WS_EXISTING_CERTIFICATE_MISSING")
    clients=(item.get("settings") or {}).get("clients")
    if not isinstance(clients,list):
        raise RuntimeError("XRAY_WS_EXISTING_CLIENTS_INVALID")
    return len(clients)


def repair():
    if not CONFIG.is_file() or not STATE.is_file():
        raise RuntimeError("XRAY_WS_CONFIG_OR_STATE_MISSING")
    if run(["systemctl","is-active","--quiet","xray"],timeout=8).returncode:
        raise RuntimeError("XRAY_WS_SERVICE_INACTIVE")
    original=CONFIG.read_bytes()
    metadata=CONFIG.stat()
    doc=json.loads(original)
    state=json.loads(STATE.read_text(encoding="utf-8"))
    if not state.get("tls_enabled"):
        raise RuntimeError("XRAY_WS_CERTIFICATE_NOT_READY")
    domain,cert,key=valid_certificate(state)
    inbounds=doc.get("inbounds")
    if not isinstance(inbounds,list):
        raise RuntimeError("XRAY_WS_INBOUNDS_INVALID")
    by_tag={entry.get("tag"):entry for entry in inbounds
            if isinstance(entry,dict)}
    live=tags()
    existing=by_tag.get(TAG)
    if isinstance(existing,dict):
        count=verify_ws(existing,domain=domain)
        if TAG not in live or not listening():
            raise RuntimeError("XRAY_WS_PERSISTED_NOT_LIVE")
        print(json.dumps({"ready":True,"changed":False,"clients":count},
                         separators=(",",":")))
        return
    if TAG in live:
        raise RuntimeError("XRAY_WS_LIVE_NOT_PERSISTED")
    if any(item.get("port")==PORT for item in inbounds if isinstance(item,dict)):
        raise RuntimeError("XRAY_WS_CONFIG_PORT_COLLISION")
    if listening():
        raise RuntimeError("XRAY_WS_SOCKET_PORT_COLLISION")

    baseline=by_tag.get("vless-xhttp-reality")
    if not isinstance(baseline,dict) or baseline.get("protocol")!="vless":
        raise RuntimeError("XRAY_WS_BASELINE_MISSING")
    original_clients=(baseline.get("settings") or {}).get("clients")
    if not isinstance(original_clients,list):
        raise RuntimeError("XRAY_WS_BASELINE_CLIENTS_INVALID")
    unique={}
    for client in original_clients:
        if not isinstance(client,dict):
            raise RuntimeError("XRAY_WS_BASELINE_CLIENT_MALFORMED")
        ident=str(client.get("id") or "").strip()
        email=str(client.get("email") or "").strip()
        if not ident or not email:
            raise RuntimeError("XRAY_WS_CLIENT_IDENTITY_MISSING")
        if email in unique and unique[email]!=ident:
            raise RuntimeError("XRAY_WS_CLIENT_IDENTITY_CONFLICT")
        unique[email]=ident

    path=str(state.get("ws_path") or "").strip()
    if not path.startswith("/") or len(path)<8:
        raise RuntimeError("XRAY_WS_PATH_INVALID")
    ws={
        "tag":TAG,
        "listen":"0.0.0.0",
        "port":PORT,
        "protocol":"vless",
        "settings":{
            "clients":[{"id":ident,"email":email,"level":0}
                       for email,ident in unique.items()],
            "decryption":"none",
        },
        "streamSettings":{
            "network":"ws",
            "security":"tls",
            "wsSettings":{"path":path},
            "tlsSettings":{
                "serverName":str(state.get("tls_sni_ws") or domain),
                "minVersion":"1.2",
                "alpn":["http/1.1"],
                "certificates":[{"certificateFile":cert,"keyFile":key}],
            },
        },
    }
    doc["inbounds"].append(ws)
    staged=None
    api_payload=None
    added=False
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",
                                         dir=CONFIG.parent,prefix=".ws-v1-",
                                         suffix=".json",delete=False) as output:
            staged=Path(output.name)
            json.dump(doc,output,ensure_ascii=False,indent=2)
            output.write("\n")
        os.chown(staged,metadata.st_uid,metadata.st_gid)
        os.chmod(staged,stat.S_IMODE(metadata.st_mode))
        check=run([XRAY,"run","-test","-config",str(staged)],timeout=30)
        if check.returncode:
            raise RuntimeError("XRAY_WS_FULL_CONFIG_TEST_FAILED")
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",
                                         prefix="tp-ws-tls-api-",
                                         suffix=".json",delete=False) as output:
            api_payload=Path(output.name)
            os.chmod(api_payload,0o600)
            json.dump({"inbounds":[ws]},output,ensure_ascii=False)
        issued=run([XRAY,"api","adi",API,"-timeout=20",str(api_payload)],
                   timeout=26)
        if issued.returncode:
            try:added=TAG in tags()
            except Exception:added=False
            raise RuntimeError("XRAY_WS_HOT_ADD_FAILED")
        added=True
        if TAG not in tags() or not listening():
            raise RuntimeError("XRAY_WS_HOT_ADD_NOT_LISTENING")
        if CONFIG.read_bytes()!=original:
            raise RuntimeError("XRAY_WS_CONCURRENT_CONFIG_CHANGE")
        backup=CONFIG.parent / ("config.json.bak-ws-tls-v1-"
                                +time.strftime("%Y%m%d-%H%M%S",time.gmtime()))
        shutil.copy2(CONFIG,backup)
        os.replace(staged,CONFIG)
        staged=None
        print(json.dumps({"ready":True,"changed":True,
                          "clients":len(unique),"port":PORT},
                         separators=(",",":")))
    except Exception:
        if added:
            removed=run([XRAY,"api","rmi",API,"-timeout=12",TAG],timeout=17)
            if removed.returncode:
                raise RuntimeError("XRAY_WS_HOT_ADD_ROLLBACK_FAILED")
        raise
    finally:
        if staged:staged.unlink(missing_ok=True)
        if api_payload:api_payload.unlink(missing_ok=True)


with LOCK.open("a+") as lock:
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
    repair()
'''


async def ensure_websocket_tls(conn, port: int) -> dict:
    """Install only a missing TLS WS inbound, without restarting Xray."""
    if not 1 <= int(port) <= 65535:
        raise ValueError("XRAY_WS_PORT_INVALID")
    script=_REMOTE.replace("__WS_PORT__",str(int(port)))
    payload=base64.b64encode(script.encode()).decode("ascii")
    raw=await provision.cmd(
        conn, "printf '%s' "+shlex.quote(payload)+" | base64 -d | python3",
        timeout=110,
    )
    try:
        result=json.loads(str(raw).strip().splitlines()[-1])
    except (IndexError,ValueError) as exc:
        raise RuntimeError("XRAY_WS_HOT_ADD_RESULT_INVALID") from exc
    if not isinstance(result,dict) or result.get("ready") is not True:
        raise RuntimeError("XRAY_WS_HOT_ADD_NOT_VERIFIED")
    await provision.ufw_allow(conn,int(port),"tcp")
    return result
