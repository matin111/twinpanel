"""Admin edit must preserve existing node assignments without bypassing plan limits."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app/routers/subscription_admin_edit_fast_v1.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
func = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "_invalid_edit_node_ids"
)
namespace = {}
exec(compile(ast.Module(body=[func], type_ignores=[]), str(SOURCE), "exec"), namespace)
invalid = namespace["_invalid_edit_node_ids"]


def test_existing_out_of_plan_node_is_grandfathered_for_same_plan():
    # Regression: msabt123792 already has Exit #1 while plan 15 allows 6/7/11/13.
    assert invalid([1, 6, 7, 11, 13], [11, 7, 6, 13],
                   [1, 6, 7, 11, 13], same_plan=True) == []


def test_a_new_out_of_plan_node_is_still_denied():
    assert invalid([1, 6, 7], [6, 7, 11, 13],
                   [6, 7], same_plan=True) == [1]


def test_changing_commercial_plan_requires_new_entitlements():
    assert invalid([1, 6], [6, 7, 11, 13],
                   [1, 6], same_plan=False) == [1]


def test_explicit_removal_does_not_force_old_node_back():
    assert invalid([6, 7, 11, 13], [6, 7, 11, 13],
                   [1, 6, 7, 11, 13], same_plan=True) == []


def test_valid_existing_node_remains_subject_to_exit_retirement_check():
    code = SOURCE.read_text(encoding="utf-8")
    # Grandfathering is only the plan membership check; subsequent Node
    # validation must still reject retired/non-Exit nodes.
    assert "Node.node_type == NodeType.EXIT" in code
    assert "Node.retired_at.is_(None)" in code
    assert "if valid_count != len(set(desired_node_ids)):" in code
