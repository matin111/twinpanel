"""Guard TLS-ready Xray nodes against accidental domainless TCP Reality reconfiguration."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"backend/app/xray_adaptive_three_profiles_v47.py"
tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
functions=[
    node for node in tree.body
    if isinstance(node,ast.AsyncFunctionDef)
    and node.name in {"_ensure_modern_xray_v47","_xray_account_modern_v47"}
]
assert len(functions)==2
ctx={
    "_effective_domain":lambda node:"",
    "_original_ensure_modern_xray":None,
    "_original_xray_account_modern":None,
}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(SOURCE),"exec"),ctx)

async def test_tls_node():
    state={"tls_enabled":True,"available_profiles":["xhttp_reality","websocket_tls"]}
    async def original_ensure(*args,**kwargs):
        return state
    async def original_item(*args,**kwargs):
        return {"node_id":7,"tls_available":True,"profiles":[{"id":"websocket_tls"}]}
    ctx["_original_ensure_modern_xray"]=original_ensure
    ctx["_original_xray_account_modern"]=original_item
    node=SimpleNamespace(id=7)  # ORM model lacks xray_domain attribute.
    result=await ctx["_ensure_modern_xray_v47"](None,8443,node)
    assert result is state, "TLS node was unexpectedly sent through TCP Reality installer"
    item=await ctx["_xray_account_modern_v47"](None,node,None,None,"not-a-real-id")
    assert item["tls_available"] is True
    assert len(item["profiles"])==1
    print("XRAY_TLS_READY_WITHOUT_ORM_DOMAIN_SMOKE=PASS")

asyncio.run(test_tls_node())
