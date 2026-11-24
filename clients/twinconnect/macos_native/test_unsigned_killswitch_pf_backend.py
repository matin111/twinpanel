"""Kernel adapter tests with an injected fake PF; never enable live PF."""
from types import SimpleNamespace
import unittest
from unsigned_killswitch_pf_backend import (
    PFBackend, PFCTL, ANCHOR, MAIN, APPLE, CLOSED, RULE_COMMAND, FLUSH_COMMAND)
from unsigned_killswitch_policy import render_policy, Transport

class Lease:
    def __init__(self): self.value=None; self.events=[]
    def read(self): return self.value
    def write(self,value): self.value=value; self.events.append(value)

class Kernel:
    def __init__(self):
        self.rules=""
        self.enabled=False
        self.token=None
        self.calls=[]
        self.fail=set()
        self.main="\n".join(MAIN)
        self.apple="\n".join(APPLE)
        self.recursive='anchor "*" all {\n}\nanchor "*" all {\n}'
    def __call__(self,args,input=None):
        self.calls.append(args)
        out=""
        if args in self.fail: return SimpleNamespace(returncode=1,stdout="",stderr="")
        if args==(PFCTL,"-s","info"):
            out="Status: "+("Enabled" if self.enabled else "Disabled")
        elif args==(PFCTL,"-sr"): out=self.main
        elif args==(PFCTL,"-a","com.apple","-sr"): out=self.apple
        elif args==(PFCTL,"-a","com.apple/*","-sr"): out=self.recursive
        elif args==(PFCTL,"-a",ANCHOR,"-sr"): out=self.rules
        elif args==(PFCTL,"-ss"): out=""
        elif args==(PFCTL,"-s","References"):
            out="Token : "+self.token if self.token else "No pf starter references held"
        elif args==(PFCTL,"-n","-v","-a",ANCHOR,"-f","-"):
            out=input.replace("user = root","user = 0")
        elif args==RULE_COMMAND: self.rules=input.replace("user = root","user = 0")
        elif args==FLUSH_COMMAND: self.rules=""
        elif args==(PFCTL,"-E"): self.enabled=True; self.token="123456"; out="Token : "+self.token
        elif args==(PFCTL,"-X","123456"): self.enabled=False; self.token=None
        else: raise AssertionError(args)
        return SimpleNamespace(returncode=0,stdout=out,stderr="")

class PFBackendTests(unittest.TestCase):
    def setUp(self):
        self.kernel=Kernel()
        self.lease=Lease()
        self.ready=True
        self.pf=PFBackend(self.lease,recovery_ready=lambda:self.ready,command=self.kernel)
    def test_owned_acquire_replace_release(self):
        self.pf.acquire_closed(CLOSED)
        self.assertEqual([v["phase"] for v in self.lease.events],["prepared","enable_pending","owned"])
        self.assertTrue(self.pf.matches(CLOSED))
        active=render_policy("utun15","en0",(Transport("1.2.3.4",443,"tcp"),))
        self.pf.replace(active)
        self.assertTrue(self.pf.matches(active))
        self.pf.replace(CLOSED)
        self.pf.release()
        self.assertTrue(self.pf.released())
        self.assertNotIn((PFCTL,"-d"),self.kernel.calls)
        self.assertNotIn((PFCTL,"-F","all"),self.kernel.calls)
    def test_requires_independent_recovery(self):
        self.ready=False
        with self.assertRaisesRegex(ValueError,"KS_INDEPENDENT_RECOVERY_REQUIRED"):
            self.pf.acquire_closed(CLOSED)
        self.assertEqual(self.kernel.calls,[])
    def test_foreign_pf_refused(self):
        self.kernel.enabled=True
        with self.assertRaisesRegex(ValueError,"KS_EXISTING_PF_REFUSED"):
            self.pf.acquire_closed(CLOSED)
        self.assertNotIn(RULE_COMMAND,self.kernel.calls)
    def test_foreign_recursive_filter_refused(self):
        self.kernel.recursive += "\npass quick all"
        with self.assertRaisesRegex(ValueError,"KS_FOREIGN_ANCHOR_UNREVIEWED"):
            self.pf.acquire_closed(CLOSED)
        self.assertNotIn(RULE_COMMAND,self.kernel.calls)
    def test_main_rule_drift_detected(self):
        self.pf.acquire_closed(CLOSED)
        self.kernel.main += "\npass quick all"
        self.assertFalse(self.pf.matches(CLOSED))
    def test_release_never_flushes_unknown_anchor(self):
        self.kernel.rules="pass all"
        with self.assertRaisesRegex(ValueError,"KS_UNOWNED_ANCHOR_REFUSED"):
            self.pf.release()
        self.assertNotIn(FLUSH_COMMAND,self.kernel.calls)
    def test_partial_enable_removes_anchor_but_never_guesses_reference(self):
        self.lease.write({"phase":"enable_pending","token":None})
        self.kernel.rules=CLOSED
        self.kernel.enabled=True
        self.kernel.token="999"
        with self.assertRaisesRegex(ValueError,"KS_PF_REFERENCE_UNKNOWN"):
            self.pf.release()
        self.assertEqual(self.kernel.rules,"")
        self.assertEqual(self.kernel.token,"999")
        self.assertIsNotNone(self.lease.read())
    def test_unknown_reference_format_never_claims_release(self):
        self.pf.acquire_closed(CLOSED)
        self.pf.references=lambda:"unrecognized reference output"
        self.assertFalse(self.pf.matches(CLOSED))
        with self.assertRaisesRegex(ValueError,"KS_PF_REFERENCE_FORMAT_UNKNOWN"):
            self.pf.release()
        self.assertEqual(self.lease.read()["phase"],"anchor_removed")
        self.assertNotIn((PFCTL,"-X","123456"),self.kernel.calls)

    def test_acquire_failure_preserves_ownership_intent(self):
        self.kernel.fail.add((PFCTL,"-E"))
        with self.assertRaisesRegex(ValueError,"KS_PF_COMMAND_FAILED"):
            self.pf.acquire_closed(CLOSED)
        self.assertEqual(self.lease.read()["phase"],"enable_pending")
        self.pf.release()
        self.assertTrue(self.pf.released())

if __name__=="__main__": unittest.main()
