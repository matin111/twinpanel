from __future__ import annotations

import inspect
import json
from datetime import datetime
from types import SimpleNamespace

from app import adaptive_candidate_qualification_v155 as qualification_v155
from app import smart_candidate_retry_guard_v169 as retry_v169
from app import smart_transport_auto_v21 as smart
from app import stale_candidate_install_recovery_v200 as recovery_v200
from app import tunnel_transport_manager_v12 as manager_v12


def _row(
    *,
    release: str | None,
    attempt_epoch: float | None,
    updated_epoch: float,
    status: str = "installing",
):
    state = {}
    if release is not None:
        state["last_install_attempt_release"] = release
    if attempt_epoch is not None:
        state["last_install_attempt_epoch"] = attempt_epoch

    return SimpleNamespace(
        enabled=True,
        status=status,
        updated_at=datetime.fromtimestamp(updated_epoch),
        config_text=json.dumps({"smart_auto_v21": state}),
    )


def test_previous_release_installing_is_immediately_stale() -> None:
    row = _row(
        release="1.1.0-rc.191",
        attempt_epoch=1000.0,
        updated_epoch=1000.0,
    )

    reason = recovery_v200.stale_installing_reason_v200(
        row,
        now_epoch=1100.0,
        current_release="1.1.0-rc.199",
    )

    assert reason == "previous_release"


def test_same_release_fresh_installing_remains_protected() -> None:
    row = _row(
        release="1.1.0-rc.199",
        attempt_epoch=1000.0,
        updated_epoch=1000.0,
    )

    reason = recovery_v200.stale_installing_reason_v200(
        row,
        now_epoch=1000.0 + smart.INSTALL_RETRY_SECONDS - 1.0,
        current_release="1.1.0-rc.199",
    )

    assert reason is None


def test_same_release_installing_recovers_after_existing_retry_window() -> None:
    row = _row(
        release="1.1.0-rc.199",
        attempt_epoch=1000.0,
        updated_epoch=1000.0,
    )

    reason = recovery_v200.stale_installing_reason_v200(
        row,
        now_epoch=1000.0 + smart.INSTALL_RETRY_SECONDS,
        current_release="1.1.0-rc.199",
    )

    assert reason == "retry_window_elapsed"


def test_old_release_stale_row_is_selected_for_official_retry() -> None:
    row = _row(
        release="1.1.0-rc.191",
        attempt_epoch=1000.0,
        updated_epoch=1000.0,
    )

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return row

    class DB:
        def query(self, model):
            return Query()

        def close(self):
            pass

    old_session = recovery_v200.SessionLocal
    old_names = smart.AUTO_INSTALL_NAMES
    old_release = retry_v169._current_release

    try:
        recovery_v200.SessionLocal = lambda: DB()
        smart.AUTO_INSTALL_NAMES = ("tp27_tcp_direct",)
        retry_v169._current_release = lambda: "1.1.0-rc.199"

        selected = recovery_v200._stale_candidate_for_tunnel_v200(6)
    finally:
        recovery_v200.SessionLocal = old_session
        smart.AUTO_INSTALL_NAMES = old_names
        retry_v169._current_release = old_release

    assert selected == ("tp27_tcp_direct", "previous_release")


def test_apply_wraps_final_v155_selector_without_replacing_normal_fallback() -> None:
    old_applied = recovery_v200._applied
    old_original = recovery_v200._original_selector
    old_selector = smart._install_candidate_name

    try:
        # Production rc.200 proved that V155 is the last layer which replaces
        # the selector. V200 must therefore wrap that exact final authority.
        smart._install_candidate_name = qualification_v155._install_candidate_name_v155
        recovery_v200._applied = False
        recovery_v200._original_selector = None

        recovery_v200.apply_stale_candidate_install_recovery_v200()

        assert (
            smart._install_candidate_name
            is recovery_v200.install_candidate_name_stale_recovery_v200
        )
        assert (
            recovery_v200._original_selector
            is qualification_v155._install_candidate_name_v155
        )
    finally:
        recovery_v200._applied = old_applied
        recovery_v200._original_selector = old_original
        smart._install_candidate_name = old_selector


def test_manager_applies_stale_recovery_after_all_selector_owners() -> None:
    source = inspect.getsource(manager_v12.main)

    v171_index = source.index("apply_smart_candidate_fair_retry_v171()")
    v175_index = source.index("apply_candidate_dataplane_v175()")
    v155_index = source.index("apply_adaptive_candidate_qualification_v155()")
    v198_index = source.index("apply_direct_tcp_rpfilter_guard_v198()")
    recovery_index = source.index("apply_stale_candidate_install_recovery_v200()")

    assert v171_index < v175_index < v155_index < v198_index < recovery_index
