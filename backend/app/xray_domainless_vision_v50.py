"""Third secure domainless Xray profile: VLESS TCP REALITY + XTLS Vision.

Why this exists:
- legacy VLESS TCP on port 8443 has security=none and must NEVER be public;
- a domainless Xray Exit previously had only two safe profiles (XHTTP and TCP
  REALITY) although a third legacy inbound existed;
- this module adds an actually distinct *secure* Vision inbound without
  replacing existing clients, reusing their UUIDs, or restarting Xray.

The node-local installer uses HandlerService AddInbound (xray api adi), checks
the live listener and registered tag, and atomically persists only the new
inbound after both checks succeed. Existing inbounds are immutable.

A TLS-enabled Exit already has three safe customer profiles (WS TLS, XHTTP
REALITY, TCP TLS); it must not be modified by the domainless installer.
"""
from __future__ import annotations

import asyncio
import base64
import json
import shlex
from typing import Any
from urllib.parse import quote, urlencode

from . import (
    tunnel_service_connections_admin_runtime,
    xray_adaptive_three_profiles_v47 as v47,
    xray_modern_admin, xray_modern_repair_runtime,
    xray_modern_runtime as xr, xray_profile_reconcile_v36,
    xray_public_delivery_runtime,
)
from .models import Node, NodeProtocolConfig
from .routers import account_delivery, provision, tunnels

PROFILE = "tcp_reality_vision"
TAG = "vless-tcp-reality-vision"
FLOW = "xtls-rprx-vision"
TARGET_OFFSET = 1010       # 9453 with default base port; not gRPC's +1006.
PUBLIC_BASE = 39000        # per-node Iran port, no overlap with +38000 TCP.
_applied = False
_original_ensure = None
_original_account = None
_original_admin_rows = None
_original_admin_status = None
_original_routes = None
_original_customer_order = None


def target_port(base: int) -> int:
    result = int(base) + TARGET_OFFSET
    if not 1 <= result <= 65535:
        raise RuntimeError("XRAY_VISION_TARGET_PORT_INVALID")
    return result


def public_port(node_id: int) -> int:
    if not 1 <= int(node_id) <= 999:
        raise RuntimeError("XRAY_VISION_NODE_ID_OUT_OF_RANGE")
    return PUBLIC_BASE + int(node_id)


def build_uri(
    *, client_id: str, host: str, port: int,
    name: str, sni: str, public_key: str, short_id: str,
) -> str:
    query = urlencode([
        ("encryption", "none"), ("security", "reality"),
        ("type", "tcp"), ("flow", FLOW),
        ("sni", sni), ("fp", "chrome"),
        ("pbk", public_key), ("sid", short_id),
    ])
    label = quote(name + "-VLESS-TCP-VISION", safe="")
    return f"vless://{client_id}@{host}:{int(port)}?{query}#{label}"


def _install_script(port: int) -> str:
    """No remote key/user material is returned to the control plane."""
    if not 1 <= int(port) <= 65535:
        raise ValueError("invalid port")
    return _REMOTE_INSTALL.replace("__VISION_PORT__", str(int(port)))


