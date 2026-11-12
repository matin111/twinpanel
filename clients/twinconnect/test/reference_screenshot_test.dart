import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('export actual Flutter reference layout at 1536x1024',
      (tester) async {
    SharedPreferences.setMockInitialValues({
      'twinconnect_ui_language_v1': 'en',
    });
    await tester.binding.setSurfaceSize(const Size(1536, 1024));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    const captureKey = Key('referenceCapture');
    await tester.pumpWidget(const RepaintBoundary(
      key: captureKey,
      child: TwinConnectApp(),
    ));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).first, const Offset(0, -260));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('windowsDemoButton')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('referenceDesktopShell')), findsOneWidget);
    expect(tester.takeException(), isNull);

    final render = tester.renderObject<RenderRepaintBoundary>(
      find.byKey(captureKey),
    );
    await tester.runAsync(() async {
      final image = await render.toImage(pixelRatio: 1);
      try {
        final data = await image.toByteData(format: ui.ImageByteFormat.png);
        expect(data, isNotNull);
        final file = File('build/reference/desktop-1536x1024.png');
        await file.parent.create(recursive: true);
        await file.writeAsBytes(data!.buffer.asUint8List());
        expect(await file.length(), greaterThan(10000));
      } finally {
        image.dispose();
      }
    });
  });
}
