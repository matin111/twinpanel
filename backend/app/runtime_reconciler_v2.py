from __future__ import annotations

from . import runtime_reconciler as v1


# ============================================================
# TWINPANEL MULTI-TUNNEL ORPHAN RECONCILER V2
#
# V1's ownership model is retained unchanged. This wrapper fixes one remote
# cleanup-script serialization bug: the nested Python heredoc which edits
# authorized_keys used '\n' inside an outer Python f-string, so the generated
# remote script could contain a literal newline inside a single-quoted string
# and fail with SyntaxError before cleanup completed.
#
# V2 rewrites only that generated snippet to use chr(10), which is immune to
# the outer-string escaping layer. Tunnel selection, confirmation cycles,
# retired-node exclusion and all destructive guards remain V1-authoritative.
# ============================================================


_original_cleanup_script = v1._cleanup_script


def _cleanup_script(tid: int) -> str:
    script = _original_cleanup_script(int(tid))

    broken = "p.write_text(('\n'.join(kept) + '\n') if kept else '')"
    fixed = (
        "sep=chr(10)\n"
        "p.write_text((sep.join(kept) + sep) if kept else '')"
    )

    if broken not in script:
        raise RuntimeError(
            "runtime_reconciler_v2_patch_target_missing"
        )

    return script.replace(broken, fixed, 1)


def _activate_patch() -> None:
    # reconcile_once() and reconciler_loop() resolve _cleanup_script from the
    # v1 module globals at runtime, so this keeps every V1 safety guard intact
    # while replacing only the broken serializer.
    v1._cleanup_script = _cleanup_script


async def reconcile_once(*, apply: bool = True) -> dict:
    _activate_patch()
    return await v1.reconcile_once(apply=apply)


async def reconciler_loop() -> None:
    _activate_patch()
    await v1.reconciler_loop()
