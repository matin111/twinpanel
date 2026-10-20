from types import SimpleNamespace

from app.models import Node
from app import mother_subscription_delivery_policy_v108 as policy


class _Query:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _DB:
    def __init__(self, *, reseller_row=None, nodes=None):
        self.reseller_row = reseller_row
        self.nodes = nodes or {}

    def query(self, *args, **kwargs):
        return _Query(self.reseller_row)

    def get(self, model, key):
        if model is Node:
            return self.nodes.get(int(key))
        return None


def _node(node_id: int, *, mother: bool):
    return SimpleNamespace(
        id=node_id,
        is_mother=mother,
    )


def test_direct_subscription_uses_admin_policy():
    db = _DB(reseller_row=None)
    sub = SimpleNamespace(id=10)

    original_admin = policy.admin_can_use_mother
    original_reseller = policy.reseller_can_use_mother

    try:
        policy.admin_can_use_mother = lambda _db: False
        policy.reseller_can_use_mother = lambda _db, _id: True
        assert policy._subscription_can_use_mother(db, sub) is False

        policy.admin_can_use_mother = lambda _db: True
        assert policy._subscription_can_use_mother(db, sub) is True
    finally:
        policy.admin_can_use_mother = original_admin
        policy.reseller_can_use_mother = original_reseller


def test_reseller_subscription_uses_reseller_policy():
    db = _DB(reseller_row=(77,))
    sub = SimpleNamespace(id=11)

    original_admin = policy.admin_can_use_mother
    original_reseller = policy.reseller_can_use_mother

    try:
        policy.admin_can_use_mother = lambda _db: True
        policy.reseller_can_use_mother = (
            lambda _db, reseller_id: reseller_id == 77
        )
        assert policy._subscription_can_use_mother(db, sub) is True

        policy.reseller_can_use_mother = lambda _db, _id: False
        assert policy._subscription_can_use_mother(db, sub) is False
    finally:
        policy.admin_can_use_mother = original_admin
        policy.reseller_can_use_mother = original_reseller


def test_hidden_mother_is_removed_without_mutating_stored_payload():
    db = _DB(
        nodes={
            1: _node(1, mother=True),
            5: _node(5, mother=False),
        }
    )

    payload = {
        "subscription_id": 12,
        "credentials": [
            {
                "protocol": "cisco",
                "items": [
                    {"node_id": 1, "node": "TwinPanel Local Core"},
                    {"node_id": 5, "node": "usa"},
                ],
            },
            {
                "protocol": "openvpn",
                "items": {
                    "node_id": 1,
                    "node": "TwinPanel Local Core",
                },
            },
        ],
    }

    result = policy._filter_mother_from_delivery(db, payload)

    assert len(result["credentials"]) == 1
    assert result["credentials"][0]["protocol"] == "cisco"
    assert result["credentials"][0]["items"] == [
        {"node_id": 5, "node": "usa"}
    ]

    # The persisted/decrypted payload supplied by account_delivery is not
    # changed. Re-enabling access can therefore expose Mother again instantly.
    assert len(payload["credentials"]) == 2
    assert len(payload["credentials"][0]["items"]) == 2


def test_stored_info_wrapper_filters_only_when_policy_is_disabled():
    db = _DB(
        nodes={
            1: _node(1, mother=True),
            5: _node(5, mother=False),
        }
    )
    sub = SimpleNamespace(id=13)
    payload = {
        "subscription_id": 13,
        "credentials": [
            {
                "protocol": "cisco",
                "items": [
                    {"node_id": 1},
                    {"node_id": 5},
                ],
            }
        ],
    }

    original_info = policy._original_stored_info
    original_allowed = policy._subscription_can_use_mother

    try:
        policy._original_stored_info = lambda _db, _sub: payload
        policy._subscription_can_use_mother = lambda _db, _sub: False

        hidden = policy._stored_info_with_mother_policy(db, sub)
        assert hidden["credentials"][0]["items"] == [{"node_id": 5}]

        policy._subscription_can_use_mother = lambda _db, _sub: True
        visible = policy._stored_info_with_mother_policy(db, sub)
        assert visible is payload
        assert visible["credentials"][0]["items"] == [
            {"node_id": 1},
            {"node_id": 5},
        ]
    finally:
        policy._original_stored_info = original_info
        policy._subscription_can_use_mother = original_allowed


if __name__ == "__main__":
    test_direct_subscription_uses_admin_policy()
    test_reseller_subscription_uses_reseller_policy()
    test_hidden_mother_is_removed_without_mutating_stored_payload()
    test_stored_info_wrapper_filters_only_when_policy_is_disabled()
    print("MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V108_OK")
