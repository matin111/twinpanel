"""Isolated Rakhsh three-carrier handshake smoke test.

Requires a pinned, checksum-verified Rakhsh binary in RAKHSH_BIN.
Runs ONLY on 127.0.0.1, never touches routes, firewall or customer tunnels.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run():
    binary = os.environ.get("RAKHSH_BIN")
    if not binary or not Path(binary).is_file():
        raise RuntimeError("RAKHSH_BIN is required; pin and verify its SHA256 in CI")
    primary, kcp = free_port(), free_port()
    while kcp == primary:
        kcp = free_port()
    with tempfile.TemporaryDirectory(prefix="twintunnel-three-links-") as td:
        root = Path(td)
        init = subprocess.run(
            [binary, "init", "--tunnel-addr", f"127.0.0.1:{primary}",
             "--carrier", "wss", "--sni", "www.bing.com", "--lanes", "4",
             "--encryption", "full", "--link", "quicv2", "--link", f"kcp:{kcp}", "--resume"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        # Do not log or persist the generated token/static private keys.
        parts = init.stdout.split("########## entry", 1)
        if len(parts) != 2:
            raise RuntimeError("Rakhsh init did not produce a matched pair")
        raw_entry, divider, raw_exit = parts[1].partition("########## exit")
        if not divider:
            raise RuntimeError("Rakhsh init omitted the exit configuration")
        procs = []
        try:
            for role, raw in (("entry", raw_entry), ("exit", raw_exit)):
                config = raw.replace("0.0.0.0:", "127.0.0.1:")
                config = config.replace(
                    f'role = "{role}"',
                    f'role = "{role}"\\nlink_policy = "spread"\\ncontrol_socket = "{root / (role + ".sock")}"',
                    1,
                )
                path = root / f"{role}.toml"
                path.write_text(config, encoding="utf-8")
                path.chmod(0o600)
                subprocess.run([binary, "check", "-c", str(path)],
                               capture_output=True, timeout=15, check=True)
            for role in ("entry", "exit"):
                log = (root / f"{role}.log").open("wb")
                proc = subprocess.Popen([binary, "run", "-c", str(root / (role + ".toml"))],
                                        stdout=log, stderr=subprocess.STDOUT)
                log.close()
                procs.append(proc)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if any(p.poll() is not None for p in procs):
                    raise AssertionError("Rakhsh process exited during handshake")
                try:
                    out = subprocess.run([binary, "status", "-c", str(root / "exit.toml"), "--json"],
                                         text=True, capture_output=True, timeout=3)
                    if out.returncode == 0:
                        state = json.loads(out.stdout)
                        names = {link.get("label") for link in state.get("links", [])}
                        if state.get("lanes_up") == 4 and {"wss", "quicv2", "kcp"} <= names:
                            print("TWINTUNNEL_RAKHSH_THREE_TRANSPORT_LOOPBACK_OK")
                            return
                except (ValueError, subprocess.TimeoutExpired):
                    pass
                time.sleep(0.25)
            raise AssertionError("Three authenticated transports were not established")
        finally:
            for p in procs:
                if p.poll() is None:
                    p.terminate()
            for p in procs:
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=5)


if __name__ == "__main__":
    run()
