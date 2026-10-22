package main

import (
	"bufio"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/binary"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
	"unsafe"
)

const (
	tunSetIFF = 0x400454ca
	iffTun    = 0x0001
	iffNoPI   = 0x1000
	magic     = "TP27TCP3"
	maxPacket = 65535

	framePing uint32 = 0
	framePong uint32 = ^uint32(0)

	heartbeatInterval       = 1 * time.Second
	startupHeartbeatTimeout = 8 * time.Second
	heartbeatTimeout        = 12 * time.Second
	writeTimeout            = 2500 * time.Millisecond
	tunWriteTimeout         = 500 * time.Millisecond
	tunWriteRetryInterval   = 2 * time.Millisecond
	tcpUserTimeoutMS        = 20000
)

type ifreqFlags struct {
	Name  [16]byte
	Flags uint16
	pad   [22]byte
}

type laneConn struct {
	id        int
	conn      net.Conn
	writeMu   sync.Mutex
	createdAt time.Time
	lastPong  atomic.Int64
	verified  atomic.Bool
	closed    atomic.Bool
}

func newLaneConn(id int, c net.Conn) *laneConn {
	return &laneConn{id: id, conn: c, createdAt: time.Now()}
}

func (l *laneConn) close() {
	if l == nil || l.conn == nil {
		return
	}
	if l.closed.CompareAndSwap(false, true) {
		_ = l.conn.Close()
	}
}

func (l *laneConn) healthy() bool {
	if l == nil || l.conn == nil || l.closed.Load() || !l.verified.Load() {
		return false
	}
	stamp := l.lastPong.Load()
	if stamp <= 0 {
		return false
	}
	return time.Since(time.Unix(0, stamp)) <= heartbeatTimeout
}

func (l *laneConn) expired(now time.Time) bool {
	if l == nil || l.conn == nil || l.closed.Load() {
		return true
	}
	stamp := l.lastPong.Load()
	if stamp <= 0 {
		return now.Sub(l.createdAt) > startupHeartbeatTimeout
	}
	return now.Sub(time.Unix(0, stamp)) > heartbeatTimeout
}

func (l *laneConn) markPong() {
	l.lastPong.Store(time.Now().UnixNano())
	if l.verified.CompareAndSwap(false, true) {
		log.Printf("lane verified=%d", l.id)
	}
}

func writeFull(w io.Writer, data []byte) error {
	for len(data) > 0 {
		n, err := w.Write(data)
		if err != nil {
			return err
		}
		if n <= 0 {
			return io.ErrUnexpectedEOF
		}
		data = data[n:]
	}
	return nil
}

func (l *laneConn) writeControl(code uint32) error {
	if l == nil || l.closed.Load() {
		return net.ErrClosed
	}
	var hdr [4]byte
	binary.BigEndian.PutUint32(hdr[:], code)
	l.writeMu.Lock()
	defer l.writeMu.Unlock()
	if l.closed.Load() {
		return net.ErrClosed
	}
	_ = l.conn.SetWriteDeadline(time.Now().Add(writeTimeout))
	err := writeFull(l.conn, hdr[:])
	_ = l.conn.SetWriteDeadline(time.Time{})
	return err
}

func (l *laneConn) writePacket(packet []byte) error {
	if l == nil || l.closed.Load() {
		return net.ErrClosed
	}
	if len(packet) == 0 || len(packet) > maxPacket {
		return errors.New("invalid packet size")
	}
	frame := make([]byte, 4+len(packet))
	binary.BigEndian.PutUint32(frame[:4], uint32(len(packet)))
	copy(frame[4:], packet)

	l.writeMu.Lock()
	defer l.writeMu.Unlock()
	if l.closed.Load() {
		return net.ErrClosed
	}
	_ = l.conn.SetWriteDeadline(time.Now().Add(writeTimeout))
	err := writeFull(l.conn, frame)
	_ = l.conn.SetWriteDeadline(time.Time{})
	return err
}

type laneSet struct {
	mu    sync.RWMutex
	lanes map[int]*laneConn
}

func newLaneSet() *laneSet { return &laneSet{lanes: make(map[int]*laneConn)} }

func (s *laneSet) set(id int, c net.Conn) *laneConn {
	lane := newLaneConn(id, c)
	s.mu.Lock()
	old := s.lanes[id]
	s.lanes[id] = lane
	s.mu.Unlock()
	if old != nil && old != lane {
		old.close()
	}
	return lane
}

func (s *laneSet) remove(id int, lane *laneConn) {
	s.mu.Lock()
	if s.lanes[id] == lane {
		delete(s.lanes, id)
	}
	s.mu.Unlock()
}

func (s *laneSet) get(id int) *laneConn {
	s.mu.RLock()
	lane := s.lanes[id]
	s.mu.RUnlock()
	return lane
}

