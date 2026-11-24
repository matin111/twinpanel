"""PF anchor adapter for the unsigned Kill Switch lifecycle controller.

No installer or activation CLI. The production service must supply a
root-private durable lease store and verified local recovery authorization.
The real kernel readback is supported; mutation paths are tested using
injected commands, not by enabling PF on the development VPS.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from unsigned_killswitch_policy import ANCHOR, PFCTL, render_policy

MAIN = ('scrub-anchor "com.apple/*" all fragment reassemble',
        'anchor "com.apple/*" all')
# The current Mac uses the stock Apple anchor tree. Any additional main or
# recursive filter rule must be reviewed rather than assumed harmless.
APPLE = ('anchor "200.AirDrop/*" all',
         'anchor "250.ApplicationFirewall/*" all')
CLOSED = render_policy()
RULE_COMMAND = (PFCTL, "-a", ANCHOR, "-f", "-")
FLUSH_COMMAND = (PFCTL, "-a", ANCHOR, "-F", "rules")


def lines(output):
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def native_command(args, input=None):
    """No shell; read-only commands or narrowly scoped private-anchor calls.

    Never run kernel mutation on the connected VPS or from an SSH session.
    This is defense in depth; acquire also needs independent recovery proof.
    """
    args = tuple(args)
    if args[0] != PFCTL:
        raise ValueError("KS_COMMAND_REFUSED")
    read_only = args in {
        (PFCTL, "-s", "info"), (PFCTL, "-sr"),
        (PFCTL, "-ss"), (PFCTL, "-s", "References"),
        (PFCTL, "-a", "com.apple", "-sr"),
        (PFCTL, "-a", "com.apple/*", "-sr"),
        (PFCTL, "-a", ANCHOR, "-sr"),
        (PFCTL, "-n", "-v", "-a", ANCHOR, "-f", "-"),
    }
    if not read_only:
        allowed = args in {RULE_COMMAND, FLUSH_COMMAND, (PFCTL, "-E")}
        allowed = allowed or (len(args) == 3 and args[1] == "-X"
                              and bool(re.fullmatch(r"[0-9]{1,20}", args[2])))
        if not allowed:
            raise ValueError("KS_COMMAND_REFUSED")
        if (sys.platform != "darwin" or os.geteuid() != 0
                or Path("/usr/local/bin/termalin-agent").exists()
                or any(os.environ.get(key) for key in (
                    "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY",
                    "TWINCONNECT_REMOTE_VPS"))):
            raise ValueError("KS_REMOTE_PF_MUTATION_REFUSED")
    return subprocess.run(args, input=input, text=True, capture_output=True,
                          timeout=8, check=False,
                          env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin",
                               "LC_ALL":"C"})


class PFBackend:
    def __init__(self, lease, *, recovery_ready, command=native_command):
        self.lease = lease
        self.recovery_ready = recovery_ready
        self.command = command

    def checked(self, *args, input=None):
        output = self.command(args, input=input)
        if output.returncode != 0:
            raise ValueError("KS_PF_COMMAND_FAILED")
        return output

    def canonical(self, rules):
        result = self.checked(PFCTL, "-n", "-v", "-a", ANCHOR, "-f", "-",
                              input=rules)
        canonical = lines(result.stdout)
        if not canonical or canonical[-1] != "block drop quick all":
            raise ValueError("KS_PF_CANONICAL_RULES_INVALID")
        return canonical

    def enabled(self):
        status = self.checked(PFCTL, "-s", "info").stdout
        if re.search(r"(?m)^Status:\s+Enabled\b", status):
            return True
        if re.search(r"(?m)^Status:\s+Disabled\b", status):
            return False
        raise ValueError("KS_PF_STATUS_UNKNOWN")

    def owned_rules(self):
        return lines(self.checked(PFCTL, "-a", ANCHOR, "-sr").stdout)

    def stock_tree(self):
        return (lines(self.checked(PFCTL, "-sr").stdout) == MAIN
                and lines(self.checked(PFCTL, "-a", "com.apple", "-sr").stdout)
                == APPLE)

    def references(self):
        return self.checked(PFCTL, "-s", "References").stdout

    def reference_tokens(self):
        output = self.references()
        if lines(output) == ("No pf starter references held",):
            return set()
        tokens = set(re.findall(r"(?im)^\s*Token\s*:\s*([0-9]{1,20})\s*$",
                                output))
        # Unknown platform formats are not evidence of reference absence.
        if not tokens:
            raise ValueError("KS_PF_REFERENCE_FORMAT_UNKNOWN")
        return tokens

    def has_reference(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[0-9]{1,20}", token):
            return False
        return token in self.reference_tokens()

    def preflight(self):
        if not self.recovery_ready():
            raise ValueError("KS_INDEPENDENT_RECOVERY_REQUIRED")
        if self.lease.read() is not None or self.enabled() or not self.stock_tree():
            raise ValueError("KS_EXISTING_PF_REFUSED")
        if self.owned_rules() or lines(self.checked(PFCTL, "-ss").stdout):
            raise ValueError("KS_EXISTING_STATE_OR_ANCHOR")
        recursive = lines(self.checked(PFCTL, "-a", "com.apple/*", "-sr").stdout)
        if recursive != ('anchor "*" all {', '}', 'anchor "*" all {', '}'):
            raise ValueError("KS_FOREIGN_ANCHOR_UNREVIEWED")
        if self.reference_tokens():
            raise ValueError("KS_EXISTING_REFERENCE_REFUSED")

    def acquire_closed(self, rules):
        if rules != CLOSED:
            raise ValueError("KS_INITIAL_POLICY_NOT_CLOSED")
        self.preflight()
        expected = self.canonical(rules)
        # Durable ownership intent before touching the private anchor.
        self.lease.write({"phase":"prepared","token":None})
        self.checked(*RULE_COMMAND, input=rules)
        if self.owned_rules() != expected:
            raise ValueError("KS_PF_RULE_READBACK_FAILED")
        # Journal the uncertainty BEFORE asking the kernel for a reference.
        # If the process dies here, recovery can remove its anchor, but must
        # never guess a token or globally disable PF.
        self.lease.write({"phase":"enable_pending","token":None})
        result = self.checked(PFCTL, "-E")
        match = re.search(r"(?im)^\s*Token\s*:\s*([0-9]{1,20})\s*$",
                          result.stdout + "\n" + result.stderr)
        if not match:
            raise ValueError("KS_PF_REFERENCE_UNKNOWN")
        self.lease.write({"phase":"owned","token":match.group(1)})
        if not self.matches(rules):
            raise ValueError("KS_PF_RULE_READBACK_FAILED")

    def matches(self, rules):
        try:
            lease = self.lease.read()
            return bool(lease and lease.get("phase") == "owned"
                and self.enabled() and self.stock_tree()
                and self.has_reference(lease.get("token"))
                and self.owned_rules() == self.canonical(rules))
        except (OSError, ValueError, subprocess.SubprocessError):
            return False

    def replace(self, rules):
        lease = self.lease.read()
        if not lease or lease.get("phase") != "owned":
            raise ValueError("KS_PF_LEASE_NOT_OWNED")
        # Recovery may always narrow our own rules. Opening a tunnel policy
        # still requires the independently verified recovery service.
        if rules != CLOSED and not self.recovery_ready():
            raise ValueError("KS_INDEPENDENT_RECOVERY_REQUIRED")
        expected = self.canonical(rules)
        self.checked(*RULE_COMMAND, input=rules)
        if self.owned_rules() != expected or not self.matches(rules):
            raise ValueError("KS_PF_RULE_READBACK_FAILED")

    def released(self):
        try:
            return self.lease.read() is None and not self.owned_rules()
        except (OSError, ValueError, subprocess.SubprocessError):
            return False

    def release(self):
        lease = self.lease.read()
        if lease is None:
            # Do not touch an anchor without recorded ownership.
            if self.owned_rules():
                raise ValueError("KS_UNOWNED_ANCHOR_REFUSED")
            return
        phase = lease.get("phase")
        token = lease.get("token")
        if phase not in ("prepared","enable_pending","owned","anchor_removed"):
            raise ValueError("KS_PF_LEASE_INVALID")
        if phase != "anchor_removed":
            self.checked(*FLUSH_COMMAND)
            if self.owned_rules():
                raise ValueError("KS_PF_ANCHOR_RELEASE_FAILED")
            if phase == "enable_pending" and self.enabled():
                # The reference could be ours or someone else's. Restore
                # traffic by removing our anchor, but preserve uncertainty.
                raise ValueError("KS_PF_REFERENCE_UNKNOWN")
            if token is None:
                self.lease.write(None)
                return
            self.lease.write({"phase":"anchor_removed","token":token})
        if not isinstance(token,str) or not re.fullmatch(r"[0-9]{1,20}",token):
            raise ValueError("KS_PF_REFERENCE_UNKNOWN")
        if self.has_reference(token):
            self.checked(PFCTL, "-X", token)
        if self.has_reference(token):
            raise ValueError("KS_PF_REFERENCE_RELEASE_FAILED")
        # An unknown readback format cannot prove reference release. A
        # production acceptance test must establish the parser on live PF.
        if self.enabled() and not self.reference_tokens():
            raise ValueError("KS_PF_REFERENCE_STATUS_UNCERTAIN")
        self.lease.write(None)