_REMOTE_INSTALL = r'''
import copy
import fcntl
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import time
from pathlib import Path

PORT = __VISION_PORT__
TAG = "vless-tcp-reality-vision"
FLOW = "xtls-rprx-vision"
CONFIG = Path("/usr/local/etc/xray/config.json")
STATE = Path("/usr/local/etc/xray/twinpanel-modern-state.json")
LOCK = Path("/run/twinpanel-xray-vision-v50.lock")
XRAY = "/usr/local/bin/xray"
SERVER = "--server=127.0.0.1:10085"


def run(args, *, timeout=18):
    return subprocess.run(args, text=True, capture_output=True,
                          check=False, timeout=timeout)


def live_tags():
    result=run([XRAY, "api", "lsi", SERVER, "-isOnlyTags=true", "-timeout=6"], timeout=9)
    if result.returncode:
        raise RuntimeError("XRAY_VISION_API_INBOUND_LIST_FAILED")
    try:
        payload=json.loads(result.stdout)
        return {str(x["tag"]) for x in payload["inbounds"] if isinstance(x, dict)}
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("XRAY_VISION_API_TAGS_INVALID") from exc


def listening():
    result=run(["ss", "-H", "-ltn", f"sport = :{PORT}"], timeout=8)
    return result.returncode==0 and bool(result.stdout.strip())


def do_install():
    if not CONFIG.is_file() or not STATE.is_file():
        raise RuntimeError("XRAY_VISION_STATE_MISSING")
    if run(["systemctl", "is-active", "--quiet", "xray"],timeout=7).returncode:
        raise RuntimeError("XRAY_VISION_XRAY_INACTIVE")
    original=CONFIG.read_bytes()
    info=CONFIG.stat()
    doc=json.loads(original)
    state=json.loads(STATE.read_text())
    if state.get("tls_enabled"):
        print(json.dumps({"ready":False,"reason":"tls_exit_uses_three_tls_profiles"}))
        return
    inbounds=doc.get("inbounds")
    if not isinstance(inbounds,list):
        raise RuntimeError("XRAY_VISION_INBOUNDS_INVALID")
    by_tag={x.get("tag"):x for x in inbounds if isinstance(x,dict)}
    baseline=by_tag.get("vless-tcp-reality")
    xhttp=by_tag.get("vless-xhttp-reality")
    if not isinstance(baseline,dict) or not isinstance(xhttp,dict):
        raise RuntimeError("XRAY_VISION_BASELINE_INCOMPLETE")
    stream=baseline.get("streamSettings") or {}
    if (baseline.get("protocol")!="vless" or stream.get("network")!="tcp"
            or stream.get("security")!="reality"):
        raise RuntimeError("XRAY_VISION_BASELINE_UNSAFE")
    original_clients=baseline.get("settings",{}).get("clients")
    if not isinstance(original_clients,list):
        raise RuntimeError("XRAY_VISION_BASELINE_USERS_INVALID")
    if any(not isinstance(u,dict) or not u.get("id") or not u.get("email")
           for u in original_clients):
        raise RuntimeError("XRAY_VISION_CLIENT_MISSING_IDENTITY")
    by_email={u["email"]:u for u in original_clients}
    if len(by_email)!=len(original_clients):
        raise RuntimeError("XRAY_VISION_BASELINE_DUPLICATE_EMAIL")
    vision=copy.deepcopy(baseline)
    vision["tag"]=TAG
    vision["port"]=PORT
    vision["settings"]["clients"]=[
        {**copy.deepcopy(u),"flow":FLOW} for u in original_clients
    ]
    existing=by_tag.get(TAG)
    current_tags=live_tags()
    if isinstance(existing,dict):
        if (existing.get("port")!=PORT or
                (existing.get("streamSettings") or {}).get("network")!="tcp" or
                (existing.get("streamSettings") or {}).get("security")!="reality"):
            raise RuntimeError("XRAY_VISION_EXISTING_INBOUND_MISMATCH")
        existing_clients=existing.get("settings",{}).get("clients")
        if not isinstance(existing_clients,list) or any(
            not isinstance(u,dict) or u.get("flow")!=FLOW
            for u in existing_clients
        ):
            raise RuntimeError("XRAY_VISION_EXISTING_CLIENT_FLOW_INVALID")
        if TAG not in current_tags or not listening():
            raise RuntimeError("XRAY_VISION_PERSISTED_BUT_NOT_LIVE")
        print(json.dumps({"ready":True,"changed":False,
                          "clients":len(existing_clients)},separators=(",",":")))
        return
    if TAG in current_tags:
        raise RuntimeError("XRAY_VISION_LIVE_NOT_PERSISTED")
    if any(i.get("port")==PORT for i in inbounds if isinstance(i,dict)):
        raise RuntimeError("XRAY_VISION_CONFIG_PORT_COLLISION")
    if listening():
        raise RuntimeError("XRAY_VISION_SOCKET_PORT_COLLISION")

    doc["inbounds"].append(vision)
    staged=None
    add_payload=None
    added=False
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",encoding="utf-8",dir=CONFIG.parent,
            prefix=".vision-v50-",suffix=".json",delete=False
        ) as output:
            staged=Path(output.name)
            json.dump(doc,output,indent=2,ensure_ascii=False)
            output.write("\n")
        os.chown(staged,info.st_uid,info.st_gid)
        os.chmod(staged,stat.S_IMODE(info.st_mode))
        validated=run([XRAY,"run","-test","-config",str(staged)],timeout=27)
        if validated.returncode:
            raise RuntimeError("XRAY_VISION_CONFIG_TEST_FAILED")
        with tempfile.NamedTemporaryFile(
            mode="w",encoding="utf-8",prefix="tp-vision-api-",
            suffix=".json",delete=False
        ) as output:
            add_payload=Path(output.name)
            os.chmod(add_payload,0o600)
            json.dump({"inbounds":[vision]},output,ensure_ascii=False)
        added_response=run([
            XRAY,"api","adi",SERVER,"-timeout=18",str(add_payload)
        ],timeout=23)
        if added_response.returncode:
            raise RuntimeError("XRAY_VISION_HOT_ADD_FAILED")
        added=True
        if TAG not in live_tags() or not listening():
            raise RuntimeError("XRAY_VISION_LIVE_VERIFICATION_FAILED")
        if CONFIG.read_bytes()!=original:
            raise RuntimeError("XRAY_VISION_CONCURRENT_CONFIG_CHANGE")
        stamp=time.strftime("%Y%m%d-%H%M%S",time.gmtime())
        backup=CONFIG.parent/f"config.json.bak-vision-v50-{stamp}"
        shutil.copy2(CONFIG,backup)
        os.replace(staged,CONFIG)
        staged=None
        print(json.dumps({"ready":True,"changed":True,
                          "clients":len(original_clients)},separators=(",",":")))
    except Exception:
        if added:
            removed=run([XRAY,"api","rmi",SERVER,"-timeout=12",TAG],timeout=17)
            if removed.returncode:
                raise RuntimeError("XRAY_VISION_ROLLBACK_FAILED")
        raise
    finally:
        if staged:staged.unlink(missing_ok=True)
        if add_payload:add_payload.unlink(missing_ok=True)


with LOCK.open("a+") as stream:
    fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
    do_install()
'''


