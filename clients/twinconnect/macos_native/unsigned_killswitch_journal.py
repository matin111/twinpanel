"""Durable root-private state for the unsigned Kill Switch controller.

No PF mutations, network I/O or daemon installation here. The service must
keep the journal open exclusively for its entire controller lifetime.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat

from unsigned_killswitch_controller import Snapshot, State
from unsigned_killswitch_attestation import Evidence
from unsigned_killswitch_policy import Transport

ROOT = Path("/private/var/run/twinconnect-killswitch")
MAX_BYTES = 16384
PROTOCOLS = frozenset((
    "wireguard", "amneziawg", "openvpn", "cisco", "l2tp", "v2ray",
    "hysteria2", "tuic", "anytls", "shadowtls", "naive", "mieru",
    "snell", "trusttunnel", "socks5", "sudoku",
))


def decode(data):
    if not isinstance(data, dict) or set(data) != {
            "state", "requested", "generation", "reason", "evidence"}:
        raise ValueError("KS_JOURNAL_SCHEMA")
    state = State(data["state"])
    if type(data["requested"]) is not bool:
        raise ValueError("KS_JOURNAL_REQUESTED")
    generation = data["generation"]
    if type(generation) is not int or not 0 <= generation <= (2**63 - 1):
        raise ValueError("KS_JOURNAL_GENERATION")
    reason = data["reason"]
    if not isinstance(reason, str) or not re.fullmatch(r"KS_[A-Z0-9_]{1,80}", reason):
        raise ValueError("KS_JOURNAL_REASON")
    evidence = None
    row = data["evidence"]
    if state == State.TUNNEL:
        if not data["requested"] or not isinstance(row, dict) or set(row) != {
                "protocol", "interface", "uplink", "pid", "transports"}:
            raise ValueError("KS_JOURNAL_EVIDENCE")
        if (row["protocol"] not in PROTOCOLS or type(row["pid"]) is not int
                or row["pid"] <= 1 or not isinstance(row["transports"], list)
                or not 1 <= len(row["transports"]) <= 16):
            raise ValueError("KS_JOURNAL_EVIDENCE")
        transports = []
        for item in row["transports"]:
            if not isinstance(item, dict) or set(item) != {"ip", "port", "proto"}:
                raise ValueError("KS_JOURNAL_EVIDENCE")
            transports.append(Transport(item["ip"], item["port"], item["proto"]))
        evidence = Evidence(row["protocol"], row["interface"], row["uplink"],
                            tuple(transports), row["pid"])
        # Reject interface or endpoint injection, even in a damaged journal.
        evidence.rules()
    elif row is not None:
        raise ValueError("KS_JOURNAL_STALE_EVIDENCE")
    if state == State.OFF and data["requested"]:
        raise ValueError("KS_JOURNAL_STATE_CONFLICT")
    if state in (State.ARMING, State.LOCKED) and not data["requested"]:
        raise ValueError("KS_JOURNAL_STATE_CONFLICT")
    return Snapshot(state, data["requested"], generation, evidence, reason)


def encode(snapshot):
    evidence = snapshot.evidence
    data = {"state": snapshot.state.value, "requested": snapshot.requested,
            "generation": snapshot.generation, "reason": snapshot.reason,
            "evidence": None}
    if evidence is not None:
        data["evidence"] = {
            "protocol": evidence.protocol, "interface": evidence.interface,
            "uplink": evidence.uplink, "pid": evidence.pid,
            "transports": [{"ip": t.ip, "port": t.port, "proto": t.proto}
                           for t in evidence.transports],
        }
    decode(data)
    return json.dumps(data, separators=(",", ":"), allow_nan=False).encode("ascii")


class FileJournal:
    def __init__(self, directory=ROOT, *, owner_uid=0):
        self.owner_uid = owner_uid
        self.dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY |
                             os.O_NOFOLLOW | os.O_CLOEXEC)
        self.lockfd = None
        try:
            self._check(os.fstat(self.dirfd), directory=True)
            fd = os.open("controller.lock", os.O_RDWR | os.O_CREAT |
                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.dirfd)
            self.lockfd = fd
            self._check(os.fstat(fd))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise

    def _check(self, info, directory=False):
        if (info.st_uid != self.owner_uid or info.st_mode & 0o077
                or not (stat.S_ISDIR(info.st_mode) if directory
                        else stat.S_ISREG(info.st_mode))
                or (not directory and info.st_nlink != 1)):
            raise ValueError("KS_JOURNAL_UNTRUSTED")

    def _require_open(self):
        if self.dirfd is None or self.lockfd is None:
            raise ValueError("KS_JOURNAL_CLOSED")

    def _read(self, name):
        self._require_open()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW |
                         os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self.dirfd)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            self._check(info)
            if info.st_size > MAX_BYTES:
                raise ValueError("KS_JOURNAL_TOO_LARGE")
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("KS_JOURNAL_TOO_LARGE")
        return raw

    def read(self):
        raw = self._read("controller.json")
        return Snapshot() if raw is None else decode(json.loads(raw))

    def _write(self, filename, raw):
        self._require_open()
        if len(raw) > MAX_BYTES:
            raise ValueError("KS_JOURNAL_TOO_LARGE")
        name = filename + ".next-" + secrets.token_hex(12)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.dirfd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, filename, src_dir_fd=self.dirfd,
                       dst_dir_fd=self.dirfd)
            os.fsync(self.dirfd)
        finally:
            try:
                os.unlink(name, dir_fd=self.dirfd)
            except FileNotFoundError:
                pass

    def write(self, snapshot):
        self._write("controller.json", encode(snapshot))

    def pf_lease(self):
        return PFLeaseJournal(self)

    def close(self):
        if self.lockfd is not None:
            os.close(self.lockfd)
            self.lockfd = None
        if self.dirfd is not None:
            os.close(self.dirfd)
            self.dirfd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class PFLeaseJournal:
    """Ownership record shares the controller's exclusive service lock."""
    def __init__(self, journal):
        self.journal = journal

    @staticmethod
    def validate(value):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"phase", "token"}:
            raise ValueError("KS_PF_LEASE_SCHEMA")
        phase, token = value["phase"], value["token"]
        if phase in ("prepared", "enable_pending"):
            if token is not None:
                raise ValueError("KS_PF_LEASE_SCHEMA")
        elif phase in ("owned", "anchor_removed"):
            if not isinstance(token, str) or not re.fullmatch(r"[0-9]{1,20}", token):
                raise ValueError("KS_PF_LEASE_SCHEMA")
        else:
            raise ValueError("KS_PF_LEASE_SCHEMA")
        return value

    def read(self):
        raw = self.journal._read("pf-lease.json")
        return None if raw is None else self.validate(json.loads(raw))

    def write(self, value):
        self.validate(value)
        self.journal._write("pf-lease.json", json.dumps(value,
            separators=(",", ":"), allow_nan=False).encode("ascii"))