func (s *laneSet) count() int {
	s.mu.RLock()
	n := len(s.lanes)
	s.mu.RUnlock()
	return n
}

func (s *laneSet) healthyCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	n := 0
	for _, lane := range s.lanes {
		if lane.healthy() {
			n++
		}
	}
	return n
}

func openTun(name string) (*os.File, error) {
	fd, err := syscall.Open("/dev/net/tun", syscall.O_RDWR|syscall.O_CLOEXEC, 0)
	if err != nil {
		return nil, err
	}

	closeFD := true
	defer func() {
		if closeFD {
			_ = syscall.Close(fd)
		}
	}()

	var req ifreqFlags
	copy(req.Name[:], []byte(name))
	req.Flags = iffTun | iffNoPI

	_, _, errno := syscall.Syscall(
		syscall.SYS_IOCTL,
		uintptr(fd),
		uintptr(tunSetIFF),
		uintptr(unsafe.Pointer(&req)),
	)
	if errno != 0 {
		return nil, errno
	}

	if err := syscall.SetNonblock(fd, true); err != nil {
		return nil, fmt.Errorf("set tun nonblock: %w", err)
	}

	f := os.NewFile(uintptr(fd), "/dev/net/tun")
	if f == nil {
		return nil, errors.New("wrap tun fd")
	}

	closeFD = false
	return f, nil
}

func writeTunPacket(tun *os.File, packet []byte) error {
	if tun == nil {
		return errors.New("tun unavailable")
	}
	if len(packet) == 0 || len(packet) > maxPacket {
		return errors.New("invalid tun packet size")
	}

	fd := int(tun.Fd())
	deadline := time.Now().Add(tunWriteTimeout)
	for {
		n, err := syscall.Write(fd, packet)
		if err == nil {
			if n != len(packet) {
				return io.ErrShortWrite
			}
			return nil
		}
		if err == syscall.EINTR {
			continue
		}
		if err != syscall.EAGAIN && err != syscall.EWOULDBLOCK {
			return err
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("tun write timeout after %s", tunWriteTimeout)
		}
		time.Sleep(tunWriteRetryInterval)
	}
}

func configureTun(name, local string, mtu int) error {
	cmds := [][]string{
		{"ip", "addr", "replace", local, "dev", name},
		{"ip", "link", "set", "dev", name, "mtu", strconv.Itoa(mtu), "up"},
		{"ip", "link", "set", "dev", name, "txqueuelen", "2000"},
	}
	for _, args := range cmds {
		out, err := exec.Command(args[0], args[1:]...).CombinedOutput()
		if err != nil {
			return fmt.Errorf("%s: %w: %s", strings.Join(args, " "), err, strings.TrimSpace(string(out)))
		}
	}
	return nil
}

func readToken(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	token := strings.TrimSpace(string(data))
	if len(token) < 24 {
		return nil, errors.New("token too short")
	}
	sum := sha256.Sum256([]byte(token))
	return sum[:], nil
}

func handshakeClient(c net.Conn, lane int, tokenHash []byte) error {
	if lane < 0 || lane > 255 {
		return errors.New("invalid lane")
	}
	buf := make([]byte, 0, len(magic)+1+len(tokenHash))
	buf = append(buf, []byte(magic)...)
	buf = append(buf, byte(lane))
	buf = append(buf, tokenHash...)
	_ = c.SetWriteDeadline(time.Now().Add(5 * time.Second))
	if err := writeFull(c, buf); err != nil {
		return err
	}
	_ = c.SetWriteDeadline(time.Time{})
	ack := []byte{0}
	_ = c.SetReadDeadline(time.Now().Add(5 * time.Second))
	if _, err := io.ReadFull(c, ack); err != nil {
		return err
	}
	_ = c.SetReadDeadline(time.Time{})
	if ack[0] != 1 {
		return errors.New("server rejected lane")
	}
	return nil
}

func handshakeServer(c net.Conn, laneCount int, tokenHash []byte) (int, error) {
	buf := make([]byte, len(magic)+1+sha256.Size)
	_ = c.SetReadDeadline(time.Now().Add(5 * time.Second))
	if _, err := io.ReadFull(c, buf); err != nil {
		return 0, err
	}
	_ = c.SetReadDeadline(time.Time{})
	if string(buf[:len(magic)]) != magic {
		return 0, errors.New("bad magic")
	}
	lane := int(buf[len(magic)])
	if lane < 0 || lane >= laneCount {
		return 0, errors.New("bad lane")
	}
	got := buf[len(magic)+1:]
	if subtle.ConstantTimeCompare(got, tokenHash) != 1 {
		return 0, errors.New("bad token")
	}
	if err := writeFull(c, []byte{1}); err != nil {
		return 0, err
	}
	return lane, nil
}

