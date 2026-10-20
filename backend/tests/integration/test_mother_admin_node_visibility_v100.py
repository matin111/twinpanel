from datetime import datetime
from types import SimpleNamespace

from app.models import NodeStatus
from app.routers import nodes as nodes_router


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    def __init__(self, rows):
        self._rows = rows
        self.commits = 0

    def query(self, *args, **kwargs):
        return _Query(self._rows)

    def commit(self):
        self.commits += 1


def _node(node_id: int, *, is_mother: bool, status=NodeStatus.ONLINE):
    return SimpleNamespace(
        id=node_id,
        is_mother=is_mother,
        status=status,
        last_seen_at=datetime.utcnow(),
    )


def _list_with_access(rows, allowed: bool):
    db = _DB(rows)
    original = nodes_router.admin_can_use_mother
    nodes_router.admin_can_use_mother = lambda _db: allowed

    try:
        result = nodes_router.list_nodes(db)
    finally:
        nodes_router.admin_can_use_mother = original

    return db, result


def test_admin_mother_visibility_policy():
    mother = _node(
        1,
        is_mother=True,
        status=NodeStatus.OFFLINE,
    )
    exit_node = _node(2, is_mother=False)

    db, hidden = _list_with_access(
        [mother, exit_node],
        allowed=False,
    )

    assert [row.id for row in hidden] == [2]
    assert mother.status == NodeStatus.ONLINE
    assert db.commits == 1

    mother.status = NodeStatus.ONLINE

    _db, visible = _list_with_access(
        [mother, exit_node],
        allowed=True,
    )

    assert [row.id for row in visible] == [1, 2]


if __name__ == "__main__":
    test_admin_mother_visibility_policy()
    print("MOTHER_ADMIN_NODE_VISIBILITY_V100_OK")
