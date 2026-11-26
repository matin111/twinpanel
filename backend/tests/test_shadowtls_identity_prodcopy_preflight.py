"""Pure production-copy ShadowTLS preflight regression, with no daemon or DB."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/"scripts/twinpanel_shadowtls_identity_prodcopy_preflight.py"
SPEC=importlib.util.spec_from_file_location("tp_shadowtls_preflight",SOURCE)
assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ProductionCopyPreflightTests(TestCase):
    def fixture(self,root:Path)->tuple[Path,Path]:
        config=root/"node.json"
        config.write_text(json.dumps({
            "inbounds":[
                {"type":"shadowtls","tag":"twinpanel-shadowtls-in",
                 "listen":"127.0.0.1","listen_port":8448,"version":3,
                 "users":[{"name":"tp-sub-42","password":"sample-old-pass"}],
                 "detour":"twinpanel-shadowtls-inner"},
                {"type":"shadowsocks","tag":"twinpanel-shadowtls-inner",
                 "listen":"127.0.0.1","method":"aes-256-gcm","password":"sample-inner-pass"}],
            "outbounds":[{"type":"direct","tag":"direct"}]
        }),encoding="utf-8")
        binary=root/"fake-sing-box"
        binary.write_text("#!/bin/sh\nexit 0\n",encoding="utf-8")
        binary.chmod(0o700)
        return config,binary

    def test_valid_parallel_copy_checks_without_replacing_original(self):
        with tempfile.TemporaryDirectory() as temp:
            config,binary=self.fixture(Path(temp))
            before=config.read_bytes()
            commands=[]
            def run(command,**kwargs):
                commands.append(command)
                return SimpleNamespace(returncode=0,stdout="",stderr="")
            with patch.object(subprocess,"run",side_effect=run):
                result=module.validate_copy(config,binary,19448)
            self.assertTrue(result["ok"])
            self.assertEqual(result["parallel_authenticated_users"],1)
            self.assertTrue(result["legacy_inbounds_preserved"])
            self.assertFalse(result["service_restarted"])
            self.assertFalse(result["installed"])
            self.assertFalse(result["delivery_enabled"])
            self.assertEqual(config.read_bytes(),before)
            self.assertEqual([item[0] for item in commands],["ss",str(binary)])
            self.assertIn("check",commands[1])

    def test_occupied_candidate_port_is_rejected_without_check(self):
        with tempfile.TemporaryDirectory() as temp:
            config,binary=self.fixture(Path(temp))
            with patch.object(subprocess,"run",return_value=SimpleNamespace(
                returncode=0,
                stdout="LISTEN 0 4096 0.0.0.0:19448 0.0.0.0:*\n",
                stderr=""
            )) as run:
                with self.assertRaisesRegex(RuntimeError,"CANDIDATE_PORT_IN_USE"):
                    module.validate_copy(config,binary,19448)
            self.assertEqual(run.call_count,1)

    def test_binary_failure_does_not_enable_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            config,binary=self.fixture(Path(temp))
            def run(command,**kwargs):
                return SimpleNamespace(returncode=0 if command[0]=="ss" else 1,
                                       stdout="",stderr="secret-should-not-be-shown")
            with patch.object(subprocess,"run",side_effect=run):
                with self.assertRaisesRegex(RuntimeError,"PARALLEL_SINGBOX_CONFIG_CHECK_FAILED"):
                    module.validate_copy(config,binary,19448)


if __name__=="__main__":
    main()
