import json
from types import SimpleNamespace

from app.routers.modern_account_delivery_v1 import _bind_unique_client_tags


def _node(node_id: int, name: str):
    return SimpleNamespace(id=node_id, name=name)


def test_naive_tag_uses_subscription_protocol_and_node_identity():
    item = {
        "config": json.dumps(
            {
                "outbounds": [
                    {
                        "type": "naive",
                        "tag": "twinpanel-naive",
                        "server": "203.0.113.10",
                        "server_port": 32005,
                        "username": "mv17_14",
                        "password": "keep-secret",
                    }
                ],
                "route": {"final": "twinpanel-naive"},
            }
        ),
        "outbound": {
            "type": "naive",
            "tag": "twinpanel-naive",
            "server": "203.0.113.10",
            "server_port": 32005,
        },
    }

    result = _bind_unique_client_tags(
        item,
        node=_node(5, "usa"),
        protocol="naive",
        username="mv17_14",
    )
    config = json.loads(result["config"])

    assert config["outbounds"][0]["tag"] == "mv17_14-naive-usa-n5"
    assert config["route"]["final"] == "mv17_14-naive-usa-n5"
    assert result["outbound"]["tag"] == "mv17_14-naive-usa-n5"
    assert config["outbounds"][0]["password"] == "keep-secret"


def test_same_user_naive_tags_are_unique_across_nodes():
    def make(node_id: int, name: str):
        item = {
            "config": json.dumps(
                {
                    "outbounds": [{"type": "naive", "tag": "twinpanel-naive"}],
                    "route": {"final": "twinpanel-naive"},
                }
            ),
            "outbound": {"type": "naive", "tag": "twinpanel-naive"},
        }
        result = _bind_unique_client_tags(
            item,
            node=_node(node_id, name),
            protocol="naive",
            username="mv17_14",
        )
        return json.loads(result["config"])["route"]["final"]

    assert make(5, "usa") != make(6, "tr")


def test_shadowtls_main_transport_detour_and_final_share_unique_identity():
    item = {
        "config": json.dumps(
            {
                "outbounds": [
                    {
                        "type": "shadowsocks",
                        "tag": "twinpanel-shadowtls",
                        "method": "aes-256-gcm",
                        "password": "inner-secret",
                        "detour": "twinpanel-shadowtls-transport",
                    },
                    {
                        "type": "shadowtls",
                        "tag": "twinpanel-shadowtls-transport",
                        "server": "203.0.113.10",
                        "server_port": 33005,
                        "password": "outer-secret",
                    },
                ],
                "route": {"final": "twinpanel-shadowtls"},
            }
        ),
        "outbound": {
            "type": "shadowtls",
            "tag": "twinpanel-shadowtls-transport",
            "server": "203.0.113.10",
            "server_port": 33005,
        },
    }

    result = _bind_unique_client_tags(
        item,
        node=_node(5, "usa"),
        protocol="shadowtls",
        username="mv17_14",
    )
    config = json.loads(result["config"])
    proxy, transport = config["outbounds"]

    assert proxy["tag"] == "mv17_14-shadowtls-usa-n5"
    assert transport["tag"] == "mv17_14-shadowtls-usa-n5-transport"
    assert proxy["detour"] == transport["tag"]
    assert config["route"]["final"] == proxy["tag"]
    assert result["outbound"]["tag"] == transport["tag"]
    assert proxy["password"] == "inner-secret"
    assert transport["password"] == "outer-secret"


def test_tag_sanitization_never_embeds_password_and_keeps_node_id_unique():
    item = {
        "config": json.dumps(
            {
                "outbounds": [{"type": "naive", "tag": "twinpanel-naive"}],
                "route": {},
            }
        ),
        "outbound": {"type": "naive", "tag": "twinpanel-naive"},
    }

    result = _bind_unique_client_tags(
        item,
        node=_node(9, "DE / Frankfurt #1"),
        protocol="naive",
        username="user@example.com",
    )
    tag = json.loads(result["config"])["route"]["final"]

    assert tag == "user-example-com-naive-DE-Frankfurt-1-n9"
    assert "password" not in tag.lower()
