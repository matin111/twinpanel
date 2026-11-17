#!/usr/bin/env python3
"""Loopback-only TCP echo target for isolated Rakhsh multi-link tests."""
import socketserver

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(120)
        while True:
            try:
                chunk = self.request.recv(65536)
            except TimeoutError:
                return
            if not chunk:
                return
            self.request.sendall(chunk)

class EchoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    with EchoServer(("127.0.0.1", 37942), Handler) as server:
        print("TwinTunnel multi-link TCP lab echo ready on loopback", flush=True)
        server.serve_forever(poll_interval=0.3)