"""ShadowTLS identified V2 uses deterministic per-user auth without legacy changes."""
import base64
import copy
import json
import secrets
from types import SimpleNamespace
from unittest.mock import patch

from app.shadowtls_identity_v2 import (
    NODE_HELPER_SCRIPT,
    IDENTIFIED_INBOUND_TAG,
    IDENTIFIED_INNER_TAG,
    identified_user_key,
)
from app.singbox_subscription_accounts import (
    SingBoxAccountSecret,
    _batch_mutation_script,
    _mutation_script,
    client_item,
)


def _sample():
    return [
        {"type": "shadowtls", "tag": "twinpanel-shadowtls-in",
         "listen": "0.0.0.0", "listen_port": 8448, "version": 3,
         "strict_mode": True, "detour": "twinpanel-shadowtls-inner",
         "handshake": {"server": "www.microsoft.com", "server_port": 443},
         "users": [
             {"name": "tp-sub-1", "password": "outer-password-1"},
             {"name": "tp-sub-2", "password": "outer-password-2"},
         ]},
        {"type": "shadowsocks", "tag": "twinpanel-shadowtls-inner",
         "listen": "127.0.0.1", "method": "aes-256-gcm",
         "password": "legacy-shared-inner"},
    ]


def test():
    ns = {}
    exec(compile(NODE_HELPER_SCRIPT, "<identified-node-helper>", "exec"), ns)
    ins = _sample()
    original = copy.deepcopy(ins)
    state = {"shadowtls": {"inner_password": "legacy-shared-inner"}}
    port = ns["ensure_identified_shadowtls"](
        ins, state, "twinpanel-shadowtls-in", "twinpanel-shadowtls-inner"
    )
    assert port == 18448
    assert ins[:2] == original, "legacy public and private connection routes changed"
    identified = next(i for i in ins if i["tag"] == IDENTIFIED_INBOUND_TAG)
    inner = next(i for i in ins if i["tag"] == IDENTIFIED_INNER_TAG)
    assert identified["listen_port"] == 18448
    assert len(inner["users"]) == len(original[0]["users"])
    assert len({x["password"] for x in inner["users"]}) == 2
    key = state["shadowtls"]["identified_server_key"]
    assert identified_user_key(key, "tp-sub-1", "outer-password-1") == inner["users"][0]["password"]
    assert identified_user_key(key, "tp-sub-2", "outer-password-2") == inner["users"][1]["password"]
    first = copy.deepcopy(ins)
    ns["ensure_identified_shadowtls"](
        ins, state, "twinpanel-shadowtls-in", "twinpanel-shadowtls-inner"
    )
    assert ins == first, "provisioning must be idempotent"
    ins[0]["users"].pop()
    ns["ensure_identified_shadowtls"](
        ins, state, "twinpanel-shadowtls-in", "twinpanel-shadowtls-inner"
    )
    assert len(next(i for i in ins if i["tag"] == IDENTIFIED_INNER_TAG)["users"]) == 1
    assert ins[1] == original[1]
    for script in (
        _mutation_script("shadowtls", "tp-sub-1", {"name": "tp-sub-1", "password": "outer-password-1"}),
        _batch_mutation_script([SingBoxAccountSecret("shadowtls", "tp-sub-1", "outer-password-1")]),
    ):
        compile(script, "<generated-shadowtls-node-script>", "exec")
        assert "ensure_identified_shadowtls" in script

    fake_node = SimpleNamespace(id=6, name="test", host="127.0.0.1", public_ip="127.0.0.1", agent_url="127.0.0.1")
    legacy = original[0].copy()
    legacy["_twinpanel_shadowtls_inner"] = {
        "method": "aes-256-gcm", "password": "legacy-shared-inner"
    }
    identified_meta = {"port":18448,"method":inner["method"],"server_key":key,"users":["tp-sub-1"]}
    legacy["_twinpanel_shadowtls_identified"] = identified_meta
    secret = SingBoxAccountSecret("shadowtls", "tp-sub-1", "outer-password-1")
    with patch("app.singbox_subscription_accounts.SHADOWTLS_IDENTIFIED_ENABLED", True):
        item = client_item(fake_node,secret,legacy,server="127.0.0.1")
    config = json.loads(item["config"])
    assert item["port"] == 18448
    assert config["outbounds"][0]["method"] == "2022-blake3-aes-128-gcm"
    assert config["outbounds"][0]["password"] == (
        key + ":" + identified_user_key(key, "tp-sub-1", "outer-password-1")
    )
    assert config["outbounds"][1]["server_port"] == 18448
    with patch("app.singbox_subscription_accounts.SHADOWTLS_IDENTIFIED_ENABLED", False):
        old = client_item(fake_node,secret,legacy,server="127.0.0.1")
    assert old["port"] == 8448
    assert json.loads(old["config"])["outbounds"][0]["method"] == "aes-256-gcm"
    print("SHADOWTLS_PARALLEL_NONDESTRUCTIVE_IDENTITY_PASS")


if __name__ == "__main__":
    test()
