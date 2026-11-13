import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('shared glass remains translucent and tenant palette responsive', () {
    final source = File('lib/interactive_glass_card.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(source, contains('ImageFilter.blur(sigmaX: 15, sigmaY: 15)'));
    expect(source, contains('secondaryColor'));
    expect(source, contains('surface.withValues(alpha: bright ? .67 : .93)'));
    expect(dashboard, contains('secondaryColor: BrandTheme.secondaryAccent(widget.brand)'));
    expect(dashboard, contains('filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16)'));
    expect(dashboard, contains('Key(\'liveConnectionControlsButton\')'));
    expect(dashboard, contains('onPressed: _vpnBusy ? null : _toggleVpn'));
    expect(dashboard, contains('backgroundColor: Colors.transparent'));
  });
}
