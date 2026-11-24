"""Failure injection for the lifecycle controller; never load real PF."""
import unittest
from unsigned_killswitch_controller import Controller, Snapshot, State, CLOSED
from unsigned_killswitch_attestation import Evidence
from unsigned_killswitch_policy import Transport

class FakeJournal:
    def __init__(self):
        self.value=Snapshot()
        self.history=[]
    def read(self): return self.value
    def write(self,value):
        self.value=value
        self.history.append(value.state)

class FakePF:
    def __init__(self):
        self.rules=None
        self.fail=set()
        self.history=[]
    def acquire_closed(self,rules):
        self.rules=rules
        self.history.append("acquire")
        if "acquire" in self.fail: raise RuntimeError()
    def replace(self,rules):
        self.history.append("replace")
        if "replace" in self.fail: raise RuntimeError()
        self.rules=rules
    def matches(self,rules):
        return self.rules==rules and "readback" not in self.fail
    def released(self): return self.rules is None
    def release(self):
        self.history.append("release")
        if "release" in self.fail: raise RuntimeError()
        self.rules=None

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.pf=FakePF()
        self.j=FakeJournal()
        self.engine=None
        self.c=Controller(self.pf,self.j,lambda:self.engine)
    def attach(self):
        self.c.enable()
        self.engine=Evidence("wireguard","utun15","en0",
                             (Transport("1.2.3.4",51820,"udp"),),123)
        return self.c.attach_verified_tunnel(self.j.value.generation)
    def test_enable_offline_lock(self):
        self.assertEqual(self.c.enable().state,State.LOCKED)
        self.assertEqual(self.pf.rules,CLOSED)
        self.assertEqual(self.j.history[:2],[State.ARMING,State.LOCKED])
        self.assertFalse(self.c.status()["leak_verified"])
    def test_verified_attach_and_disconnect_order(self):
        self.assertEqual(self.attach().state,State.TUNNEL)
        self.assertNotEqual(self.pf.rules,CLOSED)
        self.assertTrue(self.c.status()["rules_readback"])
        self.assertEqual(self.c.before_disconnect().state,State.LOCKED)
        self.assertEqual(self.pf.rules,CLOSED)
    def test_loss_stays_locked(self):
        self.attach()
        self.engine=None
        self.assertEqual(self.c.reconcile().state,State.LOCKED)
        self.assertEqual(self.pf.rules,CLOSED)
        self.assertNotIn("release",self.pf.history)
    def test_different_worker_never_auto_opens(self):
        self.attach()
        self.engine=Evidence("wireguard","utun15","en0",
                             (Transport("1.2.3.4",51820,"udp"),),124)
        self.assertEqual(self.c.reconcile().state,State.LOCKED)
        self.assertEqual(self.c.reconcile().state,State.LOCKED)
        self.assertEqual(self.pf.rules,CLOSED)
    def test_restart_closes_before_reusing_policy(self):
        self.attach()
        self.assertEqual(self.c.recover_after_service_restart().state,State.LOCKED)
        self.assertEqual(self.pf.rules,CLOSED)
    def test_readback_drift(self):
        self.attach()
        self.pf.rules="unexpected"
        self.assertFalse(self.c.status()["rules_readback"])
        self.assertEqual(self.c.reconcile().state,State.LOCKED)
    def test_acquire_partial_failure_is_fault_not_off(self):
        self.pf.fail.add("acquire")
        self.assertEqual(self.c.enable().state,State.FAULT)
        self.assertTrue(self.j.value.requested)
        self.assertFalse(self.c.status()["rules_readback"])
        self.assertEqual(self.c.reset().state,State.OFF)
    def test_failed_close_does_not_claim_lock(self):
        self.attach()
        self.pf.fail.add("replace")
        self.assertEqual(self.c.before_disconnect().state,State.FAULT)
        self.assertFalse(self.c.status()["rules_readback"])
    def test_failed_release_requires_retry(self):
        self.attach()
        self.pf.fail.add("release")
        self.assertEqual(self.c.reset().state,State.FAULT)
        self.assertTrue(self.j.value.requested)
        self.pf.fail.clear()
        self.assertEqual(self.c.reset().state,State.OFF)
        self.assertIsNone(self.pf.rules)
    def test_stale_generation_rejected(self):
        self.attach()
        old=self.j.value.generation
        self.c.reset()
        self.c.enable()
        self.assertEqual(self.c.attach_verified_tunnel(old).state,State.LOCKED)
    def test_disconnect_invalidates_pending_attach(self):
        self.attach()
        old=self.j.value.generation
        self.c.before_disconnect()
        self.assertGreater(self.j.value.generation,old)
        self.assertEqual(self.c.attach_verified_tunnel(old).state,State.LOCKED)

    def test_restart_finishes_explicit_reset(self):
        from dataclasses import replace
        self.attach()
        self.j.write(replace(self.j.value,state=State.RESETTING,evidence=None))
        self.assertEqual(self.c.recover_after_service_restart().state,State.OFF)
        self.assertIsNone(self.pf.rules)

    def test_no_automatic_reopen_from_locked(self):
        self.c.enable()
        self.engine=Evidence("wireguard","utun15","en0",
                             (Transport("1.2.3.4",51820,"udp"),),123)
        self.assertEqual(self.c.reconcile().state,State.LOCKED)
        self.assertEqual(self.pf.rules,CLOSED)

if __name__=="__main__": unittest.main()
