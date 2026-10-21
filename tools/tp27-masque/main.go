//go:build linux

package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/netip"
	"os"
	"strings"
	"sync"
	"time"

	connectip "github.com/quic-go/connect-ip-go"
	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/http3"
	"github.com/songgao/water"
	"github.com/vishvananda/netlink"
	"github.com/yosida95/uritemplate/v3"
)

const authorityHost = "tp27-masque.invalid"

type options struct {
	mode      string
	tunName   string
	localCIDR string
	peer      string
	listen    string
	certFile  string
	keyFile   string
	tokenFile string
	pinSHA256 string
	mtu       int
}

func main() {
	var o options
	flag.StringVar(&o.mode, "mode", "", "server or client")
	flag.StringVar(&o.tunName, "tun", "", "TUN interface name")
	flag.StringVar(&o.localCIDR, "local", "", "local TUN address in CIDR form")
	flag.StringVar(&o.peer, "peer", "", "server UDP address for client mode")
	flag.StringVar(&o.listen, "listen", "", "UDP listen address for server mode")
	flag.StringVar(&o.certFile, "cert", "", "TLS certificate path")
	flag.StringVar(&o.keyFile, "key", "", "TLS private key path")
	flag.StringVar(&o.tokenFile, "token-file", "", "shared token file")
	flag.StringVar(&o.pinSHA256, "pin-sha256", "", "server leaf certificate SHA-256")
	flag.IntVar(&o.mtu, "mtu", 1280, "inner TUN MTU")
	flag.Parse()

	if err := validate(o); err != nil {
		log.Fatalf("configuration error: %v", err)
	}

	token, err := os.ReadFile(o.tokenFile)
	if err != nil {
		log.Fatalf("reading token: %v", err)
	}
	sharedToken := strings.TrimSpace(string(token))
	if len(sharedToken) < 24 {
		log.Fatal("token is too short")
	}

	dev, err := createTun(o.tunName, o.localCIDR, o.mtu)
	if err != nil {
		log.Fatalf("creating TUN: %v", err)
	}
	defer dev.Close()

	log.Printf("TP27_MASQUE_TUN_READY mode=%s tun=%s local=%s mtu=%d", o.mode, dev.Name(), o.localCIDR, o.mtu)

	if o.mode == "server" {
		err = runServer(o, dev, sharedToken)
	} else {
		err = runClient(o, dev, sharedToken)
	}
	if err != nil {
		log.Fatal(err)
	}
}

func validate(o options) error {
	if o.mode != "server" && o.mode != "client" {
		return errors.New("--mode must be server or client")
	}
	if o.tunName == "" || len(o.tunName) > 15 {
		return errors.New("invalid --tun")
	}
	if _, err := netip.ParsePrefix(o.localCIDR); err != nil {
		return fmt.Errorf("invalid --local: %w", err)
	}
	if o.mtu < 1200 || o.mtu > 1400 {
		return errors.New("--mtu must be between 1200 and 1400")
	}
	if o.tokenFile == "" {
		return errors.New("--token-file is required")
	}
	if o.mode == "server" {
		if o.listen == "" || o.certFile == "" || o.keyFile == "" {
			return errors.New("server requires --listen, --cert and --key")
		}
	} else {
		if o.peer == "" || len(strings.TrimSpace(o.pinSHA256)) != 64 {
			return errors.New("client requires --peer and 64-char --pin-sha256")
		}
	}
	return nil
}

func createTun(name, cidr string, mtu int) (*water.Interface, error) {
	cfg := water.Config{DeviceType: water.TUN}
	cfg.Name = name
	dev, err := water.New(cfg)
	if err != nil {
		return nil, err
	}
	link, err := netlink.LinkByName(dev.Name())
	if err != nil {
		dev.Close()
		return nil, err
	}
	addr, err := netlink.ParseAddr(cidr)
	if err != nil {
		dev.Close()
		return nil, err
	}
	_ = netlink.AddrDel(link, addr)
	if err := netlink.AddrAdd(link, addr); err != nil {
		dev.Close()
		return nil, err
	}
	if err := netlink.LinkSetMTU(link, mtu); err != nil {
		dev.Close()
		return nil, err
	}
	if err := netlink.LinkSetUp(link); err != nil {
		dev.Close()
		return nil, err
	}
	return dev, nil
}

func allIPv4Route() connectip.IPRoute {
	return connectip.IPRoute{
		StartIP:    netip.MustParseAddr("0.0.0.0"),
		EndIP:      netip.MustParseAddr("255.255.255.255"),
		IPProtocol: 0,
	}
}

func authorityTemplate(port string) *uritemplate.Template {
	return uritemplate.MustNew(fmt.Sprintf("https://%s:%s/vpn", authorityHost, port))
}

