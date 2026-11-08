"""Authoritative, read-only Xray node profile discovery for central bulk sync.

Never bootstrap a new Exit from another subscriber's completed profile.
Only public connection metadata leaves the node; private REALITY keys, TLS
private keys, configuration, and existing client records never do.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import shlex
import uuid
from urllib.parse import quote, urlencode

from . import xray_modern_runtime as xr
from .xray_adaptive_three_profiles_v47 import _tcp_reality_uri
from .xray_tcp_tls_v39 import _tcp_tls_public_port, _tcp_tls_target_port

# This code executes on the authorized node over its saved management SSH.
# Only an allowlisted subset of non-secret fields is emitted.
_PUBLIC_PROBE = r'''
import json
import re
from pathlib import Path

state_file=Path("/usr/local/etc/xray/twinpanel-modern-state.json")
config_file=Path("/usr/local/etc/xray/config.json")
if not state_file.is_file() or not config_file.is_file():
    raise SystemExit("XRAY_NODE_STATE_MISSING")
state=json.loads(state_file.read_text(encoding="utf-8"))
config=json.loads(config_file.read_text(encoding="utf-8"))
if not isinstance(state,dict) or not isinstance(config,dict):
    raise SystemExit("XRAY_NODE_STATE_INVALID")
inbounds={i.get("tag"):i for i in config.get("inbounds",[])
          if isinstance(i,dict) and i.get("protocol")=="vless"}

def must(tag,network,security):
    inbound=inbounds.get(tag)
    stream=inbound.get("streamSettings") if isinstance(inbound,dict) else None
    if (not isinstance(stream,dict) or stream.get("network")!=network
            or stream.get("security")!=security
            or not isinstance(inbound.get("port"),int)
            or not 1<=inbound["port"]<=65535):
        raise SystemExit("XRAY_NODE_PROFILE_NOT_READY")
    return stream

def required(key):
    val=state.get(key)
    if not isinstance(val,str) or not val.strip():
        raise SystemExit("XRAY_NODE_PUBLIC_STATE_INCOMPLETE")
    return val.strip()

def domain(value):
    if (not re.fullmatch(r"[A-Za-z0-9.-]{4,253}",value)
            or ".." in value or value.startswith(".") or value.endswith(".")):
        raise SystemExit("XRAY_NODE_HOST_INVALID")
    return value

xhttp=must("vless-xhttp-reality","xhttp","reality")
if xhttp.get("xhttpSettings",{}).get("path")!=required("xhttp_path"):
    raise SystemExit("XRAY_NODE_XHTTP_PATH_MISMATCH")
reality=xhttp.get("realitySettings") or {}
name=domain(required("reality_server_name"))
sid=required("short_id_xhttp")
if (name not in reality.get("serverNames",[])
        or sid not in reality.get("shortIds",[])
        or not reality.get("privateKey")):
    raise SystemExit("XRAY_NODE_REALITY_STATE_MISMATCH")
public_key=required("reality_password")
if not re.fullmatch(r"[A-Za-z0-9_-]{40,64}",public_key):
    raise SystemExit("XRAY_NODE_PUBLIC_KEY_INVALID")
tls_enabled=bool(state.get("tls_enabled"))
tls_domain=state.get("tls_domain") if tls_enabled else ""
if tls_enabled:
    tls_domain=domain(required("tls_domain"))
    ws=must("vless-ws-tls","ws","tls")
    tcp=must("vless-tcp-tls","tcp","tls")
    if ws.get("wsSettings",{}).get("path")!=required("ws_path"):
        raise SystemExit("XRAY_NODE_WS_PATH_MISMATCH")
    if (not ws.get("tlsSettings",{}).get("certificates")
            or not tcp.get("tlsSettings",{}).get("certificates")):
        raise SystemExit("XRAY_NODE_TLS_NOT_READY")
    profiles=["websocket_tls","xhttp_reality","tcp_tls"]
else:
    tcp=must("vless-tcp-reality","tcp","reality")
    settings=tcp.get("realitySettings") or {}
    if name not in settings.get("serverNames",[]) or sid not in settings.get("shortIds",[]):
        raise SystemExit("XRAY_NODE_TCP_REALITY_MISMATCH")
    profiles=["xhttp_reality","tcp_reality"]
print(json.dumps({
    "profiles":profiles,"reality_server_name":name,
    "reality_password":public_key,"short_id_xhttp":sid,
    "xhttp_path":state["xhttp_path"],"tls_enabled":tls_enabled,
    "tls_domain":tls_domain,
    "tls_sni_ws":str(state.get("tls_sni_ws") or tls_domain) if tls_enabled else "",
    "tls_sni_tcp":str(state.get("tls_sni_tcp") or tls_domain) if tls_enabled else "",
    "ws_path":str(state.get("ws_path") or "") if tls_enabled else "",
},separators=(",",":")))
'''

_SUPPORTED = frozenset({"xhttp_reality","tcp_reality","websocket_tls","tcp_tls"})


def validate_public_authority(authority: dict) -> frozenset[str]:
    """Reject missing, unexpected or unsafe metadata before generating links."""
    if not isinstance(authority,dict):
        raise RuntimeError("XRAY_NODE_PUBLIC_AUTHORITY_INVALID")
    profiles=authority.get("profiles")
    if not isinstance(profiles,list) or len(profiles)!=len(set(profiles)):
        raise RuntimeError("XRAY_NODE_PROFILE_SET_INVALID")
    actual=frozenset(profiles)
    expected=(frozenset({"websocket_tls","xhttp_reality","tcp_tls"})
              if authority.get("tls_enabled") is True else
              frozenset({"xhttp_reality","tcp_reality"}))
    if actual != expected or not actual.issubset(_SUPPORTED):
        raise RuntimeError("XRAY_NODE_PROFILE_SET_INVALID")
    for key in ("xhttp_path","reality_password","reality_server_name","short_id_xhttp"):
        value=authority.get(key)
        if not isinstance(value,str) or not value:
            raise RuntimeError("XRAY_NODE_PUBLIC_AUTHORITY_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,64}",authority["reality_password"]):
        raise RuntimeError("XRAY_NODE_PUBLIC_KEY_INVALID")
    return actual


async def read_node_public_authority(conn) -> dict:
    """One remote read-only probe per node/batch, no user credentials returned."""
    encoded=base64.b64encode(_PUBLIC_PROBE.encode()).decode("ascii")
    command="printf '%s' "+shlex.quote(encoded)+" | base64 -d | python3"
    result=await asyncio.wait_for(conn.run(command,check=False,timeout=45),timeout=50)
    if result.exit_status:
        raise RuntimeError("XRAY_NODE_PUBLIC_PROBE_FAILED")
    try:
        authority=json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError,IndexError,TypeError) as exc:
        raise RuntimeError("XRAY_NODE_PUBLIC_PROBE_RESPONSE_INVALID") from exc
    validate_public_authority(authority)
    return authority


def _endpoint(db,node,profile):
    if profile in {"xhttp_reality","websocket_tls"}:
        return xr._profile_endpoint(db,node,profile)
    from .routers import account_delivery as ad
    host, legacy_port=ad._tunnel_access_endpoint(db,node,"v2ray")
    base_port=int(ad._port(db,node.id,"v2ray"))
    if profile=="tcp_reality":
        # V47 allocates the TCP REALITY target at base+1005.
        from .xray_adaptive_three_profiles_v47 import (
            _tcp_reality_public_port, _tcp_reality_target_port,
        )
        public=_tcp_reality_public_port(node.id)
        target=_tcp_reality_target_port(base_port)
    elif profile=="tcp_tls":
        public=_tcp_tls_public_port(node.id)
        target=_tcp_tls_target_port(base_port)
    else:
        raise RuntimeError("XRAY_NODE_PROFILE_UNSUPPORTED")
    return host,(public if int(legacy_port)==23000+int(node.id) else target)


def build_item_from_node_authority(db,node,*,client_uuid:str,
                                   account_label:str,authority:dict)->dict:
    """Build a per-user delivery from applied node public state, not a user."""
    profiles_required=validate_public_authority(authority)
    ident=str(uuid.UUID(str(client_uuid)))
    if not account_label or len(account_label)>100:
        raise ValueError("XRAY_ACCOUNT_LABEL_INVALID")
    chosen=("websocket_tls","xhttp_reality","tcp_tls") if authority["tls_enabled"] else (
        "xhttp_reality","tcp_reality")
    rendered=[]
    for key in chosen:
        host,port=_endpoint(db,node,key)
        if not host or not 1<=int(port)<=65535:
            raise RuntimeError("XRAY_NODE_PUBLIC_ENDPOINT_INVALID")
        if key in ("xhttp_reality","websocket_tls"):
            uri=xr._build_uri(profile=key,client_id=ident,host=host,
                              port=int(port),profile_name=account_label,state=authority)
        elif key=="tcp_reality":
            uri=_tcp_reality_uri(
                client_id=ident,host=host,port=int(port),
                profile_name=account_label,
                sni=authority["reality_server_name"],
                public_key=authority["reality_password"],
                short_id=authority["short_id_xhttp"])
        else:
            tls_name=authority["tls_sni_tcp"] or authority["tls_domain"]
            query=urlencode([
                ("encryption","none"),("security","tls"),("type","tcp"),
                ("sni",tls_name),("fp","chrome"),("alpn","http/1.1")])
            uri=f"vless://{ident}@{host}:{int(port)}?{query}#{quote(account_label+'-VLESS-TCP-TLS',safe='')}"
        metadata=({"tcp_reality":("VLESS TCP Reality","reality","tcp"),
                   "tcp_tls":("VLESS TCP TLS","tls","tcp")}.get(key))
        if metadata is None:
            meta=xr.PROFILE_META[key]
            metadata=(meta["title"],meta["security"],meta["transport"])
        rendered.append({
            "id":key,"title":metadata[0],"recommended":key=="xhttp_reality",
            "security":metadata[1],"transport":metadata[2],
            "server":host,"port":int(port),"uri":uri,
            "sni":(authority["tls_sni_ws"] or authority["tls_domain"]
                   if key=="websocket_tls" else
                   authority["tls_sni_tcp"] or authority["tls_domain"]
                   if key=="tcp_tls" else authority["reality_server_name"]),
        })
    if {p["id"] for p in rendered}!=profiles_required:
        raise RuntimeError("XRAY_NODE_PROFILE_BUILD_INCOMPLETE")
    first=next(p for p in rendered if p["recommended"])
    return {
        "node_id":int(node.id),"node":node.name,
        "server":first["server"],"server_ip":first["server"],
        "port":first["port"],"uuid":ident,"profile":first["id"],
        "security":first["security"],"transport":first["transport"],
        "uri":first["uri"],"profiles":rendered,
        "tls_available":authority["tls_enabled"],
        "legacy_plain_preserved":True,
    }
