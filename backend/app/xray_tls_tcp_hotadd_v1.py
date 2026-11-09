"""Safely hot-add one missing VLESS TCP+TLS inbound; no Xray restart.

The old v39 reconciler rewrote config.json and restarted Xray to add TCP TLS,
disconnecting all existing customers. This uses the already-proven Xray
HandlerService AddInbound API, validates full config before the API call,
verifies the live tag/listener, and atomically persists only after success.
WebSocket TLS and TCP TLS share one config lock.
"""
from __future__ import annotations

import base64
import json
import shlex

from .routers import provision

TAG = "vless-tcp-tls"

_REMOTE = r'''
import fcntl
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

PORT=__TCP_TLS_PORT__
CONFIG=Path("/usr/local/etc/xray/config.json")
STATE=Path("/usr/local/etc/xray/twinpanel-modern-state.json")
LOCK=Path("/run/twinpanel-xray-ws-tls-v1.lock")
XRAY="/usr/local/bin/xray"
API="--server=127.0.0.1:10085"
TAG="vless-tcp-tls"


def run(args, timeout=20):
    return subprocess.run(args, text=True, capture_output=True,
                          check=False, timeout=timeout)


def live_tags():
    result=run([XRAY,"api","lsi",API,"-isOnlyTags=true","-timeout=6"],timeout=10)
    if result.returncode:
        raise RuntimeError("XRAY_TCP_TLS_API_TAG_QUERY_FAILED")
    try:
        response=json.loads(result.stdout)
        return {str(item["tag"]) for item in response.get("inbounds",[])
                if isinstance(item,dict)}
    except (ValueError,TypeError,KeyError):
        raise RuntimeError("XRAY_TCP_TLS_API_TAG_RESPONSE_INVALID")


def listening():
    result=run(["ss","-H","-ltn",f"sport = :{PORT}"],timeout=8)
    return result.returncode == 0 and bool(result.stdout.strip())


def verified_certificate(state):
    if state.get("tls_enabled") is not True:
        raise RuntimeError("XRAY_TCP_TLS_NOT_ENABLED")
    domain=str(state.get("tls_domain") or "").strip().lower()
    hostname=str(state.get("tls_sni_tcp") or domain).strip().lower()
    cert=str(state.get("managed_cert") or "").strip()
    key=str(state.get("managed_key") or "").strip()
    if not domain or not hostname or not cert or not key:
        raise RuntimeError("XRAY_TCP_TLS_CERTIFICATE_NOT_READY")
    if not Path(cert).is_file() or not Path(key).is_file():
        raise RuntimeError("XRAY_TCP_TLS_CERTIFICATE_FILE_MISSING")
    if run(["openssl","x509","-checkend","86400","-noout","-in",cert],
           timeout=9).returncode:
        raise RuntimeError("XRAY_TCP_TLS_CERTIFICATE_EXPIRED")
    for target in (domain,hostname):
        match=run(["openssl","x509","-checkhost",target,"-noout","-in",cert],timeout=9)
        # OpenSSL returns success even when its stdout explicitly says
        # "does NOT match certificate". Never trust returncode alone.
        if (match.returncode or
                f"Hostname {target} does match certificate" not in match.stdout):
            raise RuntimeError("XRAY_TCP_TLS_CERTIFICATE_DOMAIN_MISMATCH")
    pubcert=run(["openssl","x509","-in",cert,"-pubkey","-noout"],timeout=9)
    pubkey=run(["openssl","pkey","-in",key,"-pubout"],timeout=9)
    if pubcert.returncode or pubkey.returncode or pubcert.stdout!=pubkey.stdout:
        raise RuntimeError("XRAY_TCP_TLS_CERTIFICATE_KEY_MISMATCH")
    return domain,hostname,cert,key


def repair():
    if not CONFIG.is_file() or not STATE.is_file():
        raise RuntimeError("XRAY_TCP_TLS_CONFIG_OR_STATE_MISSING")
    if run(["systemctl","is-active","--quiet","xray"],timeout=8).returncode:
        raise RuntimeError("XRAY_TCP_TLS_SERVICE_INACTIVE")
    original=CONFIG.read_bytes()
    metadata=CONFIG.stat()
    doc=json.loads(original)
    state=json.loads(STATE.read_text(encoding="utf-8"))
    domain,hostname,cert,key=verified_certificate(state)
    inbounds=doc.get("inbounds")
    if not isinstance(inbounds,list):
        raise RuntimeError("XRAY_TCP_TLS_INBOUNDS_INVALID")
    by_tag={entry.get("tag"):entry for entry in inbounds if isinstance(entry,dict)}
    live=live_tags()
    present=by_tag.get(TAG)
    if present is not None:
        stream=present.get("streamSettings") or {}
        certs=(stream.get("tlsSettings") or {}).get("certificates") or []
        if (present.get("protocol")!="vless"
                or present.get("port")!=PORT
                or stream.get("network")!="tcp"
                or stream.get("security")!="tls"
                or (stream.get("tlsSettings") or {}).get("serverName")!=hostname
                or not certs
                or certs[0].get("certificateFile")!=cert
                or certs[0].get("keyFile")!=key
                or not isinstance((present.get("settings") or {}).get("clients"),list)):
            raise RuntimeError("XRAY_TCP_TLS_EXISTING_INBOUND_MISMATCH")
        if TAG not in live or not listening():
            raise RuntimeError("XRAY_TCP_TLS_PERSISTED_NOT_LIVE")
        print(json.dumps({"ready":True,"changed":False,
                          "clients":len(present["settings"]["clients"])},
                         separators=(",",":")))
        return
    if TAG in live:
        raise RuntimeError("XRAY_TCP_TLS_LIVE_NOT_PERSISTED")
    if any(item.get("port")==PORT for item in inbounds if isinstance(item,dict)):
        raise RuntimeError("XRAY_TCP_TLS_CONFIG_PORT_COLLISION")
    if listening():
        raise RuntimeError("XRAY_TCP_TLS_SOCKET_PORT_COLLISION")

    baseline=by_tag.get("vless-xhttp-reality")
    if not isinstance(baseline,dict) or baseline.get("protocol")!="vless":
        raise RuntimeError("XRAY_TCP_TLS_BASELINE_MISSING")
    source=(baseline.get("settings") or {}).get("clients")
    if not isinstance(source,list):
        raise RuntimeError("XRAY_TCP_TLS_BASELINE_CLIENTS_INVALID")
    identities={}
    for item in source:
        if not isinstance(item,dict):
            raise RuntimeError("XRAY_TCP_TLS_BASELINE_CLIENT_MALFORMED")
        identity=str(item.get("id") or "").strip()
        email=str(item.get("email") or "").strip()
        if not email or not identity:
            raise RuntimeError("XRAY_TCP_TLS_CLIENT_IDENTITY_MISSING")
        if email in identities and identities[email]!=identity:
            raise RuntimeError("XRAY_TCP_TLS_CLIENT_IDENTITY_CONFLICT")
        identities[email]=identity
    inbound={
        "tag":TAG,
        "listen":"0.0.0.0",
        "port":PORT,
        "protocol":"vless",
        "settings":{
            "clients":[{"id":identity,"email":email,"level":0}
                       for email,identity in identities.items()],
            "decryption":"none",
        },
        "streamSettings":{
            "network":"tcp",
            "security":"tls",
            "tlsSettings":{
                "serverName":hostname,
                "minVersion":"1.2",
                "alpn":["http/1.1"],
                "certificates":[{"certificateFile":cert,"keyFile":key}],
            },
        },
    }
    if str(state.get("vless_tcp_congestion") or "").lower()=="bbr":
        inbound["streamSettings"]["sockopt"]={"tcpcongestion":"bbr"}
    doc["inbounds"].append(inbound)
    staged=None
    api_payload=None
    added=False
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",encoding="utf-8",dir=CONFIG.parent,
            prefix=".tcp-tls-v1-",suffix=".json",delete=False
        ) as output:
            staged=Path(output.name)
            json.dump(doc,output,ensure_ascii=False,indent=2)
            output.write("\n")
        os.chown(staged,metadata.st_uid,metadata.st_gid)
        os.chmod(staged,stat.S_IMODE(metadata.st_mode))
        check=run([XRAY,"run","-test","-config",str(staged)],timeout=30)
        if check.returncode:
            raise RuntimeError("XRAY_TCP_TLS_FULL_CONFIG_TEST_FAILED")

        with tempfile.NamedTemporaryFile(
            mode="w",encoding="utf-8",
            prefix="tp-tcp-tls-api-",suffix=".json",delete=False
        ) as output:
            api_payload=Path(output.name)
            os.chmod(api_payload,0o600)
            json.dump({"inbounds":[inbound]},output,ensure_ascii=False)

        result=run([XRAY,"api","adi",API,"-timeout=20",str(api_payload)],
                   timeout=26)
        if result.returncode:
            try:added=TAG in live_tags()
            except Exception:added=False
            raise RuntimeError("XRAY_TCP_TLS_HOT_ADD_FAILED")
        added=True
        if TAG not in live_tags() or not listening():
            raise RuntimeError("XRAY_TCP_TLS_HOT_ADD_NOT_LISTENING")
        if CONFIG.read_bytes()!=original:
            raise RuntimeError("XRAY_TCP_TLS_CONCURRENT_CONFIG_CHANGE")
        backup=CONFIG.parent / (
            "config.json.bak-tcp-tls-hot-v1-"
            +time.strftime("%Y%m%d-%H%M%S",time.gmtime())
        )
        shutil.copy2(CONFIG,backup)
        os.replace(staged,CONFIG)
        staged=None
        print(json.dumps({
            "ready":True,"changed":True,
            "clients":len(identities),"port":PORT,
        },separators=(",",":")))
    except Exception:
        if added:
            undone=run([XRAY,"api","rmi",API,"-timeout=12",TAG],timeout=17)
            if undone.returncode:
                raise RuntimeError("XRAY_TCP_TLS_HOT_ADD_ROLLBACK_FAILED")
        raise
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
        if api_payload is not None:
            api_payload.unlink(missing_ok=True)


# Shared with the WS TLS helper to serialize both writers on config.json.
with LOCK.open("a+") as lock:
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
    repair()
'''


async def ensure_tcp_tls(conn, port: int) -> dict:
    """Return verified TCP+TLS availability without restarting Xray."""
    if not 1 <= int(port) <= 65535:
        raise ValueError("XRAY_TCP_TLS_PORT_INVALID")
    script=_REMOTE.replace("__TCP_TLS_PORT__",str(int(port)))
    payload=base64.b64encode(script.encode()).decode("ascii")
    raw=await provision.cmd(
        conn, "printf '%s' "+shlex.quote(payload)+" | base64 -d | python3",
        timeout=110,
    )
    try:
        result=json.loads(str(raw).strip().splitlines()[-1])
    except (IndexError,ValueError) as exc:
        raise RuntimeError("XRAY_TCP_TLS_HOT_ADD_RESULT_INVALID") from exc
    if not isinstance(result,dict) or result.get("ready") is not True:
        raise RuntimeError("XRAY_TCP_TLS_HOT_ADD_NOT_VERIFIED")
    await provision.ufw_allow(conn,int(port),"tcp")
    return result
