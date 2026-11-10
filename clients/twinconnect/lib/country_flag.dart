import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Vector flags rendered by Flutter itself. Windows does not consistently
/// support Unicode regional-indicator flag emojis, which can show as DE/NL/etc.
class CountryFlag extends StatelessWidget {
  const CountryFlag(this.countryCode, {super.key, this.width = 29});
  final String countryCode;
  final double width;

  @override
  Widget build(BuildContext context) {
    final code = countryCode.trim().toUpperCase();
    return Semantics(
      label: 'Country flag $code',
      image: true,
      child: SizedBox(
        width: width,
        height: width * 2 / 3,
        child: CustomPaint(
          key: Key('countryFlag_$code'),
          painter: _FlagPainter(code),
        ),
      ),
    );
  }
}

class _FlagPainter extends CustomPainter {
  const _FlagPainter(this.code);
  final String code;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final round = RRect.fromRectAndRadius(rect, Radius.circular(size.width * .13));
    canvas.save();
    canvas.clipRRect(round);

    void fill(Color color) => canvas.drawRect(rect, Paint()..color = color);
    void band(double top, double bottom, Color color) {
      canvas.drawRect(
        Rect.fromLTWH(0, size.height * top, size.width,
            size.height * (bottom - top)),
        Paint()..color = color,
      );
    }

    switch (code) {
      case 'DE':
        band(0, 1 / 3, const Color(0xFF101010));
        band(1 / 3, 2 / 3, const Color(0xFFDD1626));
        band(2 / 3, 1, const Color(0xFFFFCE00));
      case 'NL':
        band(0, 1 / 3, const Color(0xFFAE1C28));
        band(1 / 3, 2 / 3, Colors.white);
        band(2 / 3, 1, const Color(0xFF21468B));
      case 'GB':
      case 'UK':
        fill(const Color(0xFF012169));
        // Union flag: diagonal white saltires, red saltires, white
        // central cross and narrower red central cross.
        void diagonal(Offset a, Offset b, double stroke, Color color) {
          canvas.drawLine(a, b, Paint()
            ..color = color
            ..strokeWidth = stroke
            ..strokeCap = StrokeCap.square);
        }
        final w = size.width;
        final h = size.height;
        diagonal(Offset.zero, Offset(w, h), h * .29, Colors.white);
        diagonal(Offset(w, 0), Offset(0, h), h * .29, Colors.white);
        diagonal(Offset.zero, Offset(w, h), h * .13, const Color(0xFFC8102E));
        diagonal(Offset(w, 0), Offset(0, h), h * .13, const Color(0xFFC8102E));
        band(.36, .64, Colors.white);
        canvas.drawRect(Rect.fromLTWH(w * .40, 0, w * .20, h),
            Paint()..color = Colors.white);
        band(.43, .57, const Color(0xFFC8102E));
        canvas.drawRect(Rect.fromLTWH(w * .46, 0, w * .08, h),
            Paint()..color = const Color(0xFFC8102E));
      case 'US':
        fill(Colors.white);
        for (int i = 0; i < 13; i += 2) {
          band(i / 13, (i + 1) / 13, const Color(0xFFB22234));
        }
        canvas.drawRect(
          Rect.fromLTWH(0, 0, size.width * .42, size.height * 7 / 13),
          Paint()..color = const Color(0xFF3C3B6E),
        );
        final stars = Paint()..color = Colors.white;
        for (int row = 0; row < 4; row++) {
          for (int col = 0; col < 5; col++) {
            canvas.drawCircle(
              Offset(size.width * (.042 + col * .082),
                     size.height * (.045 + row * .129)),
              size.width * .012, stars,
            );
          }
        }
      case 'SG':
        band(0, .5, const Color(0xFFEF3340));
        band(.5, 1, Colors.white);
        canvas.drawCircle(Offset(size.width * .22, size.height * .245),
            size.height * .17, Paint()..color = Colors.white);
        canvas.drawCircle(Offset(size.width * .27, size.height * .19),
            size.height * .15, Paint()..color = const Color(0xFFEF3340));
        final star = Paint()..color = Colors.white;
        for (int i = 0; i < 5; i++) {
          final angle = i * 6.283185307179586 / 5 - 1.5707963267948966;
          // Small stars remain visible even at compact list sizes.
          final x = size.width * (.38 + .09 * math.cos(angle));
          final y = size.height * (.25 + .16 * math.sin(angle));
          canvas.drawCircle(Offset(x, y), size.width * .014, star);
        }
      default:
        fill(const Color(0xFF34425A));
        final text = TextPainter(
          text: TextSpan(
            text: code.length == 2 ? code : '🌐',
            style: TextStyle(
              fontSize: size.height * .55,
              fontWeight: FontWeight.bold,
              color: Colors.white,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: size.width);
        text.paint(canvas, Offset((size.width - text.width) / 2,
            (size.height - text.height) / 2));
    }

    canvas.restore();
    canvas.drawRRect(round, Paint()
      ..color = Colors.white.withValues(alpha: .27)
      ..style = PaintingStyle.stroke
      ..strokeWidth = .75);
  }

  @override
  bool shouldRepaint(_FlagPainter oldDelegate) => oldDelegate.code != code;
}
