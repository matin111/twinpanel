package main

import (
	"bytes"
	"errors"
	"io"
	"net"
	"testing"
	"time"
)

type fakeAddr string

func (a fakeAddr) Network() string { return "fake" }
func (a fakeAddr) String() string  { return string(a) }

type fakeConn struct {
	buf    bytes.Buffer
	fail   bool
	closed bool
}

func (c *fakeConn) Read([]byte) (int, error) { return 0, io.EOF }
func (c *fakeConn) Write(p []byte) (int, error) {
	if c.fail || c.closed {
		return 0, errors.New("write failed")
	}
	return c.buf.Write(p)
}
func (c *fakeConn) Close() error                     { c.closed = true; return nil }
func (c *fakeConn) LocalAddr() net.Addr              { return fakeAddr("local") }
func (c *fakeConn) RemoteAddr() net.Addr             { return fakeAddr("remote") }
func (c *fakeConn) SetDeadline(time.Time) error      { return nil }
func (c *fakeConn) SetReadDeadline(time.Time) error  { return nil }
func (c *fakeConn) SetWriteDeadline(time.Time) error { return nil }

func ipv4ICMP(src, dst [4]byte) []byte {
	p := make([]byte, 20)
	p[0] = 0x45
	p[9] = 1
	copy(p[12:16], src[:])
	copy(p[16:20], dst[:])
	return p
}

func TestIncidentICMPPreferredLanes(t *testing.T) {
	iranToExit := ipv4ICMP([4]byte{10, 254, 0, 21}, [4]byte{10, 254, 0, 22})
	exitToIran := ipv4ICMP([4]byte{10, 254, 0, 22}, [4]byte{10, 254, 0, 21})
	if got := flowHash(iranToExit) % 8; got != 1 {
		t.Fatalf("iran->exit preferred lane=%d, want 1", got)
	}
	if got := flowHash(exitToIran) % 8; got != 5 {
		t.Fatalf("exit->iran preferred lane=%d, want 5", got)
	}
}

func TestNewLaneRequiresHeartbeatPong(t *testing.T) {
	conn := &fakeConn{}
	lane := newLaneConn(1, conn)
	if lane.healthy() {
		t.Fatal("new lane must not carry payload before a real heartbeat pong")
	}
	if lane.expired(time.Now()) {
		t.Fatal("new unverified lane must receive startup grace")
	}
	lane.markPong()
	if !lane.healthy() {
		t.Fatal("lane should become payload-eligible after heartbeat pong")
	}
}

func TestForwardPacketSkipsUnverifiedPreferredLane(t *testing.T) {
	packet := ipv4ICMP([4]byte{10, 254, 0, 21}, [4]byte{10, 254, 0, 22})
	lanes := newLaneSet()
	unverified := &fakeConn{}
	fallback := &fakeConn{}

	preferred := lanes.set(1, unverified)
	good := lanes.set(2, fallback)
	good.markPong()

	if !forwardPacket(lanes, 8, packet) {
		t.Fatal("packet was not sent on verified fallback lane")
	}
	if preferred.closed.Load() {
		t.Fatal("unverified lane inside startup grace must not be closed by forwarding")
	}
	if unverified.buf.Len() != 0 {
		t.Fatalf("unverified preferred lane received %d bytes", unverified.buf.Len())
	}
	if fallback.buf.Len() != 4+len(packet) {
		t.Fatalf("verified fallback frame length=%d, want %d", fallback.buf.Len(), 4+len(packet))
	}
}

func TestForwardPacketRetriesNextHealthyLane(t *testing.T) {
	packet := ipv4ICMP([4]byte{10, 254, 0, 21}, [4]byte{10, 254, 0, 22})
	lanes := newLaneSet()
	bad := &fakeConn{fail: true}
	good := &fakeConn{}
	badLane := lanes.set(1, bad)
	goodLane := lanes.set(2, good)
	badLane.markPong()
	goodLane.markPong()

	if !forwardPacket(lanes, 8, packet) {
		t.Fatal("packet was not retried on fallback lane")
	}
	if !bad.closed {
		t.Fatal("failed preferred lane was not closed")
	}
	if good.buf.Len() != 4+len(packet) {
		t.Fatalf("fallback frame length=%d, want %d", good.buf.Len(), 4+len(packet))
	}
}