async def prepare_domainless_vision(conn, base_port: int) -> dict[str, Any]:
    """Idempotent hot-add on node, without calling the legacy Xray installer.

    Return a clean TLS skip when the node already has three TLS profiles.
    Never alter existing VLESS listeners or restart Xray for paid users.
    """
    script = _install_script(target_port(base_port))
    encoded = base64.b64encode(script.encode()).decode()
    result = await provision.cmd(
        conn, "printf '%s' " + shlex.quote(encoded)
        + " | base64 -d | python3", timeout=90,
    )
    try:
        response = json.loads(result.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError("XRAY_VISION_REMOTE_RESPONSE_INVALID") from exc
    if not isinstance(response,dict):
        raise RuntimeError("XRAY_VISION_REMOTE_RESPONSE_INVALID")
    if response.get("ready") is True:
        await provision.ufw_allow(conn, target_port(base_port), "tcp")
    elif response.get("reason") != "tls_exit_uses_three_tls_profiles":
        raise RuntimeError("XRAY_VISION_LIVE_INSTALL_NOT_VERIFIED")
    return response


async def ensure_modern_xray_v50(conn, base_port: int, node=None, *,
                               bootstrap_done: bool = False):
    assert _original_ensure is not None
    state = await _original_ensure(
        conn, base_port, node, bootstrap_done=bootstrap_done,
    )
    if bool(state.get("tls_enabled")):
        return state
    # The mother/core is diagnostics-only during the Exit-node rollout.
    # Never introduce a new Xray listener there as a side effect of purchases.
    if node is not None and (
        bool(getattr(node,"is_mother",False))
        or bool(getattr(node,"is_local_core",False))
        or getattr(node,"agent_url",None)=="local://core"
    ):
        return state
    verified = await prepare_domainless_vision(conn, base_port)
    if verified.get("ready") is not True:
        raise RuntimeError("XRAY_VISION_LIVE_INSTALL_NOT_VERIFIED")
    available = list(state.get("available_profiles") or [])
    if PROFILE not in available:
        available.append(PROFILE)
    state["available_profiles"] = available
    return state


def _customer_order_v50(item: dict[str,Any]) -> tuple[str,...]:
    assert _original_customer_order is not None
    original = _original_customer_order(item)
    if original and original[0] == xr.PROFILE_WS:
        return original
    profiles=item.get("profiles")
    if (isinstance(profiles,list) and
        any(isinstance(p,dict) and p.get("id")==PROFILE and p.get("uri")
            for p in profiles)):
        return (*original, PROFILE)
    return original


async def _account_modern_v50(db,node,sub,user,client_id:str, *,
                             reusable_connection=None):
    assert _original_account is not None
    item = await _original_account(
        db,node,sub,user,client_id,
        reusable_connection=reusable_connection,
    )
    if (item.get("tls_available") or v47._effective_domain(node)
            or bool(getattr(node,"is_mother",False))
            or bool(getattr(node,"is_local_core",False))
            or getattr(node,"agent_url",None)=="local://core"):
        return item
    profiles=item.get("profiles")
    if not isinstance(profiles,list) or not any(
        isinstance(p,dict) and p.get("id")==v47.PROFILE_TCP_REALITY
        for p in profiles
    ):
        raise RuntimeError("XRAY_VISION_BASE_PROFILE_MISSING")
    host,port=xr._profile_endpoint(db,node,PROFILE)
    sni,pbk,sid=v47._reality_values_from_xhttp(profiles)
    name=str(sub.account_username or f"user{sub.id}")[:100]
    uri=build_uri(
        client_id=client_id,host=host,port=port,name=name,
        sni=sni,public_key=pbk,short_id=sid,
    )
    profiles.append({
        "id":PROFILE,"title":"VLESS TCP Reality Vision",
        "recommended":False,"security":"reality","transport":"tcp",
        "flow":FLOW,"server":host,"port":int(port),"uri":uri,"sni":sni,
    })
    return item


def _routes_v50(db,exit_node,exit_tunnel_ip:str)->list[dict]:
    assert _original_routes is not None
    routes=list(_original_routes(db,exit_node,exit_tunnel_ip))
    if (bool(getattr(exit_node,"is_mother",False))
            or bool(getattr(exit_node,"is_local_core",False))
            or getattr(exit_node,"agent_url",None)=="local://core"):
        return routes
    if v47._effective_domain_from_db(db,exit_node):
        return routes
    cfg=db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id==int(exit_node.id),
        NodeProtocolConfig.protocol=="v2ray",
    ).first()
    if (cfg is None or
        str(getattr(cfg.status,"value",cfg.status)).lower()!="online"):
        return routes
    if any(r.get("profile")==PROFILE and r.get("protocol")=="v2ray"
           for r in routes if isinstance(r,dict)):
        return routes
    base=int(cfg.port or account_delivery.DEFAULT_PORTS["v2ray"])
    routes.append({
        "protocol":"v2ray","profile":PROFILE,
        "exit_node_id":int(exit_node.id),
        "public_port":public_port(int(exit_node.id)),
        "target_ip":exit_tunnel_ip,
        "target_port":target_port(base),
        "transport":"tcp","client_subnet":None,
    })
    return routes


