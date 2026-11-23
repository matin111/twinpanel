"""Read-only trusted protocol report must never reveal tunnel secrets."""
from pathlib import Path
import sys
import tempfile
import json
import stat
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent.parent / "tool"
sys.path.insert(0, str(SOURCE))
import tun_admin_protocol_status as protocol


class TUNAdminProtocolTests(unittest.TestCase):
    def test_active_root_owned_config_matches_live_process_and_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "active-123456.json"
            config.write_text(json.dumps({
                "inbounds": [{"type": "tun"}],
                "outbounds": [{"type": "tuic", "tag": "proxy",
                               "password": "never-print-secret"}]}))
            config.chmod(0o600)
            fake_ps = f"{root}/sing-box run -c {config}\n"
            with patch.object(protocol.os, 'geteuid', return_value=0), \
                 patch.object(protocol.Path, 'lstat', autospec=True) as st:
                real = config.stat()
                st.return_value.st_uid = 0
                st.return_value.st_mode = real.st_mode
                st.return_value.st_size = real.st_size
                self.assertEqual(protocol.current_protocol(root, fake_ps), "tuic")
                st.return_value.st_mode = stat.S_IFREG | 0o666
                self.assertIsNone(protocol.current_protocol(root, fake_ps))

    def test_incorrect_engine_or_duplicate_profiles_never_claim_connected_type(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "active-123.json"
            config.write_text(json.dumps({
                "inbounds": [{"type": "tun"}],
                "outbounds": [{"type": "vless", "tag": "proxy"}]}))
            config.chmod(0o600)
            with patch.object(protocol.os, 'geteuid', return_value=0), \
                 patch.object(protocol.Path, 'lstat', autospec=True) as st:
                info = config.stat()
                st.return_value.st_uid = 0
                st.return_value.st_mode = info.st_mode
                st.return_value.st_size = info.st_size
                self.assertIsNone(protocol.current_protocol(root, "other-process"))
                (root / "active-456.json").touch()
                self.assertIsNone(protocol.current_protocol(
                    root, f"{root}/sing-box run -c {config}"))

    def test_shadowtls_is_attested_from_exact_two_stage_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "active-1234.json"
            profile = {
                "inbounds": [{"type": "tun"}],
                "outbounds": [
                    {"type": "shadowsocks", "tag": "proxy", "method": "aes-256-gcm",
                     "detour": "shadowtls-transport"},
                    {"type": "shadowtls", "tag": "shadowtls-transport", "version": 3}
                ]}
            config.write_text(json.dumps(profile))
            config.chmod(0o600)
            ps = f"{root}/sing-box run -c {config}\n"
            with patch.object(protocol.os, "geteuid", return_value=0), \
                 patch.object(protocol.Path, "lstat", autospec=True) as st:
                meta = config.stat()
                st.return_value.st_uid = 0
                st.return_value.st_mode = meta.st_mode
                st.return_value.st_size = meta.st_size
                self.assertEqual(protocol.current_protocol(root, ps), "shadowtls")
                profile["outbounds"][0]["detour"] = "unknown-tag"
                config.write_text(json.dumps(profile))
                st.return_value.st_size = config.stat().st_size
                self.assertIsNone(protocol.current_protocol(root, ps))
                profile["outbounds"][0]["detour"] = "shadowtls-transport"
                profile["outbounds"][1]["version"] = 2
                config.write_text(json.dumps(profile))
                st.return_value.st_size = config.stat().st_size
                self.assertIsNone(protocol.current_protocol(root, ps))

    def test_non_root_never_reads_private_profile(self):
        with patch.object(protocol.os, 'geteuid', return_value=501):
            self.assertIsNone(protocol.current_protocol())

    def test_sanitized_allowlist(self):
        self.assertEqual(protocol.ALLOWED['vless'], 'v2ray')
        self.assertEqual(protocol.ALLOWED['hysteria2'], 'hysteria2')
        self.assertEqual(protocol.ALLOWED['tuic'], 'tuic')
        self.assertNotIn('password', protocol.ALLOWED)


if __name__ == '__main__':
    unittest.main()