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
	"syscall"
	"time"
	"unsafe"
)

const (
	tunSetIFF = 0x400454ca
	iffTun    = 0x0001
	iffNoPI   = 0x1000
	magic     = "TP27TCP1"
	maxPacket = 65535
)

type ifreqFlags struct {
	Name  [16]byte
	Flags uint16
	pad   [22]byte
}

type laneSet struct {
	mu    sync.RWMutex
	lanes map[int]net.Conn
}

func newLaneSet() *laneSet { return &laneSet{lanes: make(map[int]net.Conn)} }

func (s *laneSet) set(id int, c net.Conn) {
	s.mu.Lock()
	old := s.lanes[id]
	s.lanes[id] = c
	s.mu.Unlock()
	if old != nil && old != c {
		_ = old.Close()
	}
}

func (s *laneSet) remove(id int, c net.Conn) {
	s.mu.Lock()
	if s.lanes[id] == c {
		delete(s.lanes, id)
	}
	s.mu.Unlock()
}

func (s *laneSet) get(id int) net.Conn {
	s.mu.RLock()
	c := s.lanes[id]
	s.mu.RUnlock()
	return c
}

func (s *laneSet) count() int {
	s.mu.RLock()
	n := len(s.lanes)
	s.mu.RUnlock()
	return n
}

func openTun(name string) (*os.File, error) {
	f, err := os.OpenFile("/dev/net/tun", os.O_RDWR, 0)
	if err != nil {
		return nil, err
	}
	var req ifreqFlags
	copy(req.Name[:], []byte(name))
	req.Flags = iffTun | iffNoPI
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), uintptr(tunSetIFF), uintptr(unsafe.Pointer(&req)))
	if errno != 0 {
		_ = f.Close()
		return nil, errno
	}
	return f, nil
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
	if _, err := c.Write(buf); err != nil {
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
	if _, err := c.Write([]byte{1}); err != nil {
		return 0, err
	}
	return lane, nil
}

func setTCPOptions(c net.Conn) {
	if tcp, ok := c.(*net.TCPConn); ok {
		_ = tcp.SetNoDelay(true)
		_ = tcp.SetKeepAlive(true)
		_ = tcp.SetKeepAlivePeriod(15 * time.Second)
		_ = tcp.SetReadBuffer(4 * 1024 * 1024)
		_ = tcp.SetWriteBuffer(4 * 1024 * 1024)
	}
}

func writeFrame(w io.Writer, packet []byte) error {
	if len(packet) == 0 || len(packet) > maxPacket {
		return errors.New("invalid packet size")
	}
	var hdr [4]byte
	binary.BigEndian.PutUint32(hdr[:], uint32(len(packet)))
	if _, err := w.Write(hdr[:]); err != nil {
		return err
	}
	_, err := w.Write(packet)
	return err
}

func receiveFrames(c net.Conn, tun *os.File, tunWriteMu *sync.Mutex) error {
	r := bufio.NewReaderSize(c, 512*1024)
	var hdr [4]byte
	for {
		if _, err := io.ReadFull(r, hdr[:]); err != nil {
			return err
		}
		n := int(binary.BigEndian.Uint32(hdr[:]))
		if n <= 0 || n > maxPacket {
			return fmt.Errorf("invalid frame length %d", n)
		}
		packet := make([]byte, n)
		if _, err := io.ReadFull(r, packet); err != nil {
			return err
		}
		tunWriteMu.Lock()
		_, err := tun.Write(packet)
		tunWriteMu.Unlock()
		if err != nil {
			return err
		}
	}
}

func flowHash(packet []byte) uint32 {
	// FNV-1a over stable IPv4/IPv6 flow fields. This keeps packets from the same
	// flow on one TCP lane and avoids cross-lane reordering for TCP/QUIC flows.
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

func tunToNetwork(tun *os.File, lanes *laneSet, laneCount int) {
	buf := make([]byte, maxPacket)
	for {
		n, err := tun.Read(buf)
		if err != nil {
			log.Fatalf("tun read: %v", err)
		}
		if n <= 0 {
			continue
		}
		packet := append([]byte(nil), buf[:n]...)
		preferred := int(flowHash(packet) % uint32(laneCount))
		var c net.Conn
		for i := 0; i < laneCount; i++ {
			c = lanes.get((preferred + i) % laneCount)
			if c != nil {
				break
			}
		}
		if c == nil {
			time.Sleep(10 * time.Millisecond)
			continue
		}
		_ = c.SetWriteDeadline(time.Now().Add(5 * time.Second))
		if err := writeFrame(c, packet); err != nil {
			_ = c.Close()
		}
		_ = c.SetWriteDeadline(time.Time{})
	}
}

func runServer(listen string, laneCount int, tokenHash []byte, tun *os.File) error {
	ln, err := net.Listen("tcp", listen)
	if err != nil {
		return err
	}
	defer ln.Close()
	lanes := newLaneSet()
	var tunWriteMu sync.Mutex
	go tunToNetwork(tun, lanes, laneCount)
	log.Printf("server listening=%s lanes=%d", listen, laneCount)
	for {
		c, err := ln.Accept()
		if err != nil {
			return err
		}
		setTCPOptions(c)
		go func(conn net.Conn) {
			lane, err := handshakeServer(conn, laneCount, tokenHash)
			if err != nil {
				_ = conn.Close()
				return
			}
			lanes.set(lane, conn)
			log.Printf("lane online=%d remote=%s", lane, conn.RemoteAddr())
			err = receiveFrames(conn, tun, &tunWriteMu)
			lanes.remove(lane, conn)
			_ = conn.Close()
			log.Printf("lane offline=%d error=%v", lane, err)
		}(c)
	}
}

func clientLaneLoop(peer string, lane int, laneCount int, tokenHash []byte, tun *os.File, lanes *laneSet, tunWriteMu *sync.Mutex) {
	backoff := time.Second
	for {
		d := net.Dialer{Timeout: 5 * time.Second, KeepAlive: 15 * time.Second}
		c, err := d.Dial("tcp", peer)
		if err == nil {
			setTCPOptions(c)
			err = handshakeClient(c, lane, tokenHash)
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
		lanes.set(lane, c)
		log.Printf("lane online=%d peer=%s", lane, peer)
		err = receiveFrames(c, tun, tunWriteMu)
		lanes.remove(lane, c)
		_ = c.Close()
		log.Printf("lane offline=%d error=%v", lane, err)
	}
}

func runClient(peer string, laneCount int, tokenHash []byte, tun *os.File) error {
	lanes := newLaneSet()
	var tunWriteMu sync.Mutex
	for lane := 0; lane < laneCount; lane++ {
		go clientLaneLoop(peer, lane, laneCount, tokenHash, tun, lanes, &tunWriteMu)
	}
	go tunToNetwork(tun, lanes, laneCount)
	for lanes.count() == 0 {
		time.Sleep(100 * time.Millisecond)
	}
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

	log.Printf("tp27-tcp-direct mode=%s tun=%s local=%s mtu=%d lanes=%d", *mode, *tunName, *local, *mtu, *lanes)
	if *mode == "server" {
		err = runServer(*listen, *lanes, tokenHash, tun)
	} else {
		err = runClient(*peer, *lanes, tokenHash, tun)
	}
	if err != nil {
		log.Fatal(err)
	}
}
