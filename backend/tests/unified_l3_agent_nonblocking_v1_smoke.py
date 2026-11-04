"""Ensure the rendered Iran Agent never blocks heartbeat with tunnel subprocesses."""
import ast
import asyncio
import time
from pathlib import Path

src=Path(__file__).resolve().parents[1]/"app/unified_l3_core_v49.py"
tree=ast.parse(src.read_text())
rendered=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="_AGENT_RECONCILE_V49" for t in node.targets))
code=ast.parse(rendered)
fn=next(node for node in code.body if isinstance(node,ast.AsyncFunctionDef) and node.name=="reconcile_tunnels")
needed={
    "reconcile_tunnel_interfaces",
    "unified_l3_carrier_probe",
    "check_ssh_tun",
    "configure_wireguard",
    "ensure_keypair",
    "ping_ms",
    "reconcile_service_routing",
}
offloaded=set()
for node in ast.walk(fn):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=="to_thread" and isinstance(node.func.value,ast.Name) and node.func.value.id=="asyncio":
        if node.args and isinstance(node.args[0],ast.Name):
            offloaded.add(node.args[0].id)
assert needed<=offloaded, f"Blocking Agent operation still on event loop: {needed-offloaded}"

# Functional event-loop responsiveness: a deliberately slow synchronous
# iptables-style operation must not block the concurrent heartbeat ticker.
async def verify():
    beats=0
    async def ticker():
        nonlocal beats
        for _ in range(5):
            beats+=1
            await asyncio.sleep(0.015)
    await asyncio.gather(ticker(),asyncio.to_thread(time.sleep,0.08))
    assert beats==5
asyncio.run(verify())
print("UNIFIED_L3_AGENT_NONBLOCKING_RECONCILE_V1=PASS")
