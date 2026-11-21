#!/usr/bin/env python3
"""Offline regression tests for the macOS unsigned local-proxy runner."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("standalone", HERE / "standalone_connection_manager.py")
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class StandaloneManagerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def config(self, obj):
        path = self.root / "config.json"
        path.write_text(json.dumps(obj))
        return path

    def test_all_fifteen_codes_registered(self):
        self.assertEqual(len(manager.PROTOCOLS), 15)
        self.assertEqual(len(set(manager.PROTOCOLS)), 15)
        listed = manager.list_protocols()
        self.assertFalse(listed["default_route_modified"])
        self.assertEqual(len(listed["protocols"]), 15)
        self.assertEqual(listed["mode"], "local_proxy_only")

    def test_xray_local_socks_only(self):
        config = self.config({
            "inbounds": [{"listen": "127.0.0.1", "port": 10808, "protocol": "socks"}],
            "outbounds": [{"protocol": "vless"}]
        })
        self.assertEqual(manager.validate("v2ray", config), 10808)

    def test_singbox_local_proxy(self):
        config = self.config({
            "inbounds": [{"listen": "127.0.0.1", "listen_port": 10809, "type": "mixed"}],
            "outbounds": [{"type": "hysteria2"}]
        })
        self.assertEqual(manager.validate("hysteria2", config), 10809)

    def test_rejects_full_tunnel(self):
        cfg = self.config({
            "inbounds": [{"type": "tun", "listen_port": 10809}],
            "outbounds": [{"type": "tuic"}]
        })
        with self.assertRaisesRegex(ValueError, "TUN"):
            manager.validate("tuic", cfg)

    def test_rejects_non_loopback(self):
        cfg = self.config({
            "inbounds": [{"listen": "0.0.0.0", "listen_port": 10809, "type": "mixed"}],
            "outbounds": [{"type": "tuic"}]
        })
        with self.assertRaisesRegex(ValueError, "NON_LOOPBACK"):
            manager.validate("tuic", cfg)

    def test_rejects_wrong_outbound(self):
        cfg = self.config({
            "inbounds": [{"listen_port": 10809, "type": "mixed"}],
            "outbounds": [{"type": "direct"}]
        })
        with self.assertRaisesRegex(ValueError, "OUTBOUND"):
            manager.validate("snell", cfg)

    def test_rejects_invalid_local_port(self):
        cfg = self.config({
            "inbounds": [{"listen_port": 80, "type": "mixed"}],
            "outbounds": [{"type": "socks"}]
        })
        with self.assertRaisesRegex(ValueError, "PORT"):
            manager.validate("socks5", cfg)

    def test_unimplemented_protocols_are_not_reported_ready(self):
        listed = {p["code"]: p for p in manager.list_protocols()["protocols"]}
        for code in ("wireguard", "amneziawg", "openvpn", "openconnect",
                     "l2tp", "mieru", "trusttunnel"):
            self.assertNotEqual(listed[code]["state"], "proxy_engine_present")


    def test_listener_waits_until_proxy_port_is_ready(self):
        process = mock.Mock()
        process.poll.return_value = None
        sock = mock.MagicMock()
        with mock.patch.object(manager.socket, "create_connection",
                               side_effect=[ConnectionRefusedError(), sock]) as conn, \
             mock.patch.object(manager.time, "sleep"):
            manager.wait_for_local_listener(process, 17089)
        self.assertEqual(conn.call_count, 2)
        conn.assert_called_with(("127.0.0.1", 17089), timeout=0.2)

    def test_listener_exited_before_ready(self):
        process = mock.Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(
            ValueError, "^ENGINE_EXITED_BEFORE_PROXY_READY$"
        ):
            manager.wait_for_local_listener(process, 17089)

    def test_safe_last_attempt_is_available_when_engine_stopped(self):
        with mock.patch.object(manager, "STATE", self.root / "state"):
            self.assertEqual(manager.last_attempt(), {"state": "not_recorded"})
            recorded = manager.record_attempt("naive", "LOCAL_PROFILE_INVALID")
            self.assertEqual(recorded, {
                "state": "last_attempt",
                "protocol": "naive",
                "reason": "LOCAL_PROFILE_INVALID",
            })
            observed = manager.last_attempt()
            self.assertEqual(
                {key: observed[key] for key in recorded}, recorded)
            self.assertIn(observed["age"], (
                "less_than_minute", "one_to_ten_minutes",
                "ten_to_sixty_minutes", "older_than_hour",
            ))
            self.assertEqual(manager.status(), {"state": "stopped"})
            self.assertEqual(
                manager.attempt_path().stat().st_mode & 0o777, 0o600)
            self.assertEqual(manager.STATE.stat().st_mode & 0o777, 0o700)
            with self.assertRaisesRegex(ValueError, "INVALID_ATTEMPT_CODE"):
                manager.record_attempt("naive", "user@example.com?token=SECRET")
            with self.assertRaisesRegex(ValueError, "UNKNOWN_PROTOCOL"):
                manager.record_attempt("unknown", "CONNECT_REQUESTED")
            observed = manager.last_attempt()
            self.assertEqual(
                {key: observed[key] for key in recorded}, recorded)
            self.assertIn(observed["age"], (
                "less_than_minute", "one_to_ten_minutes",
                "ten_to_sixty_minutes", "older_than_hour",
            ))

    def test_last_attempt_cannot_be_symlink_or_untrusted_record(self):
        with mock.patch.object(manager, "STATE", self.root / "state"):
            manager.record_attempt("tuic", "CONNECT_REQUESTED")
            attempt = manager.attempt_path()
            attempt.unlink()
            attempt.symlink_to(self.root / "secret")
            with self.assertRaisesRegex(ValueError, "INVALID_ATTEMPT_RECORD"):
                manager.last_attempt()
            attempt.unlink()
            attempt.write_text('{"state":"last_attempt","protocol":"naive",'
                               '"reason":"https://token.example"}')
            with self.assertRaisesRegex(ValueError, "INVALID_ATTEMPT_RECORD"):
                manager.last_attempt()

    def test_naive_local_proxy_config(self):
        cfg = self.config({
            "inbounds": [{"listen": "127.0.0.1", "listen_port": 10810, "type": "mixed"}],
            "outbounds": [{
                "type": "naive", "tag": "proxy",
                "server": "example.com", "server_port": 443,
            }],
            "route": {"final": "proxy"},
        })
        self.assertEqual(manager.validate("naive", cfg), 10810)
        self.assertEqual(manager.EXECUTABLE["naive"], "sing-box")

        # The verified route and outbound tag are mandatory: an unsigned
        # local proxy must never silently fall back to direct connections.
        untagged = self.config({
            "inbounds": [{"listen": "127.0.0.1", "listen_port": 10810, "type": "mixed"}],
            "outbounds": [{
                "type": "naive",
                "server": "example.com", "server_port": 443,
            }],
            "route": {"final": "proxy"},
        })
        with self.assertRaisesRegex(ValueError, "VERIFIED_PROXY_TAG_REQUIRED"):
            manager.validate("naive", untagged)

    def test_probe_verified_egress(self):
        record = {"protocol": "v2ray", "port": 10808, "pid": 42}
        result = subprocess.CompletedProcess([], 0, "203.0.113.12\n", "")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=result) as run:
            status = manager.probe("203.0.113.12")
        self.assertEqual(status["state"], "egress_verified")
        self.assertFalse(status["system_wide_vpn"])
        command = run.call_args.args[0]
        self.assertIn("socks5h://127.0.0.1:10808", command)
        self.assertIn("--noproxy", command)

    def test_probe_fails_closed_without_process(self):
        with mock.patch.object(manager, "read_state", return_value=None):
            with self.assertRaisesRegex(ValueError, "ENGINE_NOT_RUNNING"):
                manager.probe()

    def test_probe_ip_mismatch_is_not_verified(self):
        record = {"protocol": "naive", "port": 10810, "pid": 42}
        result = subprocess.CompletedProcess([], 0, "203.0.113.13\n", "")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=result):
            status = manager.probe("203.0.113.12")
        self.assertEqual(status["state"], "egress_ip_mismatch")
        self.assertFalse(status["verified_expected_egress"])


    def test_proxy_failure_codes_do_not_expose_remote_details(self):
        self.assertEqual(manager.proxy_failure_category(7),
                         "PROXY_TCP_UNREACHABLE")
        self.assertEqual(manager.proxy_failure_category(28),
                         "PROXY_OR_REMOTE_TIMEOUT")
        self.assertEqual(manager.proxy_failure_category(97),
                         "PROXY_SOCKS_HANDSHAKE_FAILED")
        self.assertEqual(manager.proxy_failure_category(123456),
                         "PROXY_EGRESS_REQUEST_FAILED")

    def test_probe_curl_failure_reports_safe_status_only(self):
        record = {"protocol": "hysteria2", "port": 17089, "pid": 42}
        result = subprocess.CompletedProcess([], 28, "", "remote.example secret=hello")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "^PROXY_OR_REMOTE_TIMEOUT$"):
                manager.probe()

    def test_curl_tcp_error_identifies_missing_local_socks_listener(self):
        record = {"protocol": "shadowtls", "port": 17089, "pid": 42}
        failed = subprocess.CompletedProcess([], 7, "", "PRIVATE_HOST")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=failed), \
             mock.patch.object(manager.socket, "create_connection",
                               side_effect=ConnectionRefusedError()):
            with self.assertRaisesRegex(
                ValueError, "^LOCAL_SOCKS_LISTENER_UNREACHABLE$"
            ):
                manager.probe()

    def test_curl_tcp_error_with_listener_identifies_upstream_failure(self):
        record = {"protocol": "shadowtls", "port": 17089, "pid": 42}
        failed = subprocess.CompletedProcess([], 7, "", "PRIVATE_HOST")
        connection = mock.MagicMock()
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=failed), \
             mock.patch.object(manager.socket, "create_connection",
                               return_value=connection) as connect:
            with self.assertRaisesRegex(
                ValueError, "^SOCKS_UPSTREAM_TCP_FAILED$"
            ):
                manager.probe()
        connect.assert_called_once_with(("127.0.0.1", 17089), timeout=0.7)

    def test_diagnosis_classifies_logs_without_returning_secrets(self):
        logfile = self.root / "engine.log"
        logfile.write_text(
            "private-token=secret-value\ntransport QUIC handshake timeout\n")
        with mock.patch.object(manager, "STATE", self.root):
            reason = manager.engine_failure_category()
        self.assertEqual(reason, "ENGINE_REMOTE_TIMEOUT")
        self.assertNotIn("secret-value", reason)


    def test_diagnosis_prefers_remote_auth_over_generic_quic(self):
        logfile = self.root / "engine.log"
        logfile.write_text("private-password=secret_value\nQUIC authentication failed\n")
        with mock.patch.object(manager, "STATE", self.root):
            reason = manager.engine_failure_category()
        self.assertEqual(reason, "HYSTERIA2_REMOTE_AUTH_REJECTED")
        self.assertNotIn("secret_value", reason)

    def test_diagnosis_classifies_refused_and_cert_errors(self):
        logfile = self.root / "engine.log"
        with mock.patch.object(manager, "STATE", self.root):
            logfile.write_text("connect: connection refused\n")
            self.assertEqual(manager.engine_failure_category(),
                             "ENGINE_REMOTE_CONNECTION_REFUSED")
            logfile.write_text("tls: x509: certificate signed by unknown authority\n")
            self.assertEqual(manager.engine_failure_category(),
                             "TLS_CERTIFICATE_UNTRUSTED_CA")

    def test_diagnose_distinguishes_empty_stale_and_missing_logs(self):
        with mock.patch.object(manager, "STATE", self.root):
            self.assertEqual(manager.diagnose()["engine_log_state"],
                             "missing_or_unreadable")
            self.assertEqual(manager.diagnose()["engine_log_age"], "missing")
            log = self.root / "engine.log"
            log.touch()
            diagnosis = manager.diagnose()
            self.assertEqual(diagnosis["engine_log_state"], "empty")
            self.assertEqual(diagnosis["reason"],
                             "ENGINE_FAILURE_NOT_CLASSIFIED")
            self.assertEqual(diagnosis["engine_log_age"], "less_than_minute")
            log.write_text("Unknown panic details account_password=SECRET")
            diagnosis = manager.diagnose()
            self.assertEqual(diagnosis["engine_log_state"], "nonempty")
            self.assertNotIn("SECRET", str(diagnosis))
            import os
            old = manager.time.time() - 4000
            os.utime(log, (old, old))
            self.assertEqual(manager.diagnose()["engine_log_age"],
                             "older_than_hour")

    def test_silent_naive_early_exit_reports_specific_safe_code(self):
        cfg = self.config({
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1",
                          "listen_port": 17893}],
            "outbounds": [{"type": "naive", "tag": "proxy",
                           "server": "example.com", "server_port": 443}],
            "route": {"final": "proxy"},
        })
        exe = self.root / "sing-box"
        exe.touch()
        proc = mock.Mock()
        proc.pid = 11111
        proc.poll.return_value = 1
        with mock.patch.object(manager, "STATE", self.root / "state"), \
             mock.patch.object(manager, "binary_for", return_value=exe), \
             mock.patch.object(manager, "read_state", return_value=None), \
             mock.patch.object(manager.subprocess, "Popen", return_value=proc), \
             mock.patch.object(manager.time, "sleep"):
            with self.assertRaisesRegex(
                ValueError, "^ENGINE_EXITED_WITHOUT_LOG$"
            ):
                manager.start("naive", cfg)
        proc.poll.return_value = -11
        with mock.patch.object(manager, "STATE", self.root / "state"), \
             mock.patch.object(manager, "binary_for", return_value=exe), \
             mock.patch.object(manager, "read_state", return_value=None), \
             mock.patch.object(manager.subprocess, "Popen", return_value=proc), \
             mock.patch.object(manager.time, "sleep"):
            with self.assertRaisesRegex(
                ValueError, "^ENGINE_TERMINATED_BY_SIGNAL$"
            ):
                manager.start("naive", cfg)

    def test_naive_early_exit_returns_safe_cronet_diagnostic(self):
        cfg = self.config({
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1",
                          "listen_port": 17891}],
            "outbounds": [{"type": "naive", "tag": "proxy",
                           "server": "example.com", "server_port": 443}],
            "route": {"final": "proxy"},
        })
        fake_executable = self.root / "sing-box"
        fake_executable.write_text("")
        proc = mock.Mock()
        proc.pid = 34567
        proc.poll.return_value = 1

        def failed_engine(_args, **kwargs):
            kwargs["stdout"].write(
                "FATAL[0000] initialize outbound: cronet: library not found\n"
                "Authorization=SECRET_CONNECTION_TOKEN\n"
            )
            kwargs["stdout"].flush()
            return proc

        with mock.patch.object(manager, "STATE", self.root / "state"), \
             mock.patch.object(manager, "binary_for", return_value=fake_executable), \
             mock.patch.object(manager, "read_state", return_value=None), \
             mock.patch.object(manager.subprocess, "Popen",
                               side_effect=failed_engine), \
             mock.patch.object(manager.time, "sleep"):
            with self.assertRaisesRegex(
                ValueError, "^NAIVE_CRONET_LIBRARY_MISSING$"
            ) as failure:
                manager.start("naive", cfg)
            self.assertNotIn("SECRET_CONNECTION_TOKEN", str(failure.exception))

    def test_safe_naive_fatal_categories_do_not_echo_private_logs(self):
        logfile = self.root / "engine.log"
        cases = {
            "FATAL[0000] create service: initialize outbound[0]: TLS required":
                "NAIVE_TLS_REQUIRED",
            "FATAL[0000] cronet: library not found secret=TOP_SECRET":
                "NAIVE_CRONET_LIBRARY_MISSING",
            "FATAL[0000] unsupported on naive outbound secret=TOP_SECRET":
                "NAIVE_TLS_OPTION_UNSUPPORTED",
            "FATAL[0000] invalid certificate secret=TOP_SECRET":
                "NAIVE_TLS_CERTIFICATE_INVALID",
            "FATAL[0000] unknown field tls.foo secret=TOP_SECRET":
                "ENGINE_CONFIG_UNSUPPORTED_FIELD",
            "FATAL[0000] unexpected failure at server TOP_SECRET":
                "ENGINE_STARTUP_FATAL_UNCLASSIFIED",
        }
        with mock.patch.object(manager, "STATE", self.root):
            for log, expected in cases.items():
                with self.subTest(log=expected):
                    logfile.write_text(log)
                    category = manager.engine_failure_category()
                    self.assertEqual(category, expected)
                    self.assertNotIn("TOP_SECRET", category)

    def test_start_truncates_stale_engine_log(self):
        log = self.root / "engine.log"
        log.write_text("STALE_SECRET_OLD_QUIC_TIMEOUT")
        cfg = self.config({
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1",
                          "listen_port": 17890}],
            "outbounds": [{"type": "hysteria2", "tag": "proxy"}]
        })
        fake_executable = self.root / "sing-box"
        fake_executable.write_text("")
        fake_proc = mock.Mock()
        fake_proc.pid = 123456
        fake_proc.poll.return_value = None
        with mock.patch.object(manager, "STATE", self.root), \
             mock.patch.object(manager, "binary_for", return_value=fake_executable), \
             mock.patch.object(manager, "read_state", return_value=None), \
             mock.patch.object(manager.subprocess, "Popen", return_value=fake_proc), \
             mock.patch.object(manager.time, "sleep"), \
             mock.patch.object(manager, "wait_for_local_listener") as ready, \
             mock.patch.object(manager, "save_state"):
            result = manager.start("hysteria2", cfg)
        ready.assert_called_once_with(fake_proc, 17890)
        self.assertEqual(result["state"], "process_running_unverified")
        self.assertEqual(log.read_text(), "")


    def test_tls_diagnostics_distinguish_hostname_ca_and_expiry(self):
        log = self.root / "engine.log"
        cases = {
            "x509: certificate is valid for good.example, not bad.example":
                "TLS_CERTIFICATE_HOSTNAME_MISMATCH",
            "x509: certificate signed by unknown authority":
                "TLS_CERTIFICATE_UNTRUSTED_CA",
            "x509: certificate has expired or is not yet valid":
                "TLS_CERTIFICATE_EXPIRED_OR_CLOCK",
        }
        with mock.patch.object(manager, "STATE", self.root):
            for message, expected in cases.items():
                log.write_text(message)
                self.assertEqual(manager.engine_failure_category(), expected)


    def test_stop_waits_until_engine_exits_before_deleting_state(self):
        record = {"protocol": "hysteria2", "pid": 4242,
                  "executable": "/safe/sing-box", "config": "/private/test.json"}
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches",
                               side_effect=[True, True, False]), \
             mock.patch.object(manager.os, "kill") as kill, \
             mock.patch.object(manager.time, "sleep"), \
             mock.patch.object(manager, "state_path",
                               return_value=self.root / "current.json"):
            (self.root / "current.json").write_text("{}")
            result = manager.stop()
        self.assertEqual(result["state"], "stopped")
        kill.assert_called_once_with(4242, manager.signal.SIGTERM)
        self.assertFalse((self.root / "current.json").exists())

    def test_stop_escalates_only_validated_owned_process(self):
        record = {"protocol": "hysteria2", "pid": 4242}
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches",
                               side_effect=[True] * 32 + [False]), \
             mock.patch.object(manager.os, "kill") as kill, \
             mock.patch.object(manager.time, "sleep"), \
             mock.patch.object(manager, "state_path",
                               return_value=self.root / "current.json"):
            (self.root / "current.json").write_text("{}")
            result = manager.stop()
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(kill.call_args_list, [
            mock.call(4242, manager.signal.SIGTERM),
            mock.call(4242, manager.signal.SIGKILL)
        ])

    def test_stop_keeps_state_when_engine_refuses_to_exit(self):
        record = {"protocol": "hysteria2", "pid": 4242}
        state = self.root / "current.json"
        state.write_text("{}")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.os, "kill"), \
             mock.patch.object(manager.time, "sleep"), \
             mock.patch.object(manager, "state_path", return_value=state):
            with self.assertRaisesRegex(
                ValueError, "ENGINE_STILL_RUNNING_STATE_PRESERVED"
            ):
                manager.stop()
        self.assertTrue(state.exists())

    def test_stop_stale_record_never_kills_unknown_pid(self):
        record = {"protocol": "hysteria2", "pid": 4242}
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=False), \
             mock.patch.object(manager.os, "kill") as kill, \
             mock.patch.object(manager, "state_path",
                               return_value=self.root / "current.json"):
            result = manager.stop()
        self.assertEqual(result["state"], "stopped")
        kill.assert_not_called()


    def test_watchdog_stops_engine_when_app_process_exits(self):
        record = {"pid": 4412, "owner_pid": 1309, "owner_started": "birth1"}
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager, "process_start_signature",
                               return_value=None), \
             mock.patch.object(manager, "stop",
                               return_value={"state": "stopped"}) as stop:
            result = manager.watch_owner(1309, 4412, "birth1")
        self.assertEqual(result["state"], "stopped")
        stop.assert_called_once()

    def test_watchdog_never_stops_replaced_engine(self):
        record = {"pid": 991, "owner_pid": 1309, "owner_started": "birth1"}
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "stop") as stop:
            result = manager.watch_owner(1309, 4412, "birth1")
        self.assertEqual(result["state"], "watcher_finished")
        stop.assert_not_called()

    def test_watchdog_pid_reuse_must_not_count_as_live_owner(self):
        record = {"pid": 4412, "owner_pid": 1309, "owner_started": "birth1"}
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager, "process_start_signature",
                               return_value="different_birth"), \
             mock.patch.object(manager, "stop",
                               return_value={"state": "stopped"}) as stop:
            self.assertEqual(
                manager.watch_owner(1309, 4412, "birth1")["state"], "stopped"
            )
        stop.assert_called_once()

    def test_start_requires_alive_owner_when_owner_supplied(self):
        cfg = self.config({
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1",
                          "listen_port": 18001}],
            "outbounds": [{"type": "hysteria2"}]
        })
        with mock.patch.object(manager, "binary_for",
                               return_value=self.root / "sing-box"), \
             mock.patch.object(manager, "read_state", return_value=None), \
             mock.patch.object(manager, "process_start_signature",
                               return_value=None), \
             mock.patch.object(manager.subprocess, "Popen") as spawned:
            with self.assertRaisesRegex(ValueError, "PROXY_OWNER_NOT_RUNNING"):
                manager.start("hysteria2", cfg, 1234)
        spawned.assert_not_called()


    def test_measured_profile_is_private_and_source_unchanged(self):
        source = self.config({
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1",
                          "listen_port": 17089}],
            "outbounds": [{"type": "hysteria2", "tag": "proxy"}],
        })
        original = source.read_bytes()
        with mock.patch.object(manager, "STATE", self.root / "private"):
            runtime, port, secret = manager.measured_runtime_config("hysteria2", source)
            self.assertNotEqual(runtime, source)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o600)
            self.assertEqual(runtime.parent.stat().st_mode & 0o777, 0o700)
            self.assertTrue(1024 <= port <= 65535)
            self.assertGreaterEqual(len(secret), 32)
            generated = json.loads(runtime.read_text())
            api = generated["experimental"]["clash_api"]
            self.assertEqual(api["external_controller"], f"127.0.0.1:{port}")
            self.assertEqual(api["secret"], secret)
            self.assertFalse(api["access_control_allow_private_network"])
            manager.cleanup_runtime_config({"managed_profile": str(runtime)})
            self.assertFalse(runtime.exists())

    def test_traffic_reads_authenticated_local_counter_without_secrets(self):
        secret = "a" * 48
        state = {"pid": 42, "protocol": "hysteria2",
                 "metrics_port": 17293, "metrics_secret": secret}
        connection = mock.Mock()
        reply = connection.getresponse.return_value
        reply.status = 200
        reply.read.return_value = b'{"uploadTotal":2345,"downloadTotal":6789}'
        with mock.patch.object(manager, "read_state", return_value=state), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.http.client, "HTTPConnection",
                               return_value=connection) as client:
            result = manager.traffic()
        client.assert_called_once_with("127.0.0.1", 17293, timeout=2)
        request = connection.request.call_args
        self.assertEqual(request.args[:2], ("GET", "/connections"))
        self.assertEqual(request.kwargs["headers"]["Authorization"],
                         "Bearer " + secret)
        self.assertEqual(result["download_bytes"], 6789)
        self.assertEqual(result["upload_bytes"], 2345)
        self.assertEqual(result["mode"], "local_proxy_only")
        self.assertNotIn(secret, repr(result))

    def test_traffic_unavailable_does_not_fabricate_counters(self):
        state = {"pid": 42, "metrics_port": 17293,
                 "metrics_secret": "a" * 48}
        connection = mock.Mock()
        reply = connection.getresponse.return_value
        reply.status = 200
        reply.read.return_value = b'{"connections":[]}'
        with mock.patch.object(manager, "read_state", return_value=state), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.http.client, "HTTPConnection",
                               return_value=connection):
            with self.assertRaisesRegex(ValueError, "TRAFFIC_MONITOR_UNAVAILABLE"):
                manager.traffic()


    def test_new_singbox_protocols_use_real_local_manager(self):
        for protocol, outbound in [
            ("tuic", {"type": "tuic", "uuid": "f3cd1140-2eb6-4c84-976c-8b72177ead67",
                      "password": "secret"}),
            ("anytls", {"type": "anytls", "password": "secret"}),
            ("socks5", {"type": "socks", "version": "5",
                        "username": "user", "password": "secret"}),
            ("snell", {"type": "snell", "version": 4,
                       "psk": "secret-credentials"}),
        ]:
            with self.subTest(protocol=protocol):
                outbound = {**outbound, "tag": "proxy"}
                conf = self.config({
                    "inbounds": [{
                        "type": "mixed", "listen": "127.0.0.1",
                        "listen_port": 17089
                    }],
                    "outbounds": [outbound],
                    "route": {"final": "proxy"}
                })
                self.assertEqual(manager.validate(protocol, conf), 17089)
                with mock.patch.object(manager, "STATE", self.root / protocol):
                    managed, port, secret = manager.measured_runtime_config(
                        protocol, conf)
                    self.assertNotEqual(managed, conf)
                    self.assertIsInstance(port, int)
                    self.assertGreaterEqual(len(secret), 32)
                    data = json.loads(managed.read_text())
                    self.assertEqual(data["outbounds"], [outbound])
                    self.assertEqual(data["route"], {"final": "proxy"})
                    self.assertEqual(data["experimental"]["clash_api"][
                        "external_controller"], f"127.0.0.1:{port}")
                    manager.cleanup_runtime_config(
                        {"managed_profile": str(managed)})

    def test_new_protocols_reject_direct_fallback(self):
        main = {"type": "tuic", "tag": "proxy"}
        local = {"type": "mixed", "listen": "127.0.0.1",
                 "listen_port": 17089}
        for bad in [
            {"inbounds": [local], "outbounds": [main],
             "route": {"final": "direct"}},
            {"inbounds": [local], "outbounds": [main, {
                "type": "direct", "tag": "direct"}],
             "route": {"final": "proxy"}},
            {"inbounds": [local], "outbounds": [main],
             "route": {"final": "proxy", "rules": [
                 {"action": "route", "outbound": "direct"}]}},
            {"inbounds": [local], "outbounds": [main],
             "route": {"final": "proxy"},
             "dns": {"servers": [{"tag": "local", "type": "local"}]}},
        ]:
            with self.subTest(bad=bad):
                conf = self.config(bad)
                with self.assertRaises(ValueError):
                    manager.validate("tuic", conf)

    def test_naive_and_shadowtls_are_strict_loopback_only(self):
        naive = {
            "inbounds": [{"type": "mixed", "listen": "127.0.0.1",
                          "listen_port": 17089}],
            "outbounds": [{"type": "naive", "tag": "proxy",
                           "server": "example.com", "server_port": 443,
                           "username": "u", "password": "p",
                           "tls": {"enabled": True, "server_name": "example.com"}}],
            "route": {"final": "proxy"}
        }
        shadow = {
            "inbounds": naive["inbounds"],
            "outbounds": [
                {"type": "shadowsocks", "tag": "proxy",
                 "method": "aes-128-gcm", "password": "ss-key",
                 "detour": "shadowtls-transport"},
                {"type": "shadowtls", "tag": "shadowtls-transport",
                 "version": 3, "server": "example.com", "server_port": 443,
                 "password": "transport-key",
                 "tls": {"enabled": True, "server_name": "example.com"}}
            ],
            "route": {"final": "proxy"}
        }
        for code, profile in (("naive", naive), ("shadowtls", shadow)):
            with self.subTest(protocol=code):
                config = self.config(profile)
                self.assertEqual(manager.validate(code, config), 17089)
                with mock.patch.object(manager, "STATE", self.root / code):
                    runtime, port, secret = manager.measured_runtime_config(
                        code, config)
                    self.assertTrue(runtime.is_file())
                    self.assertIsInstance(port, int)
                    self.assertGreaterEqual(len(secret), 32)
                    generated = json.loads(runtime.read_text())
                    self.assertEqual(generated["outbounds"], profile["outbounds"])
                    manager.cleanup_runtime_config({"managed_profile": str(runtime)})
        direct = dict(shadow)
        direct["outbounds"] = [*shadow["outbounds"], {
            "type": "direct", "tag": "direct"}]
        with self.assertRaises(ValueError):
            manager.validate("shadowtls", self.config(direct))
        wrongDetour = dict(shadow)
        wrongDetour["outbounds"] = [dict(shadow["outbounds"][0]),
                                    shadow["outbounds"][1]]
        wrongDetour["outbounds"][0]["detour"] = "direct"
        with self.assertRaises(ValueError):
            manager.validate("shadowtls", self.config(wrongDetour))

    def test_new_protocols_never_accept_system_tun(self):
        for protocol, outbound in [
            ("tuic", {"type": "tuic"}),
            ("anytls", {"type": "anytls"}),
            ("socks5", {"type": "socks"}),
            ("snell", {"type": "snell"}),
        ]:
            with self.subTest(protocol=protocol):
                conf = self.config({
                    "inbounds": [{"type": "tun",
                                  "listen": "127.0.0.1",
                                  "listen_port": 17089}],
                    "outbounds": [outbound]
                })
                with self.assertRaisesRegex(
                    ValueError, "TUN_OR_NON_PROXY_INBOUND_FORBIDDEN"
                ):
                    manager.validate(protocol, conf)


if __name__ == "__main__":
    unittest.main()