func setTCPOptions(c net.Conn) {
	tcp, ok := c.(*net.TCPConn)
	if !ok {
		return
	}
	_ = tcp.SetNoDelay(true)
	_ = tcp.SetKeepAlive(true)
	_ = tcp.SetKeepAlivePeriod(10 * time.Second)
	_ = tcp.SetReadBuffer(4 * 1024 * 1024)
	_ = tcp.SetWriteBuffer(4 * 1024 * 1024)

	if raw, err := tcp.SyscallConn(); err == nil {
		_ = raw.Control(func(fd uintptr) {
			_ = syscall.SetsockoptInt(int(fd), syscall.IPPROTO_TCP, 18, tcpUserTimeoutMS)
		})
	}
}

func receiveFrames(lane *laneConn, tun *os.File) error {
	r := bufio.NewReaderSize(lane.conn, 512*1024)
	var hdr [4]byte
	for {
		if _, err := io.ReadFull(r, hdr[:]); err != nil {
			return err
		}
		code := binary.BigEndian.Uint32(hdr[:])
		switch code {
		case framePing:
			if err := lane.writeControl(framePong); err != nil {
				return err
			}
			continue
		case framePong:
			lane.markPong()
			continue
		}
		n := int(code)
		if n <= 0 || n > maxPacket {
			return fmt.Errorf("invalid frame length %d", n)
		}
		packet := make([]byte, n)
		if _, err := io.ReadFull(r, packet); err != nil {
			return err
		}
		if err := writeTunPacket(tun, packet); err != nil {
			return fmt.Errorf("tun write: %w", err)
		}
	}
}

func heartbeatLoop(lane *laneConn) {
	sendPing := func() bool {
		if err := lane.writeControl(framePing); err != nil {
			log.Printf("lane unhealthy=%d reason=heartbeat_write error=%v", lane.id, err)
			lane.close()
			return false
		}
		return true
	}

	if !sendPing() {
		return
	}

	ticker := time.NewTicker(heartbeatInterval)
	defer ticker.Stop()
	for range ticker.C {
		if lane.closed.Load() {
			return
		}
		if lane.expired(time.Now()) {
			reason := "heartbeat_timeout"
			if !lane.verified.Load() {
				reason = "heartbeat_startup_timeout"
			}
			log.Printf("lane unhealthy=%d reason=%s", lane.id, reason)
			lane.close()
			return
		}
		if !sendPing() {
			return
		}
	}
}

func flowHash(packet []byte) uint32 {
	var data []byte
	if len(packet) >= 20 && packet[0]>>4 == 4 {
		ihl := int(packet[0]&0x0f) * 4
		if ihl >= 20 && len(packet) >= ihl {
			data = append(data, packet[9])
			data = append(data, packet[12:20]...)
			if (packet[9] == 6 || packet[9] == 17) && len(packet) >= ihl+4 {
				data = append(data, packet[ihl:ihl+4]...)
			}
		}
	} else if len(packet) >= 40 && packet[0]>>4 == 6 {
		data = append(data, packet[6])
		data = append(data, packet[8:40]...)
		if (packet[6] == 6 || packet[6] == 17) && len(packet) >= 44 {
			data = append(data, packet[40:44]...)
		}
	}
	if len(data) == 0 {
		if len(packet) > 64 {
			data = packet[:64]
		} else {
			data = packet
		}
	}
	var h uint32 = 2166136261
	for _, b := range data {
		h ^= uint32(b)
		h *= 16777619
	}
	return h
}

func forwardPacket(lanes *laneSet, laneCount int, packet []byte) bool {
	preferred := int(flowHash(packet) % uint32(laneCount))
	now := time.Now()
	for i := 0; i < laneCount; i++ {
		id := (preferred + i) % laneCount
		lane := lanes.get(id)
		if lane == nil {
			continue
		}
		if !lane.healthy() {
			if lane.expired(now) {
				lane.close()
				lanes.remove(id, lane)
			}
			continue
		}
		if err := lane.writePacket(packet); err == nil {
			return true
		} else {
			log.Printf("lane write-fail=%d error=%v; retrying packet on healthy fallback", id, err)
			lane.close()
			lanes.remove(id, lane)
		}
	}
	return false
}

func tunToNetwork(tun *os.File, lanes *laneSet, laneCount int) {
	buf := make([]byte, maxPacket)
	for {
		for lanes.healthyCount() == 0 {
			time.Sleep(25 * time.Millisecond)
		}

		n, err := tun.Read(buf)
		if err != nil {
			log.Fatalf("tun read: %v", err)
		}
		if n <= 0 {
			continue
		}
		packet := append([]byte(nil), buf[:n]...)
		if forwardPacket(lanes, laneCount, packet) {
			continue
		}

		deadline := time.Now().Add(1500 * time.Millisecond)
		for time.Now().Before(deadline) {
			time.Sleep(10 * time.Millisecond)
			if forwardPacket(lanes, laneCount, packet) {
				break
			}
		}
	}
}