func runServer(o options, dev *water.Interface, token string) error {
	_, port, err := net.SplitHostPort(o.listen)
	if err != nil {
		return fmt.Errorf("invalid listen address: %w", err)
	}
	cert, err := tls.LoadX509KeyPair(o.certFile, o.keyFile)
	if err != nil {
		return fmt.Errorf("loading TLS keypair: %w", err)
	}
	udpAddr, err := net.ResolveUDPAddr("udp", o.listen)
	if err != nil {
		return err
	}
	udpConn, err := net.ListenUDP("udp", udpAddr)
	if err != nil {
		return fmt.Errorf("listening UDP: %w", err)
	}
	defer udpConn.Close()

	tlsConf := http3.ConfigureTLSConfig(&tls.Config{
		Certificates: []tls.Certificate{cert},
		MinVersion:   tls.VersionTLS13,
	})
	listener, err := quic.ListenEarly(udpConn, tlsConf, &quic.Config{
		EnableDatagrams:      true,
		InitialPacketSize:    1200,
		HandshakeIdleTimeout: 10 * time.Second,
		MaxIdleTimeout:       45 * time.Second,
		KeepAlivePeriod:      10 * time.Second,
	})
	if err != nil {
		return fmt.Errorf("creating QUIC listener: %w", err)
	}
	defer listener.Close()

	template := authorityTemplate(port)
	proxy := connectip.Proxy{}
	var sessionMu sync.Mutex
	var active bool

	mux := http.NewServeMux()
	mux.HandleFunc("/vpn", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+token {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		req, parseErr := connectip.ParseProxyRequest(r, template)
		if parseErr != nil {
			var pe *connectip.ProxyRequestParseError
			if errors.As(parseErr, &pe) {
				w.WriteHeader(pe.HTTPStatus)
			} else {
				w.WriteHeader(http.StatusBadRequest)
			}
			return
		}

		sessionMu.Lock()
		if active {
			sessionMu.Unlock()
			w.WriteHeader(http.StatusConflict)
			return
		}
		active = true
		sessionMu.Unlock()
		defer func() {
			sessionMu.Lock()
			active = false
			sessionMu.Unlock()
		}()

		conn, proxyErr := proxy.Proxy(w, req)
		if proxyErr != nil {
			log.Printf("TP27_MASQUE_PROXY_ERROR error=%v", proxyErr)
			return
		}
		defer conn.Close()
		if advErr := conn.AdvertiseRoute([]connectip.IPRoute{allIPv4Route()}); advErr != nil {
			log.Printf("TP27_MASQUE_ROUTE_ERROR error=%v", advErr)
			return
		}
		log.Printf("TP27_MASQUE_SESSION_UP remote=%s", r.RemoteAddr)
		if proxyErr = proxyTun(conn, dev, o.mtu); proxyErr != nil {
			log.Printf("TP27_MASQUE_SESSION_DOWN error=%v", proxyErr)
		}
	})

	server := http3.Server{Handler: mux, EnableDatagrams: true}
	log.Printf("TP27_MASQUE_SERVER_READY listen=%s", o.listen)
	return server.ServeListener(listener)
}

func runClient(o options, dev *water.Interface, token string) error {
	_, port, err := net.SplitHostPort(o.peer)
	if err != nil {
		return fmt.Errorf("invalid peer address: %w", err)
	}
	pin := strings.ToLower(strings.TrimSpace(o.pinSHA256))
	if _, err := hex.DecodeString(pin); err != nil {
		return fmt.Errorf("invalid pin: %w", err)
	}

	tlsConf := &tls.Config{
		ServerName:         authorityHost,
		NextProtos:         []string{http3.NextProtoH3},
		MinVersion:         tls.VersionTLS13,
		InsecureSkipVerify: true,
		VerifyConnection: func(cs tls.ConnectionState) error {
			if len(cs.PeerCertificates) == 0 {
				return errors.New("server certificate missing")
			}
			sum := sha256.Sum256(cs.PeerCertificates[0].Raw)
			if !strings.EqualFold(hex.EncodeToString(sum[:]), pin) {
				return errors.New("server certificate pin mismatch")
			}
			return nil
		},
	}

	transport := &connectip.Transport{
		TLSClientConfig: tlsConf,
		QUICConfig: &quic.Config{
			EnableDatagrams:      true,
			InitialPacketSize:    1200,
			HandshakeIdleTimeout: 10 * time.Second,
			MaxIdleTimeout:       45 * time.Second,
			KeepAlivePeriod:      10 * time.Second,
		},
		DialAddr: func(ctx context.Context, _ string, tc *tls.Config, qc *quic.Config) (*quic.Conn, error) {
			return quic.DialAddr(ctx, o.peer, tc, qc)
		},
	}

	req, err := connectip.NewRequest(context.Background(), authorityTemplate(port))
	if err != nil {
		return err
	}
	req.Header().Set("Authorization", "Bearer "+token)
	conn, rsp, err := transport.Dial(req)
	if err != nil {
		return fmt.Errorf("CONNECT-IP dial failed: %w", err)
	}
	defer conn.Close()
	if rsp.StatusCode != http.StatusOK {
		return fmt.Errorf("CONNECT-IP HTTP status %d", rsp.StatusCode)
	}
	if err := conn.AdvertiseRoute([]connectip.IPRoute{allIPv4Route()}); err != nil {
		return fmt.Errorf("advertising route: %w", err)
	}
	log.Printf("TP27_MASQUE_CLIENT_READY peer=%s", o.peer)
	return proxyTun(conn, dev, o.mtu)
}

func proxyTun(conn *connectip.Conn, dev *water.Interface, mtu int) error {
	errCh := make(chan error, 2)
	bufSize := mtu + 256

	go func() {
		buf := make([]byte, bufSize)
		for {
			n, err := conn.ReadPacket(buf)
			if err != nil {
				errCh <- fmt.Errorf("CONNECT-IP read: %w", err)
				return
			}
			if _, err := dev.Write(buf[:n]); err != nil {
				errCh <- fmt.Errorf("TUN write: %w", err)
				return
			}
		}
	}()

	go func() {
		buf := make([]byte, bufSize)
		for {
			n, err := dev.Read(buf)
			if err != nil {
				errCh <- fmt.Errorf("TUN read: %w", err)
				return
			}
			icmp, err := conn.WritePacket(buf[:n])
			if err != nil {
				errCh <- fmt.Errorf("CONNECT-IP write: %w", err)
				return
			}
			if len(icmp) > 0 {
				if _, err := dev.Write(icmp); err != nil {
					log.Printf("TP27_MASQUE_ICMP_WRITE_ERROR error=%v", err)
				}
			}
		}
	}()

	return <-errCh
}
