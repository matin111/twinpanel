from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request


API = __API_LITERAL__
NODE_ID = __NODE_ID__
SECRET = __SECRET_LITERAL__
AGENT_VERSION = "v33.1"
POLL_SECONDS = 10


def run(args, timeout=10):
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip()
    except Exception as exc:
        return 998, f"{type(exc).__name__}:{exc}"


def request(method, path, payload=None, timeout=12):
    data = None
    headers = {
        "X-Node-Secret": SECRET,
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        API.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def counters(dev):
    if not dev or not os.path.isdir("/sys/class/net/" + dev):
        return None
    output = {}
    for key in (
        "rx_packets",
        "tx_packets",
        "rx_bytes",
        "tx_bytes",
        "rx_errors",
        "tx_errors",
        "rx_dropped",
        "tx_dropped",
    ):
        try:
            with open(f"/sys/class/net/{dev}/statistics/{key}", "r", encoding="utf-8") as handle:
                output[key] = int(handle.read().strip())
        except Exception:
            output[key] = None
    return output


def delta(before, after):
    if not before or not after:
        return None
    output = {}
    for key in before:
        left = before.get(key)
        right = after.get(key)
        output[key] = right - left if isinstance(left, int) and isinstance(right, int) else None
    return output


def service_state(service):
    if not service:
        return {"ActiveState": "unknown", "SubState": "unknown", "query_rc": 127}
    code, text = run([
        "systemctl",
        "show",
        service,
        "--no-page",
        "--property=ActiveState,SubState,MainPID,NRestarts",
    ])
    result = {"query_rc": code}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def interface_state(iface):
    exists = bool(iface and os.path.isdir("/sys/class/net/" + iface))
    if not exists:
        return {"exists": False}

    mtu = None
    try:
        with open(f"/sys/class/net/{iface}/mtu", "r", encoding="utf-8") as handle:
            mtu = int(handle.read().strip())
    except Exception:
        pass

    _, addr = run(["ip", "-4", "-o", "addr", "show", "dev", iface])
    _, link = run(["ip", "-o", "link", "show", "dev", iface])
    return {
        "exists": True,
        "mtu": mtu,
        "addr": addr,
        "link": link,
        "counters": counters(iface),
    }


def listener_state(target):
    if not target.get("server") or not target.get("port"):
        return {"required": False, "present": None, "matches": []}

    protocol = str(target.get("protocol") or "")
    args = ["ss", "-H", "-lnup"] if protocol == "udp" else ["ss", "-H", "-lntp"]
    _, text = run(args)
    needle = ":" + str(target["port"])
    matches = [line for line in text.splitlines() if needle in line]
    return {
        "required": True,
        "present": bool(matches),
        "matches": matches[:8],
    }


def firewall_state(target):
    marker = target.get("firewall_marker")
    if not marker:
        return {"checked": False, "present": None, "matches": []}

    code, text = run(["iptables", "-S"])
    if code != 0:
        return {"checked": False, "present": None, "matches": []}

    matches = [line for line in text.splitlines() if str(marker) in line]
    if not matches and target.get("port"):
        needle = "--dport " + str(target["port"])
        matches = [line for line in text.splitlines() if needle in line]

    return {
        "checked": True,
        "present": bool(matches),
        "matches": matches[:12],
    }


def secret_digest(target):
    kind = target.get("secret_kind")
    path = target.get("secret_path")
    if not kind or not path:
        return {"checked": False, "present": None, "sha256": None}

    try:
        if kind == "file":
            with open(path, "rb") as handle:
                data = handle.read()
        elif kind == "mtunnel_config":
            with open(path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
            data = base64.b64decode(str(config.get("key") or ""))
        else:
            return {"checked": False, "present": None, "sha256": None}
        return {
            "checked": True,
            "present": True,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    except Exception:
        return {"checked": True, "present": False, "sha256": None}


def physical_interface(remote_public_ip):
    if not remote_public_ip:
        return None
    _, text = run(["ip", "-4", "route", "get", str(remote_public_ip)])
    match = re.search(r"\bdev\s+(\S+)", text)
    return match.group(1) if match else None


def peer_ping(target):
    iface = str(target.get("interface") or "")
    peer_ip = str(target.get("peer_ip") or "")
    if not iface or not os.path.isdir("/sys/class/net/" + iface):
        return {
            "rc": 127,
            "loss_pct": 100.0,
            "received": 0,
            "transmitted": 0,
            "latency_ms": None,
            "summary": "interface_missing",
        }

    code, text = run([
        "ping",
        "-I",
        iface,
        "-c",
        "4",
        "-W",
        "1",
        peer_ip,
    ], timeout=8)

    match = re.search(
        r"(\d+) packets transmitted, (\d+) received.*?(\d+(?:\.\d+)?)% packet loss",
        text,
        re.S,
    )
    tx = int(match.group(1)) if match else None
    rx = int(match.group(2)) if match else None
    loss = float(match.group(3)) if match else (0.0 if code == 0 else 100.0)
    latency_match = re.search(r"=\s*[0-9.]+/([0-9.]+)/", text)
    latency = round(float(latency_match.group(1)), 2) if latency_match else None

    return {
        "rc": code,
        "loss_pct": loss,
        "received": rx,
        "transmitted": tx,
        "latency_ms": latency,
        "summary": text[-1200:],
    }


def diagnose_target(target):
    iface = str(target.get("interface") or "")
    carrier_iface = str(target.get("carrier_interface") or "") or None
    physical = physical_interface(target.get("remote_public_ip"))

    before_iface = counters(iface)
    before_carrier = counters(carrier_iface)
    before_physical = counters(physical)

    ping = peer_ping(target)

    after_iface = counters(iface)
    after_carrier = counters(carrier_iface)
    after_physical = counters(physical)

    return {
        "ok": True,
        "service": service_state(str(target.get("service") or "")),
        "interface": interface_state(iface),
        "listener": listener_state(target),
        "firewall": firewall_state(target),
        "secret": secret_digest(target),
        "physical_interface": physical,
        "ping": ping,
        "counter_delta": {
            "interface": delta(before_iface, after_iface),
            "carrier": delta(before_carrier, after_carrier),
            "physical": delta(before_physical, after_physical),
        },
    }


def one_pass():
    desired = request(
        "GET",
        f"/v1/tunnel-diagnostics/node/{NODE_ID}/desired",
        timeout=12,
    )
    if not isinstance(desired, list):
        return

    for item in desired:
        if not isinstance(item, dict):
            continue
        tunnel_id = int(item.get("tunnel_id") or 0)
        if tunnel_id <= 0:
            continue

        diagnostics = {}
        for target in item.get("targets") or []:
            if not isinstance(target, dict):
                continue
            name = str(target.get("transport") or "").strip().lower()
            if not name:
                continue
            try:
                diagnostics[name] = diagnose_target(target)
            except Exception as exc:
                diagnostics[name] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}:{exc}"[:1200],
                }

        request(
            "POST",
            f"/v1/tunnel-diagnostics/tunnel/{tunnel_id}/node/{NODE_ID}/report",
            {
                "agent_version": AGENT_VERSION,
                "diagnostics": diagnostics,
            },
            timeout=12,
        )


def main():
    print(
        f"[TwinPanelDiagAgent] started node={NODE_ID} version={AGENT_VERSION}",
        flush=True,
    )
    while True:
        try:
            one_pass()
        except urllib.error.HTTPError as exc:
            print(
                f"[TwinPanelDiagAgent] HTTP {exc.code}: {exc.reason}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"[TwinPanelDiagAgent] {type(exc).__name__}: {exc}",
                flush=True,
            )
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
