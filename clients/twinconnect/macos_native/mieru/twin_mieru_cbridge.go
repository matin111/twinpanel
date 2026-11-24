// Package main builds a C ABI for a single Mieru client INSIDE a signed
// macOS Network Extension. It does not use the Mieru CLI, subprocesses,
// environment variables, RPC ports or persistent credential files.
//
// This is an experimental library: an extension must still establish a real
// authenticated peer session, packetFlow to Libbox relay, DNS and route checks
// before allowing a VPN Connected state.
package main

/*
#include <stdint.h>
*/
import "C"

import (
    "net"
    "strconv"
    "sync"
    "time"
    "unsafe"

    "github.com/enfein/mieru/v3/pkg/appctl"
    "github.com/enfein/mieru/v3/pkg/appctl/appctlcommon"
    pb "github.com/enfein/mieru/v3/pkg/appctl/appctlpb"
    "github.com/enfein/mieru/v3/pkg/socks5"
    "google.golang.org/protobuf/encoding/protojson"
)

type runningCore struct {
    mux interface { Close() error }
    socks *socks5.Server
    listener net.Listener
}

var state = struct {
    sync.Mutex
    core *runningCore
}{}

//export TwinMieruStart
func TwinMieruStart(raw *C.char, rawLength C.int32_t) C.int32_t {
    if raw == nil || rawLength <= 0 || rawLength > 65536 {
        return -1
    }
    // This library owns exactly one in-extension Mieru core instance.
    state.Lock()
    defer state.Unlock()
    if state.core != nil {
        return -2
    }

    config := &pb.ClientConfig{}
    data := C.GoBytes(unsafe.Pointer(raw), C.int(rawLength))
    if err := (protojson.UnmarshalOptions{DiscardUnknown: false}).Unmarshal(data, config); err != nil {
        return -3
    }
    // RPC/HTTP/background processes are not allowed within a PacketTunnel.
    if config.GetRpcPort() != 0 || config.HttpProxyPort != nil ||
        config.GetSocks5ListenLAN() || config.GetHttpProxyListenLAN() ||
        config.GetSocks5Port() < 1025 || config.GetSocks5Port() > 65535 ||
        len(config.GetSocks5Authentication()) != 0 {
        return -4
    }
    if err := appctl.ValidateFullClientConfig(config); err != nil {
        return -5
    }
    profile, err := appctl.GetActiveProfileFromConfig(config, config.GetActiveProfile())
    if err != nil || profile == nil {
        return -6
    }
    // The caller must pin the authenticated server address before it installs
    // TUN routes. DNS and route-bypass checks stay with the extension.
    for _, endpoint := range profile.GetServers() {
        if endpoint.GetDomainName() != "" || net.ParseIP(endpoint.GetIpAddress()) == nil {
            return -7
        }
    }

    mux, err := appctlcommon.NewClientMuxFromProfile(
        profile, nil, nil, &net.Resolver{}, nil)
    if err != nil {
        return -8
    }
    socks, err := socks5.New(&socks5.Config{
        UseProxy: true,
        AuthOpts: socks5.Auth{ClientSideAuthentication: true},
        ProxyDialer: mux,
        Resolver: &net.Resolver{},
        HandshakeTimeout: 10 * time.Second,
    })
    if err != nil {
        _ = mux.Close()
        return -9
    }
    endpoint := net.JoinHostPort("127.0.0.1", strconv.Itoa(int(config.GetSocks5Port())))
    listener, err := net.Listen("tcp", endpoint)
    if err != nil {
        _ = mux.Close()
        return -10
    }
    instance := &runningCore{mux: mux, socks: socks, listener: listener}
    state.core = instance
    go func() {
        // A local listener becoming ready is NOT a verified peer handshake.
        _ = socks.Serve(listener)
    }()
    return 0
}

//export TwinMieruStop
func TwinMieruStop() C.int32_t {
    state.Lock()
    core := state.core
    state.core = nil
    state.Unlock()
    if core == nil {
        return 0
    }
    _ = core.socks.Close()
    _ = core.listener.Close()
    _ = core.mux.Close()
    return 0
}

//export TwinMieruLocalReady
func TwinMieruLocalReady() C.int32_t {
    state.Lock()
    defer state.Unlock()
    if state.core == nil {
        return 0
    }
    // Only means the local SOCKS service was initialized.
    return 1
}

func main() {}
