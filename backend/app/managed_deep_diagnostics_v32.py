from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
from typing import Any

from sqlalchemy.orm import Session

from .models import Node, Tunnel, TunnelTransport
from .mtunnel_transport import mtunnel_runtime_values
from .routers.provision import ssh_connect_saved
from .tp2027_provision import backhaul_runtime_values, tp2027_runtime_values
from .transport_candidates.common import runtime as modern_runtime


V32_TRANSPORTS = (
    "kcp_2027",
    "mtunnel",
    "kernel_gre",
    "gost_tun",
)


_COUNTER_KEYS = (
    "rx_packets",
    "tx_packets",
    "rx_bytes",
    "tx_bytes",
    "rx_errors",
    "tx_errors",
    "rx_dropped",
    "tx_dropped",
)


def _db_row(db: Session, tunnel_id: int, name: str) -> dict[str, Any]:
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == name,
        )
        .first()
    )
    if row is None:
        return {
            "present": False,
            "enabled": False,
            "status": "not_installed",
            "latency_ms": None,
            "last_error": None,
        }
    return {
        "present": True,
        "enabled": bool(row.enabled),
        "status": str(row.status or ""),
        "latency_ms": row.latency_ms,
        "last_error": row.last_error,
        "last_healthy_at": row.last_healthy_at.isoformat() if row.last_healthy_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _runtime_for(name: str, tunnel_id: int) -> dict[str, Any]:
    if name == "kcp_2027":
        rt = dict(tp2027_runtime_values(name, tunnel_id))
        rt["carrier"] = dict(backhaul_runtime_values(tunnel_id))
        rt["secret_kind"] = "file"
        rt["secret_path"] = f"/etc/twinpanel/backhaul/{rt['interface']}.key"
        rt["server_role"] = "exit"
        rt["firewall_marker"] = f"TP2027-BH{int(tunnel_id)}-udp-{int(rt['port'])}"
        return rt

    if name == "mtunnel":
        rt = dict(mtunnel_runtime_values(tunnel_id))
        rt["iran_service"] = rt["service"]
        rt["exit_service"] = rt["service"]
        rt["protocol"] = "udp"
        rt["server_role"] = "exit"
        rt["secret_kind"] = "mtunnel_config"
        rt["secret_path"] = rt["config"]
        rt["firewall_marker"] = str(int(rt["port"]))
        return rt

    rt = dict(modern_runtime(name, tunnel_id))
    if name == "kernel_gre":
        rt["protocol"] = "gre"
        rt["server_role"] = None
        rt["firewall_marker"] = f"TwinPanel-GRE-{int(tunnel_id)}"
    elif name == "gost_tun":
        rt["protocol"] = "tcp"
        rt["server_role"] = "exit"
        rt["firewall_marker"] = f"TwinPanel-GOST-{int(tunnel_id)}"
    return rt


def _node_script(
    *,
    service: str,
    iface: str,
    source_ip: str,
    peer_ip: str,
    remote_public_ip: str,
    protocol: str,
    port: int | None,
    server: bool,
    firewall_marker: str | None,
    carrier_iface: str | None,
    secret_kind: str | None,
    secret_path: str | None,
) -> str:
    payload = {
        "service": service,
        "iface": iface,
        "source_ip": source_ip,
        "peer_ip": peer_ip,
        "remote_public_ip": remote_public_ip,
        "protocol": protocol,
        "port": port,
        "server": server,
        "firewall_marker": firewall_marker,
        "carrier_iface": carrier_iface,
        "secret_kind": secret_kind,
        "secret_path": secret_path,
        "counter_keys": list(_COUNTER_KEYS),
    }
    raw = json.dumps(payload, separators=(",", ":"))

    return f"""python3 - <<'PY'
import base64
import hashlib
import json
import os
import re
import subprocess

cfg=json.loads({raw!r})

def run(args, timeout=12):
    try:
        p=subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return {{"rc":p.returncode,"out":(p.stdout or "")[-5000:],"err":(p.stderr or "")[-2000:]}}
    except Exception as exc:
        return {{"rc":998,"out":"","err":type(exc).__name__+":"+str(exc)}}

def counters(dev):
    if not dev or not os.path.isdir('/sys/class/net/'+dev):
        return None
    out={{}}
    for key in cfg['counter_keys']:
        try:
            with open('/sys/class/net/'+dev+'/statistics/'+key) as h:
                out[key]=int(h.read().strip())
        except Exception:
            out[key]=None
    return out

def service_state():
    r=run(['systemctl','show',cfg['service'],'--no-page','--property=ActiveState,SubState,MainPID,NRestarts'])
    data={{}}
    for line in r['out'].splitlines():
        if '=' in line:
            k,v=line.split('=',1); data[k]=v
    data['query_rc']=r['rc']
    return data

def iface_state():
    dev=cfg['iface']
    exists=os.path.isdir('/sys/class/net/'+dev)
    if not exists:
        return {{"exists":False}}
    mtu=None
    try:
        with open('/sys/class/net/'+dev+'/mtu') as h: mtu=int(h.read().strip())
    except Exception: pass
    addr=run(['ip','-4','-o','addr','show','dev',dev])
    link=run(['ip','-o','link','show','dev',dev])
    return {{"exists":True,"mtu":mtu,"addr":addr['out'].strip(),"link":link['out'].strip(),"counters":counters(dev)}}

def listener_state():
    if not cfg['server'] or not cfg['port']:
        return {{"required":False,"present":None,"matches":[]}}
    proto=cfg['protocol']
    args=['ss','-H','-lnup'] if proto=='udp' else ['ss','-H','-lntp']
    r=run(args)
    needle=':'+str(cfg['port'])
    matches=[line for line in r['out'].splitlines() if needle in line]
    return {{"required":True,"present":bool(matches),"matches":matches[:8]}}

def firewall_state():
    marker=cfg.get('firewall_marker')
    if not marker:
        return {{"checked":False,"present":None,"matches":[]}}
    r=run(['iptables','-S'])
    if r['rc'] not in (0,):
        return {{"checked":False,"present":None,"matches":[]}}
    matches=[line for line in r['out'].splitlines() if marker in line]
    if not matches and cfg.get('port'):
        p='--dport '+str(cfg['port'])
        matches=[line for line in r['out'].splitlines() if p in line]
    return {{"checked":True,"present":bool(matches),"matches":matches[:12]}}

def secret_digest():
    kind=cfg.get('secret_kind'); path=cfg.get('secret_path')
    if not kind or not path:
        return {{"checked":False,"present":None,"sha256":None}}
    try:
        if kind=='file':
            data=open(path,'rb').read()
        elif kind=='mtunnel_config':
            obj=json.load(open(path,'r'))
            data=base64.b64decode(str(obj.get('key') or ''))
        else:
            return {{"checked":False,"present":None,"sha256":None}}
        return {{"checked":True,"present":True,"sha256":hashlib.sha256(data).hexdigest()}}
    except Exception:
        return {{"checked":True,"present":False,"sha256":None}}

def physical_iface():
    ip=cfg.get('remote_public_ip')
    if not ip: return None
    r=run(['ip','-4','route','get',ip])
    m=re.search(r'\\bdev\\s+(\\S+)',r['out'])
    return m.group(1) if m else None

def peer_ping():
    if not os.path.isdir('/sys/class/net/'+cfg['iface']):
        return {{"rc":127,"loss_pct":100.0,"received":0,"transmitted":0,"latency_ms":None,"summary":"interface_missing"}}
    r=run(['ping','-I',cfg['iface'],'-c','4','-W','1',cfg['peer_ip']],timeout=8)
    text=(r['out']+'\\n'+r['err'])[-2500:]
    m=re.search(r'(\\d+) packets transmitted, (\\d+) received.*?(\\d+(?:\\.\\d+)?)% packet loss',text,re.S)
    tx=int(m.group(1)) if m else None
    rx=int(m.group(2)) if m else None
    loss=float(m.group(3)) if m else (0.0 if r['rc']==0 else 100.0)
    lm=re.search(r'=\\s*[0-9.]+/([0-9.]+)/',text)
    lat=round(float(lm.group(1)),2) if lm else None
    return {{"rc":r['rc'],"loss_pct":loss,"received":rx,"transmitted":tx,"latency_ms":lat,"summary":text[-1200:]}}

phy=physical_iface()
before={{"iface":counters(cfg['iface']),"carrier":counters(cfg.get('carrier_iface')),"physical":counters(phy)}}
ping=peer_ping()
after={{"iface":counters(cfg['iface']),"carrier":counters(cfg.get('carrier_iface')),"physical":counters(phy)}}

print(json.dumps({{
  "service":service_state(),
  "interface":iface_state(),
  "listener":listener_state(),
  "firewall":firewall_state(),
  "secret":secret_digest(),
  "route_to_peer":run(['ip','-4','route','get',cfg['peer_ip'],'from',cfg['source_ip']])['out'].strip(),
  "physical_interface":phy,
  "ping":ping,
  "counters_before":before,
  "counters_after":after,
}},separators=(',',':')))
PY"""


async def _inspect_side(conn, **kwargs) -> dict[str, Any]:
    result = await conn.run(
        _node_script(**kwargs),
        check=False,
        timeout=35,
    )
    if result.exit_status != 0:
        return {
            "ok": False,
            "error": ((result.stderr or "") + "\n" + (result.stdout or ""))[-3000:],
        }
    try:
        data = json.loads((result.stdout or "").strip())
    except Exception as exc:
        return {
            "ok": False,
            "error": f"invalid_diag_json:{type(exc).__name__}:{exc}",
        }
    data["ok"] = True
    return data


def _delta(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, int | None] | None:
    if not before or not after:
        return None
    out: dict[str, int | None] = {}
    for key in _COUNTER_KEYS:
        a = before.get(key)
        b = after.get(key)
        out[key] = (int(b) - int(a)) if isinstance(a, int) and isinstance(b, int) else None
    return out


def _add_deltas(side: dict[str, Any]) -> None:
    before = side.get("counters_before") or {}
    after = side.get("counters_after") or {}
    side["counter_delta"] = {
        "interface": _delta(before.get("iface"), after.get("iface")),
        "carrier": _delta(before.get("carrier"), after.get("carrier")),
        "physical": _delta(before.get("physical"), after.get("physical")),
    }


def _service_active(side: dict[str, Any]) -> bool:
    return str(((side.get("service") or {}).get("ActiveState") or "")).lower() == "active"


def _iface_exists(side: dict[str, Any]) -> bool:
    return bool(((side.get("interface") or {}).get("exists")))


def _listener_ok(side: dict[str, Any]) -> bool:
    listener = side.get("listener") or {}
    return (not listener.get("required")) or bool(listener.get("present"))


def _ping_ok(side: dict[str, Any]) -> bool:
    ping = side.get("ping") or {}
    try:
        return int(ping.get("received") or 0) > 0 and float(ping.get("loss_pct") or 100.0) < 100.0
    except Exception:
        return False


def _secret_match(iran: dict[str, Any], exit_side: dict[str, Any]) -> bool | None:
    left = iran.get("secret") or {}
    right = exit_side.get("secret") or {}
    if not left.get("checked") and not right.get("checked"):
        return None
    if not left.get("present") or not right.get("present"):
        return False
    return bool(left.get("sha256") and left.get("sha256") == right.get("sha256"))


def _classify(name: str, iran: dict[str, Any], exit_side: dict[str, Any], secret_match: bool | None) -> tuple[str, str]:
    if not iran.get("ok") or not exit_side.get("ok"):
        return "diagnostic_unavailable", "Deep diagnostic could not complete on both nodes."
    if not _service_active(iran) or not _service_active(exit_side):
        return "service_down", "At least one transport service is not active."
    if not _iface_exists(iran) or not _iface_exists(exit_side):
        return "interface_missing", "At least one transport interface is missing."
    if not _listener_ok(exit_side):
        return "listener_missing", "The expected Exit-side listener is not present."
    fw = exit_side.get("firewall") or {}
    if fw.get("checked") and fw.get("present") is False:
        return "firewall_rule_missing", "The transport-specific inbound firewall rule is missing."
    if secret_match is False:
        return "secret_mismatch", "Peer key material is missing or does not match."

    iran_ok = _ping_ok(iran)
    exit_ok = _ping_ok(exit_side)
    if iran_ok and exit_ok:
        return "healthy", "Bidirectional peer L3 is healthy."
    if iran_ok != exit_ok:
        return "one_way_peer_loss", "Peer L3 works in only one direction."

    if name == "kcp_2027":
        return "kcp_dataplane_stalled", "KCP service/interface/listener/key checks pass, but peer L3 remains at 100% loss."
    if name == "mtunnel":
        return "mtunnel_udp_dataplane_stalled", "MTunnel service/interface/key checks pass, but UDP-backed peer L3 remains at 100% loss."
    if name == "kernel_gre":
        return "gre_dataplane_blocked", "GRE services/interfaces exist, but protocol-47 peer L3 remains unavailable."
    if name == "gost_tun":
        return "gost_dataplane_stalled", "GOST listener/services/interfaces exist, but TUN peer L3 remains unavailable."
    return "peer_l3_loss", "Peer L3 remains unavailable."


async def deep_diagnose_transport(
    tunnel_id: int,
    name: str,
    db: Session,
) -> dict[str, Any]:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")
    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise RuntimeError("tunnel_nodes_missing")

    rt = _runtime_for(name, int(tunnel_id))
    carrier = rt.get("carrier") or {}
    carrier_iface = carrier.get("interface")

    ci = ce = None
    try:
        ci, ce = await asyncio.gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
        )
        common = {
            "iface": str(rt["interface"]),
            "protocol": str(rt.get("protocol") or ""),
            "port": int(rt["port"]) if rt.get("port") is not None else None,
            "firewall_marker": rt.get("firewall_marker"),
            "carrier_iface": str(carrier_iface) if carrier_iface else None,
            "secret_kind": rt.get("secret_kind"),
            "secret_path": rt.get("secret_path"),
        }
        iran_kwargs = {
            **common,
            "service": str(rt.get("iran_service") or rt.get("service") or ""),
            "source_ip": str(rt["iran_ip"]),
            "peer_ip": str(rt["exit_ip"]),
            "remote_public_ip": str(exit_node.public_ip),
            "server": str(rt.get("server_role") or "") == "iran",
        }
        exit_kwargs = {
            **common,
            "service": str(rt.get("exit_service") or rt.get("service") or ""),
            "source_ip": str(rt["exit_ip"]),
            "peer_ip": str(rt["iran_ip"]),
            "remote_public_ip": str(iran.public_ip),
            "server": str(rt.get("server_role") or "") == "exit",
        }
        iran_diag, exit_diag = await asyncio.gather(
            _inspect_side(ci, **iran_kwargs),
            _inspect_side(ce, **exit_kwargs),
        )
        _add_deltas(iran_diag)
        _add_deltas(exit_diag)
        secret_match = _secret_match(iran_diag, exit_diag)
        code, summary = _classify(name, iran_diag, exit_diag, secret_match)
        for side in (iran_diag, exit_diag):
            secret = side.get("secret") or {}
            secret.pop("sha256", None)
        return {
            "transport": name,
            "db": _db_row(db, int(tunnel_id), name),
            "runtime": {
                "interface": rt.get("interface"),
                "iran_ip": rt.get("iran_ip"),
                "exit_ip": rt.get("exit_ip"),
                "port": rt.get("port"),
                "protocol": rt.get("protocol"),
                "carrier_interface": carrier_iface,
            },
            "root_cause_code": code,
            "summary": summary,
            "secret_match": secret_match,
            "iran": iran_diag,
            "exit": exit_diag,
        }
    finally:
        for conn in (ci, ce):
            if conn is not None:
                conn.close()
                await conn.wait_closed()


async def deep_diagnose_managed_tunnel(
    tunnel_id: int,
    db: Session,
) -> dict[str, Any]:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    output: list[dict[str, Any]] = []
    for name in V32_TRANSPORTS:
        row = _db_row(db, int(tunnel_id), name)
        if not row.get("present"):
            continue
        try:
            item = await deep_diagnose_transport(int(tunnel_id), name, db)
        except Exception as exc:
            item = {
                "transport": name,
                "db": row,
                "root_cause_code": "diagnostic_error",
                "summary": f"{type(exc).__name__}: {str(exc)[:1600]}",
            }
        output.append(item)

    return {
        "ok": True,
        "read_only": True,
        "tunnel_id": int(tunnel_id),
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "transports": output,
        "unhealthy": [
            item["transport"]
            for item in output
            if item.get("root_cause_code") != "healthy"
        ],
        "marker": "TWINPANEL_MANAGED_DEEP_DIAGNOSTICS_V32_ACTIVE",
    }
