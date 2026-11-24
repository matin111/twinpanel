"""Durability, ownership and crash-state tests; no network changes."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from unsigned_killswitch_journal import FileJournal, decode
from unsigned_killswitch_controller import Snapshot, State, Controller, CLOSED
from unsigned_killswitch_attestation import Evidence
from unsigned_killswitch_policy import Transport
from test_unsigned_killswitch_controller import FakePF

class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def journal(self):
        return FileJournal(self.root, owner_uid=os.getuid())
    def test_durable_snapshot_roundtrip(self):
        sample = Snapshot(State.TUNNEL, True, 7, Evidence("wireguard", "utun15",
                   "en0", (Transport("1.2.3.4",51820,"udp"),),123),
                   "KS_TUNNEL_POLICY_APPLIED")
        with self.journal() as j:
            self.assertEqual(j.read(), Snapshot())
            j.write(sample)
        with self.journal() as j:
            self.assertEqual(j.read(), sample)
            self.assertEqual((self.root/"controller.json").stat().st_mode & 0o777,0o600)
    def test_concurrent_controller_refused(self):
        with self.journal():
            with self.assertRaises(OSError):
                self.journal()
    def test_corrupt_state_not_off(self):
        with self.journal() as j:
            (self.root/"controller.json").write_text("{broken")
            (self.root/"controller.json").chmod(0o600)
            with self.assertRaises(ValueError):
                j.read()
    def test_symlink_state_refused(self):
        with self.journal() as j:
            (self.root/"controller.json").symlink_to("/etc/passwd")
            with self.assertRaises(OSError):
                j.read()
    def test_untrusted_permissions_refused(self):
        with self.journal() as j:
            j.write(Snapshot())
            (self.root/"controller.json").chmod(0o644)
            with self.assertRaisesRegex(ValueError,"KS_JOURNAL_UNTRUSTED"):
                j.read()
    def test_invalid_state_rejected(self):
        for state,requested in (("off",True),("locked",False),("tunnel",True)):
            with self.assertRaises(ValueError):
                decode({"state":state,"requested":requested,"generation":1,
                        "reason":"KS_TEST","evidence":None})
    def test_pf_lease_is_durable_and_validated(self):
        with self.journal() as j:
            lease=j.pf_lease()
            self.assertIsNone(lease.read())
            lease.write({"phase":"prepared","token":None})
            lease.write({"phase":"owned","token":"123456"})
        with self.journal() as j:
            lease=j.pf_lease()
            self.assertEqual(lease.read(),{"phase":"owned","token":"123456"})
            with self.assertRaises(ValueError):
                lease.write({"phase":"owned","token":"not-a-token"})
            lease.write(None)
            self.assertIsNone(lease.read())

    def test_restart_never_reuses_previous_tunnel_policy(self):
        pf=FakePF()
        engine=Evidence("wireguard","utun15","en0",
                        (Transport("1.2.3.4",51820,"udp"),),123)
        with self.journal() as j:
            c=Controller(pf,j,lambda:engine)
            c.enable()
            self.assertEqual(c.attach_verified_tunnel(j.read().generation).state,State.TUNNEL)
        with self.journal() as j:
            c=Controller(pf,j,lambda:engine)
            self.assertEqual(c.recover_after_service_restart().state,State.LOCKED)
            self.assertEqual(pf.rules,CLOSED)
            self.assertFalse(c.status()["leak_verified"])

if __name__ == "__main__":
    unittest.main()
