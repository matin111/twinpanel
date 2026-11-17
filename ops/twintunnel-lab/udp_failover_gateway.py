#!/usr/bin/env python3
"""TwinTunnel UDP failover CANARY; stable, local-only frontend.

Bound to 127.0.0.1:37961, this test-only relay forwards one UDP client session
unmodified to the existing Rakhsh datagram GRE and UDP echo lab paths.
It uses separate health probes that the *lab echo service* reflects.
It must NEVER be connected directly to production WireGuard/OpenVPN without
a real health endpoint, session-preserving return-path design and load tests.
"""
import argparse
import os
import secrets
import selectors
import signal
import socket
import struct
import time

FRONTEND = ("127.0.0.1", 37961)
CARRIERS = (("shabdiz-gre", ("127.0.0.1", 37921)),
            ("shabdiz-udp", ("127.0.0.1", 37933)))
INTERVAL = 0.45
HEALTH_WINDOW = 1.8
FAILBACK_STABLE = 1.4

class Gateway:
    def __init__(self):
        self.selector = selectors.DefaultSelector()
        self.frontend = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.frontend.bind(FRONTEND)
        self.frontend.setblocking(False)
        self.selector.register(self.frontend, selectors.EVENT_READ, ("front", None))
        self.backends = {}
        self.last_probe = {}
        self.last_healthy = {}
        self.health_since = {}
        self.last_nonce = {}
        self.stats = {"requests":0,"replies":0,"no_path":0,"changes":0,"health_sent":0}
        self.client = None
        self.active = None
        self.running = True
        self.start = time.monotonic()
        self.heartbeat_token = secrets.token_bytes(20)
        for name, addr in CARRIERS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(addr)
            sock.setblocking(False)
            self.backends[name] = sock
            self.selector.register(sock, selectors.EVENT_READ, ("back", name))
            self.last_healthy[name] = 0.0
            self.health_since[name] = None
            self.last_probe[name] = 0.0

    def stop(self, *_):
        self.running = False

    def heartbeat(self, now):
        for name, sock in self.backends.items():
            if now - self.last_probe[name] >= INTERVAL:
                nonce = secrets.token_bytes(8)
                data = b"TTLB1TT-UDP-LAB-HB/" + self.heartbeat_token + nonce
                self.last_nonce[name] = data
                try:
                    sock.send(data)
                    self.stats["health_sent"] += 1
                except OSError:
                    pass
                self.last_probe[name] = now

    def is_healthy(self, name, now):
        return now - self.last_healthy[name] <= HEALTH_WINDOW

    def choose(self, now):
        available = [name for name,_ in CARRIERS if self.is_healthy(name,now)]
        if not available:
            desired = None
        elif self.active in available:
            desired = self.active
            if self.active != CARRIERS[0][0] and CARRIERS[0][0] in available:
                first = CARRIERS[0][0]
                since = self.health_since[first]
                if since is not None and (now-since)>=FAILBACK_STABLE:
                    desired = first
        else:
            desired = available[0]
        if desired != self.active:
            prev=self.active
            self.active = desired
            self.stats["changes"] += 1
            print(f"ROUTE_CHANGE from={prev} to={desired} uptime={now-self.start:.2f}s", flush=True)

    def receive(self, sock, kind, name):
        try:
            data,addr=sock.recvfrom(65535)
        except (BlockingIOError,OSError):
            return
        now=time.monotonic()
        if kind == "front":
            # One stable source per canary to avoid unsafe cross-client reply mapping.
            if self.client is None:
                self.client=addr
                print("TEST_CLIENT_ASSIGNED",flush=True)
            if addr!=self.client:
                print("REJECT_SECOND_CLIENT",flush=True)
                return
            self.stats["requests"] += 1
            if self.active:
                try:self.backends[self.active].send(data)
                except OSError:self.stats["no_path"]+=1
            else:self.stats["no_path"]+=1
        else:
            if data == self.last_nonce.get(name):
                if not self.is_healthy(name,now):
                    self.health_since[name] = now
                self.last_healthy[name] = now
                return
            if data.startswith(b"TTLB1TT-UDP-LAB-HB/"):
                return
            if self.client:
                try:
                    self.frontend.sendto(data,self.client)
                    self.stats["replies"] += 1
                except OSError:pass

    def run(self, limit):
        print("CANARY_READY listen=127.0.0.1:37961 paths=GRE,UDP loopback_only=true",flush=True)
        next_report=self.start+5
        try:
            while self.running and time.monotonic()-self.start < limit:
                now=time.monotonic()
                self.heartbeat(now)
                self.choose(now)
                for key,_ in self.selector.select(timeout=0.07):
                    self.receive(key.fileobj,*key.data)
                if now>=next_report:
                    print("GATEWAY_STATS",self.stats,"active",self.active,flush=True)
                    next_report=now+5
        finally:
            print("CANARY_FINAL",self.stats,"active",self.active,flush=True)
            self.selector.close()
            self.frontend.close()
            for s in self.backends.values():s.close()

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--duration",type=int,default=180)
    opts=parser.parse_args()
    if not 10<=opts.duration<=600:
        parser.error("duration must be 10..600 seconds")
    gateway=Gateway()
    signal.signal(signal.SIGTERM,gateway.stop)
    signal.signal(signal.SIGINT,gateway.stop)
    gateway.run(opts.duration)