def _admin_rows_v50(node,base_port:int)->list[dict]:
    assert _original_admin_rows is not None
    rows=list(_original_admin_rows(node,base_port))
    if v47._effective_domain(node):
        return rows
    if not any(str(x.get("id") or "")==PROFILE for x in rows):
        rows.append({
            "id":PROFILE,"title":"VLESS TCP Reality Vision",
            "security":"reality","transport":"tcp","recommended":False,
            "requires_tls_domain":False,
            "target_port":target_port(base_port),
            "tunnel_public_port":public_port(node.id),
        })
    return rows


async def _admin_status_v50(conn,base_port:int)->dict[str,Any]:
    assert _original_admin_status is not None
    state=dict(await _original_admin_status(conn,base_port))
    profiles=dict(state.get("profiles") or {})
    profiles[PROFILE]=bool(
        await provision.listener(conn,target_port(base_port),"tcp")
    )
    state["profiles"]=profiles
    return state


def reattach_service_routes_v50_after_v87()->None:
    global _original_routes
    current=tunnels._service_routes_for_exit
    if current is _routes_v50:
        return
    _original_routes=current
    tunnels._service_routes_for_exit=_routes_v50


def apply_xray_domainless_vision_v50()->None:
    global _applied,_original_ensure,_original_account
    global _original_admin_rows,_original_admin_status
    global _original_routes,_original_customer_order
    if _applied:
        return
    _original_ensure=xr._ensure_modern_xray
    _original_account=xr._xray_account_modern
    _original_admin_rows=xray_modern_admin._profile_rows
    _original_admin_status=xray_modern_admin._status_remote
    _original_routes=tunnels._service_routes_for_exit
    _original_customer_order=v47._customer_order_for_item
    xr.PROFILE_META[PROFILE]={
        "offset":TARGET_OFFSET,"public_base":PUBLIC_BASE,
        "title":"VLESS TCP Reality Vision","transport":"tcp",
        "security":"reality","recommended":False,
    }
    xr._ensure_modern_xray=ensure_modern_xray_v50
    xr._xray_account_modern=_account_modern_v50
    account_delivery._xray=_account_modern_v50
    v47._customer_order_for_item=_customer_order_v50
    xray_public_delivery_runtime._PROFILE_LABELS[PROFILE]="TCP Reality Vision"
    xray_modern_admin._profile_rows=_admin_rows_v50
    xray_modern_admin._status_remote=_admin_status_v50
    xray_modern_repair_runtime._ensure_modern_xray=ensure_modern_xray_v50
    tunnel_service_connections_admin_runtime._current_xray_status_remote=_admin_status_v50
    tunnel_service_connections_admin_runtime._XRAY_PROFILE_TITLES[
        PROFILE
    ]="VLESS TCP Reality Vision"
    tunnels._service_routes_for_exit=_routes_v50
    _applied=True
    print(
        "TWINPANEL_XRAY_THREE_SAFE_V50_ACTIVE "
        "domainless=xhttp_reality,tcp_reality,tcp_reality_vision "
        "tls=websocket_tls,xhttp_reality,tcp_tls "
        "hot_add_inbound=1 no_global_restart=1 legacy_plain_hidden=1",
        flush=True,
    )
