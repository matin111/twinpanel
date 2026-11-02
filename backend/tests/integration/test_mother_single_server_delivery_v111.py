from types import SimpleNamespace

from app.models import NodeType
from app.routers import central_account_delivery_runtime_v3 as runtime


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class _DB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *args, **kwargs):
        return _Query(self.rows)


def test_snapshot_nodes_preserve_mother_for_provisioning(monkeypatch):
    mother = SimpleNamespace(id=1, node_type=NodeType.EXIT, agent_url="local://core")
    exit_node = SimpleNamespace(id=5, node_type=NodeType.EXIT, agent_url="https://agent.example.invalid")
    db = _DB([mother, exit_node])
    sub = SimpleNamespace(id=10)

    result = runtime.subscription_snapshot_nodes(db, sub)

    assert [node.id for node in result] == [1, 5]


def test_customer_delivery_does_not_hide_mother_before_multilink(monkeypatch):
    monkeypatch.setattr(runtime, "_ORIGINAL_DELIVERY_ITEM_IS_USABLE", lambda _db, _protocol, _item: True)

    assert runtime.customer_delivery_item_is_usable(
        object(),
        "openvpn",
        {"node_id": 1},
    ) is True
