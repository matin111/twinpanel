import '../lib/macos_mieru_tun_relay.dart';

void main() {
  print(MacMieruTunRelay.encode(
    localSocksPort: 34101,
    coreOwnedByPacketTunnel: true,
    endpointPinnedOutsideTunnel: true,
  ));
}
