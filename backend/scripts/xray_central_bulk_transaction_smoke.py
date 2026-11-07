"""Verify Xray bulk profile factory and atomic central persistence contract."""
from copy import deepcopy
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit,parse_qs
from uuid import uuid4

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app.xray_bulk_profile_factory_v1 import build_node_item_from_template

old=str(uuid4())
new=str(uuid4())
template={"node_id":13,"uuid":old,"server":"tunel1.in88.sbs",
          "server_ip":"tunel1.in88.sbs","port":24013,
          "profiles":[
              {"id":pid,"server":"tunel1.in88.sbs","port":port,
               "recommended":k==0,"sni":"example.org",
               "uri":f"vless://{old}@tunel1.in88.sbs:{port}?security=reality&pbk=PUBLIC_KEY&sid=001#{pid}"}
              for k,(pid,port) in enumerate(
                (("xhttp_reality",24013),("tcp_reality",38013)))
          ]}
template["uri"]=template["profiles"][0]["uri"]
before=deepcopy(template)
item=build_node_item_from_template(
    template,node_id=13,template_uuid=old,
    client_uuid=new,account_label="bulk-canary",
    required_profile_ids={"xhttp_reality","tcp_reality"})
assert template==before
assert item["uuid"]==new
assert item["node_id"]==13
assert {x["id"] for x in item["profiles"]}=={"xhttp_reality","tcp_reality"}
for orig,now in zip(template["profiles"],item["profiles"]):
    original_url=urlsplit(orig["uri"])
    fresh=urlsplit(now["uri"])
    assert fresh.username==new
    assert fresh.hostname==original_url.hostname
    assert fresh.port==original_url.port
    assert fresh.query==original_url.query
    assert old not in fresh.geturl()
    assert now["sni"]==orig["sni"]
    assert fresh.fragment.startswith("bulk-canary")
assert item["uri"]==item["profiles"][0]["uri"]
for mutation in (
    lambda x:x.update({"node_id":11}),
    lambda x:x["profiles"].pop(),
    lambda x:x["profiles"][0].update({"uri":"vless://evil@tunel1.in88.sbs:24013"}),
    lambda x:x["profiles"][0].update({"port":9999}),
):
    bad=deepcopy(template);mutation(bad)
    try:
        build_node_item_from_template(bad,node_id=13,template_uuid=old,
                                     client_uuid=new,account_label="safe",
                                     required_profile_ids={"xhttp_reality","tcp_reality"})
    except (ValueError,TypeError):
        pass
    else:
        raise AssertionError("malformed template incorrectly accepted")
runner=(root/"scripts/twinpanel_xray_bulk_pilot_v1.py").read_text("utf8")
compile(runner,"runner","exec")
assert "build_node_item_from_template(" in runner
assert ".with_for_update().one_or_none()" in runner
assert "current.append(prepared[sid])" in runner
assert runner.count("db.commit()")==1
assert "reusable_connection=conn" not in runner
assert "new_account_work_has_priority()" in runner
assert "if not apply or not chosen:" in runner
assert "if node_id != 13:" in runner
assert "if len(chosen) > 10:" in runner
print("XRAY_CENTRAL_BULK_SINGLE_TRANSACTION_SMOKE_PASS")
