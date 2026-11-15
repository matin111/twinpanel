import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/windows_singbox_tunnel.dart';

void main() {
  test('modern native tunnel never claims connection without a verified run',
      () async {
    final tunnel = WindowsSingBoxTunnel();
    expect(tunnel.isRunning, isFalse);
    expect(tunnel.publicIp, isNull);
    expect(tunnel.serverId, isNull);
    expect(tunnel.protocol, isNull);

    // Flutter Linux unit tests must not touch Windows network routes.
    if (!Platform.isWindows) {
      await expectLater(
        tunnel.start(protocol: 'hysteria2', serverId: '1',
          profile: const <String, dynamic>{}),
        throwsFormatException);
    }
    expect(tunnel.isRunning, isFalse);
    await tunnel.stop();
    expect(tunnel.isRunning, isFalse);
    tunnel.dispose();
  });
}
