"""Read-only fast path contract: profile-only scope and session cleanup."""
from pathlib import Path
import ast
from typing import Any

SOURCE=Path(__file__).resolve().parents[1]/"app/routers/public_connection_files_v9.py"
code=SOURCE.read_text(encoding="utf-8")
tree=ast.parse(code)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_active_payload")

class HTTPException(Exception):
    def __init__(self,status_code,detail): self.status_code=status_code;self.detail=detail

class FakeSub:
    class status:
        value="active"

class FakeDb:
    def __init__(self): self.info={}

calls=[]
def stored_info(db,sub):
    calls.append(db.info.get("_tp_public_feed_only_protocol"))
    return {"credentials":[{"protocol":"openvpn","items":[{"config":"config"}]}]}

def disambiguate(info): info["checked"]=True

scope={"Any":Any,"Session":object,"HTTPException":HTTPException,
 "_subscription_from_share_token":lambda token,db:FakeSub(),
 "_stored_info":stored_info,"disambiguate_openvpn_filenames":disambiguate}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),scope)
active=scope["_active_payload"]

def test_only_selected_protocol():
    db=FakeDb();db.info["_tp_download_only_protocol_v1"]="openvpn"
    result=active("fake-token",db)
    assert calls==["openvpn"]
    assert result["checked"]
    assert "_tp_public_feed_only_protocol" not in db.info

def test_previous_context_restored():
    db=FakeDb();db.info.update(_tp_download_only_protocol_v1="wireguard",_tp_public_feed_only_protocol="v2ray")
    result=active("fake-token",db)
    assert result["credentials"]
    assert db.info["_tp_public_feed_only_protocol"]=="v2ray"

def test_status_validation_retained():
    original=scope["_subscription_from_share_token"]
    scope["_subscription_from_share_token"]=lambda token,db:type("Inactive",(),{"status":"expired"})()
    try:
        try:active("expired-token",FakeDb())
        except HTTPException as exc:assert exc.status_code==403
        else:raise AssertionError("Inactive subscription was accepted")
    finally:scope["_subscription_from_share_token"]=original

if __name__=="__main__":
    test_only_selected_protocol()
    test_previous_context_restored()
    test_status_validation_retained()
    print("PUBLIC_CONFIG_FASTPATH_SMOKE_OK")
