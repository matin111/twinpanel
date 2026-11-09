"""Contract-level tests for central Sudoku revocation and recovery safeguards."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.models import NodeType
from app.services import sudoku_central_enforcement_v1 as subject


def exit_node(node_id):
    return SimpleNamespace(id=node_id, node_type=NodeType.EXIT)


class MembershipDB:
    def query(self, *args, **kwargs):
        return self
    def join(self, *args, **kwargs):
        return self
    def filter(self, *args, **kwargs):
        return self
    def all(self):
        return [exit_node(6),exit_node(19),exit_node(22)]


def test_central_acks_only_verified_current_whitelist():
    db = MembershipDB()
    with patch.object(subject,"is_central_node",return_value=True), \
         patch.object(subject,"desired_sudoku_fingerprint",return_value="a" * 64), \
         patch.object(subject,"last_sudoku_applied",return_value="a" * 64):
        assert subject.central_sudoku_enforcement_result(
            db,exit_node(19),74,"revoke_subscription"
        ) == "controller_central_sudoku_whitelist_converged"
        assert subject.central_sudoku_enforcement_result(
            db,exit_node(22),74,"restore_subscription"
        ) == "controller_central_sudoku_whitelist_converged"


def test_incomplete_central_does_not_ack_and_schedules_stage():
    from app.services import central_node_stage_launcher_v1 as launcher
    db = MembershipDB()
    launched=[]
    with patch.object(subject,"is_central_node",return_value=True), \
         patch.object(subject,"desired_sudoku_fingerprint",return_value="a" * 64), \
         patch.object(subject,"last_sudoku_applied",return_value="b" * 64), \
         patch.object(launcher,"launch",side_effect=lambda db,n:launched.append(n)):
        try:
            subject.central_sudoku_enforcement_result(
                db,exit_node(19),74,"revoke_subscription"
            )
        except subject.CentralSudokuReconciliationPending:
            pass
        else:
            raise AssertionError("unapplied shared whitelist was acknowledged")
    assert launched == [19]


def test_currently_running_stage_keeps_command_pending():
    from app.services import central_node_stage_launcher_v1 as launcher
    with patch.object(subject,"is_central_node",return_value=True), \
         patch.object(subject,"desired_sudoku_fingerprint",return_value="a" * 64), \
         patch.object(subject,"last_sudoku_applied",return_value="b" * 64), \
         patch.object(launcher,"launch",side_effect=launcher.CentralStageLaunchError("ALREADY_RUNNING")):
        try:
            subject.central_sudoku_enforcement_result(
                MembershipDB(),exit_node(22),74,"restore_subscription"
            )
        except subject.CentralSudokuReconciliationPending:
            pass
        else:
            raise AssertionError("concurrent pending stage was acknowledged")


def test_legacy_revoke_still_removes_old_access():
    with patch.object(subject,"is_central_node",return_value=False):
        assert subject.central_sudoku_enforcement_result(
            MembershipDB(),exit_node(6),74,"revoke_subscription"
        ) is None


def test_legacy_restore_never_resurrects_if_central_exit_registered():
    with patch.object(subject,"is_central_node",side_effect=lambda db,n:n in {19,22}):
        assert subject.central_sudoku_enforcement_result(
            MembershipDB(),exit_node(6),74,"restore_subscription"
        ) == "controller_legacy_sudoku_restore_suppressed"


def test_controller_worker_retries_slow_whitelist_without_unjustified_success():
    from pathlib import Path
    worker=(Path(__file__).resolve().parents[1]/"app/services/account_enforcement_v2.py").read_text()
    assert "if protocol == \"sudoku\":" in worker
    assert "handled_by_central_sudoku = True" in worker
    assert "if not handled_by_central_sudoku:" in worker
    assert "isinstance(error, CentralSudokuReconciliationPending)" in worker
    assert '"controller_central_sudoku_awaiting_ack"' in worker
    assert 'row.status = "controller_processing"' in worker
    assert worker.index("handled_by_central_sudoku = True") < worker.index(
        "conn = await ssh_connect_saved(node, db)"
    )


def run():
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
    print("SUDOKU_CENTRAL_ENFORCEMENT_V1_SMOKE_OK")


if __name__ == "__main__":
    run()
