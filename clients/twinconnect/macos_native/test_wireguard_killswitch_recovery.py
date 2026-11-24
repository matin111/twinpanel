"""Bounded recovery proof must not weaken normal remote route protection."""
import unittest
from unittest.mock import patch
import wireguard_management_route_guard as guard

class BoundedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.current={"worker_pid":123,"full_interface":"utun15","protocol_code":"wireguard"}
        self.nonce="a"*32
        self.rules=["pass quick on lo0 all no state","pass quick on utun15 all no state","block drop quick all"]
        self.lease={"phase":"owned","locked":False,"nonce":self.nonce,"pid":123,"interface":"utun15","token":"12345","canonical":self.rules}
        self.ready={"nonce":self.nonce,"deadline":5110}
        self.status={"version":1,"persistent":False,"session_limit":120,"state":"active","expires_at":5110,"timestamp":5000}
        self.job="state = running\n"+str(guard.KS_CONTROL_ROOT/"unsigned_killswitch_console_control.py")+"\n--watchdog\n"+self.nonce
    def accepts(self,job=None,live=None,info="Status: Enabled",now=5000):
        with patch.object(guard,"read_trusted_ks_json",side_effect=[self.lease,self.ready,self.status,self.lease]), patch.object(guard,"ks_recovery_command",side_effect=[info,"\n".join(self.rules) if live is None else live,self.job if job is None else job]), patch.object(guard.time,"time",return_value=now):
            return guard.bounded_killswitch_recovery(self.current)
    def test_active(self): self.assertTrue(self.accepts())
    def test_wrong_worker(self):
        self.lease["pid"]=124
        self.assertFalse(self.accepts())
    def test_stale(self):
        self.status["timestamp"]=4980
        self.assertFalse(self.accepts())
    def test_expired(self): self.assertFalse(self.accepts(now=5111))
    def test_disabled_pf(self): self.assertFalse(self.accepts(info="Status: Disabled"))
    def test_missing_recovery(self): self.assertFalse(self.accepts(job="state = not running"))
    def test_drift(self): self.assertFalse(self.accepts(live="pass all"))
    def test_other_protocol(self):
        self.current["protocol_code"]="amneziawg"
        self.assertFalse(self.accepts())
    def test_persistent(self):
        self.status["persistent"]=True
        self.assertFalse(self.accepts())
    def test_missing_lease(self):
        with patch.object(guard,"read_trusted_ks_json",side_effect=FileNotFoundError):
            self.assertFalse(guard.bounded_killswitch_recovery(self.current))

if __name__=="__main__": unittest.main()