func runServer(listen string, laneCount int, tokenHash []byte, tun *os.File) error {
	ln, err := net.Listen("tcp", listen)
	if err != nil {
		return err
	}
	defer ln.Close()
	lanes := newLaneSet()
	go tunToNetwork(tun, lanes, laneCount)
	log.Printf("server listening=%s lanes=%d protocol=%s", listen, laneCount, magic)
	for {
		c, err := ln.Accept()
		if err != nil {
			return err
		}
		setTCPOptions(c)
		go func(conn net.Conn) {
			laneID, err := handshakeServer(conn, laneCount, tokenHash)
			if err != nil {
				_ = conn.Close()
				return
			}
			lane := lanes.set(laneID, conn)
			log.Printf("lane online=%d remote=%s", laneID, conn.RemoteAddr())
			go heartbeatLoop(lane)
			err = receiveFrames(lane, tun)
			lanes.remove(laneID, lane)
			lane.close()
			log.Printf("lane offline=%d error=%v", laneID, err)
		}(c)
	}
}

func clientLaneLoop(peer string, laneID int, laneCount int, tokenHash []byte, tun *os.File, lanes *laneSet) {
	backoff := time.Second
	for {
		d := net.Dialer{Timeout: 5 * time.Second, KeepAlive: 10 * time.Second}
		c, err := d.Dial("tcp", peer)
		if err == nil {
			setTCPOptions(c)
			err = handshakeClient(c, laneID, tokenHash)
		}
		if err != nil {
			if c != nil {
				_ = c.Close()
			}
			time.Sleep(backoff)
			if backoff < 10*time.Second {
				backoff *= 2
			}
			continue
		}
		backoff = time.Second
		lane := lanes.set(laneID, c)
		log.Printf("lane online=%d peer=%s", laneID, peer)
		go heartbeatLoop(lane)
		err = receiveFrames(lane, tun)
		lanes.remove(laneID, lane)
		lane.close()
		log.Printf("lane offline=%d error=%v", laneID, err)
	}
}

func runClient(peer string, laneCount int, tokenHash []byte, tun *os.File) error {
	lanes := newLaneSet()
	for lane := 0; lane < laneCount; lane++ {
		go clientLaneLoop(peer, lane, laneCount, tokenHash, tun, lanes)
	}
	go tunToNetwork(tun, lanes, laneCount)
	for lanes.healthyCount() == 0 {
		time.Sleep(50 * time.Millisecond)
	}
	log.Printf("client ready verified_lanes=%d protocol=%s", lanes.healthyCount(), magic)
	select {}
}

func main() {
	mode := flag.String("mode", "", "server or client")
	tunName := flag.String("tun", "", "TUN interface name")
	local := flag.String("local", "", "local interface CIDR")
	listen := flag.String("listen", "", "server listen address")
	peer := flag.String("peer", "", "client peer host:port")
	lanes := flag.Int("lanes", 8, "parallel TCP lanes")
	mtu := flag.Int("mtu", 1320, "TUN MTU")
	tokenFile := flag.String("token-file", "", "shared token file")
	flag.Parse()

	if *mode != "server" && *mode != "client" {
		log.Fatal("--mode must be server or client")
	}
	if *tunName == "" || *local == "" || *tokenFile == "" {
		log.Fatal("--tun, --local and --token-file are required")
	}
	if *lanes < 1 || *lanes > 32 {
		log.Fatal("--lanes must be 1..32")
	}
	if *mtu < 576 || *mtu > 9000 {
		log.Fatal("--mtu out of range")
	}
	if *mode == "server" && *listen == "" {
		log.Fatal("--listen is required in server mode")
	}
	if *mode == "client" && *peer == "" {
		log.Fatal("--peer is required in client mode")
	}

	tokenHash, err := readToken(*tokenFile)
	if err != nil {
		log.Fatalf("token: %v", err)
	}
	tun, err := openTun(*tunName)
	if err != nil {
		log.Fatalf("open tun: %v", err)
	}
	defer tun.Close()
	if err := configureTun(*tunName, *local, *mtu); err != nil {
		log.Fatalf("configure tun: %v", err)
	}

	log.Printf("tp27-tcp-direct mode=%s tun=%s local=%s mtu=%d lanes=%d protocol=%s", *mode, *tunName, *local, *mtu, *lanes, magic)
	if *mode == "server" {
		err = runServer(*listen, *lanes, tokenHash, tun)
	} else {
		err = runClient(*peer, *lanes, tokenHash, tun)
	}
	if err != nil {
		log.Fatal(err)
	}
}
