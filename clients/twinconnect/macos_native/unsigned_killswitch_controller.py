"""Kill Switch lifecycle controller, independent of GUI and VPN engine.

The privileged service must serialize all calls and provide an exclusive,
verified PF backend and durable journal. This module does not load PF rules
itself. A validated policy is NOT proof of packet filtering or leak safety.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, Callable
import math

from unsigned_killswitch_policy import render_policy
from unsigned_killswitch_attestation import Evidence

CLOSED = render_policy()


class State(str, Enum):
    OFF = "off"
    ARMING = "arming"
    LOCKED = "locked"
    TUNNEL = "tunnel"
    RESETTING = "resetting"
    FAULT = "fault"


@dataclass(frozen=True)
class Snapshot:
    state: State = State.OFF
    requested: bool = False
    generation: int = 0
    evidence: Evidence | None = None
    reason: str = "KS_OFF"


class Firewall(Protocol):
    """Privileged PF backend; no implementation may bypass these checks.

    acquire_closed: acquire ONLY a private anchor and reference, initially
    with a blocking policy. Must verify anchor reachability, no conflicting
    rules/state/skip interfaces, and independent recovery readiness BEFORE
    any kernel mutation. Raise if acquisition or verification fails.
    replace: atomic private-anchor replacement with readback verification.
    matches: observe actual enabled PF, reference and exact effective rules.
    release: remove ONLY owned rules and reference. Must be idempotent even
    after partially failed acquire. Never disable third-party PF.
    """
    def acquire_closed(self, rules: str) -> None: ...
    def replace(self, rules: str) -> None: ...
    def matches(self, rules: str) -> bool: ...
    def release(self) -> None: ...
    def released(self) -> bool: ...


class Journal(Protocol):
    """Root-only durable write-before-mutate journal. No credentials."""
    def read(self) -> Snapshot: ...
    def write(self, snapshot: Snapshot) -> None: ...


class Controller:
    def __init__(self, firewall: Firewall, journal: Journal,
                 collect: Callable[[], Evidence | None]):
        self.firewall = firewall
        self.journal = journal
        self.collect = collect

    def put(self, snapshot: Snapshot) -> Snapshot:
        self.journal.write(snapshot)
        return snapshot

    def _fault(self, snapshot: Snapshot, reason: str) -> Snapshot:
        return self.put(replace(snapshot, state=State.FAULT,
                                evidence=None, reason=reason))

    def _close(self, snapshot: Snapshot, reason: str) -> Snapshot:
        # Even a process crash after this durable transition must recover
        # to CLOSED, not restore a previous interface's permissive rules.
        pending = self.put(replace(snapshot, state=State.ARMING,
                                   generation=snapshot.generation + 1,
                                   evidence=None, reason=reason))
        try:
            self.firewall.replace(CLOSED)
            if not self.firewall.matches(CLOSED):
                raise RuntimeError("KS_CLOSED_READBACK_FAILED")
        except Exception:
            return self._fault(pending, "KS_CLOSE_FAILED")
        return self.put(replace(pending, state=State.LOCKED, reason=reason))

    def enable(self) -> Snapshot:
        current = self.journal.read()
        if current.requested:
            return self.reconcile()
        if current.state != State.OFF or not self.firewall.released():
            return self._fault(current, "KS_PREVIOUS_LEASE_REQUIRES_RESET")
        pending = self.put(Snapshot(State.ARMING, True,
                                    current.generation + 1, None, "KS_ARMING"))
        try:
            self.firewall.acquire_closed(CLOSED)
            if not self.firewall.matches(CLOSED):
                raise RuntimeError("KS_CLOSED_READBACK_FAILED")
        except Exception:
            # A failed acquire can be partially applied. Never report OFF.
            return self._fault(pending, "KS_ACQUIRE_FAILED")
        locked = self.put(replace(pending, state=State.LOCKED,
                                  reason="KS_OFFLINE_LOCKED"))
        return self.reconcile()

    def reconcile(self) -> Snapshot:
        """Root service tick. No GUI heartbeat, no automatic direct fallback."""
        current = self.journal.read()
        if not current.requested:
            return current
        if current.state in (State.ARMING, State.RESETTING, State.FAULT):
            # A crash or error requires explicit recovery; never reopen
            # the previous tunnel policy from a journal alone.
            return self._close(current, "KS_RECOVERY_LOCKED")
        if current.state not in (State.LOCKED, State.TUNNEL):
            return self._fault(current, "KS_STATE_INVALID")
        try:
            expected = current.evidence.rules() if current.evidence else CLOSED
            if not self.firewall.matches(expected):
                return self._close(current, "KS_POLICY_DRIFT_LOCKED")
            evidence = self.collect()
            if evidence is not None and not isinstance(evidence, Evidence):
                raise ValueError("KS_EVIDENCE_INVALID")
        except Exception:
            return self._close(current, "KS_ATTESTATION_FAILED")
        if evidence is None:
            if current.state == State.LOCKED:
                return current
            return self._close(current, "KS_TUNNEL_LOST")
        if current.state == State.TUNNEL:
            if current.evidence == evidence:
                return current
            # A different process/interface/endpoint is not a reconnect
            # authorization. First close; require a fresh explicit arm.
            return self._close(current, "KS_TUNNEL_CHANGED")
        # A deliberately closed policy must not automatically become open
        # after an unrelated engine/interface appears. Only a fresh request
        # may attach a tunnel, through attach_verified_tunnel().
        return current

    def attach_verified_tunnel(self, generation: int) -> Snapshot:
        """Bind a freshly attested live engine to the current closed lease.

        Engine integration must arrange authenticated, narrowly scoped
        handshake access before this call. Never use a GUI protocol label.
        """
        current = self.journal.read()
        if not current.requested or current.state != State.LOCKED or type(generation) is not int or generation != current.generation:
            return current
        try:
            if not self.firewall.matches(CLOSED):
                return self._close(current, "KS_POLICY_DRIFT_LOCKED")
            evidence = self.collect()
            if not isinstance(evidence, Evidence):
                return current
            rules = evidence.rules()
        except Exception:
            return self._close(current, "KS_ATTESTATION_FAILED")
        pending = self.put(replace(current, state=State.ARMING,
                                   evidence=None, reason="KS_ATTACHING"))
        try:
            self.firewall.replace(rules)
            if not self.firewall.matches(rules):
                raise RuntimeError("KS_POLICY_READBACK_FAILED")
            # Verify evidence again after mutation to detect a lost or
            # replaced worker. Fail closed, not to the physical network.
            if self.collect() != evidence:
                return self._close(pending, "KS_TUNNEL_CHANGED")
        except Exception:
            return self._close(pending, "KS_ATTACH_FAILED")
        return self.put(replace(pending, state=State.TUNNEL,
                                evidence=evidence, reason="KS_TUNNEL_POLICY_APPLIED"))

    def before_disconnect(self) -> Snapshot:
        """Engine must call synchronously BEFORE releasing any route."""
        current = self.journal.read()
        if not current.requested:
            return current
        return self._close(current, "KS_DISCONNECT_LOCKED")

    def reset(self) -> Snapshot:
        """Explicit user recovery, not an automatic fail-open on engine loss."""
        current = self.journal.read()
        pending = self.put(replace(current, state=State.RESETTING,
                                   evidence=None, reason="KS_RESETTING"))
        try:
            self.firewall.release()
            if not self.firewall.released():
                raise RuntimeError("KS_RELEASE_READBACK_FAILED")
        except Exception:
            return self._fault(pending, "KS_RESET_FAILED")
        return self.put(Snapshot(State.OFF, False, current.generation,
                                 None, "KS_OFF"))

    def recover_after_service_restart(self) -> Snapshot:
        """Never reopen a stale interface from persistent state."""
        current = self.journal.read()
        if current.state == State.RESETTING:
            # An explicit reset was already durably authorized. Finish
            # releasing only our lease; do not reacquire a firewall.
            return self.reset()
        if current.requested:
            return self._close(current, "KS_RESTART_LOCKED")
        if current.state != State.OFF:
            return self._fault(current, "KS_PREVIOUS_LEASE_REQUIRES_RESET")
        if not self.firewall.released():
            return self._fault(current, "KS_UNOWNED_RULES_REQUIRE_RESET")
        return current

    def status(self) -> dict:
        current = self.journal.read()
        # Readback is not an end-to-end leak test. UI must not turn this
        # into a 'verified protection' claim.
        try:
            if current.state == State.TUNNEL and current.evidence:
                applied = self.firewall.matches(current.evidence.rules())
                applied = applied and self.collect() == current.evidence
            elif current.state == State.LOCKED:
                applied = self.firewall.matches(CLOSED)
            else:
                applied = False
        except Exception:
            applied = False
        return {"state":current.state.value,"requested":current.requested,
                "rules_readback":bool(applied),"leak_verified":False,
                "reason":current.reason}
