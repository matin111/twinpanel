import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

/// Premium six-language selector shared by Windows dashboard themes.
/// Selected app locale, not Windows system locale, determines reading direction.
Future<String?> showTwinLanguagePicker({
  required BuildContext context,
  required String selectedCode,
  required bool dark,
  required bool rtl,
  required Color primary,
  required Color accent,
  required String title,
  required String subtitle,
  required String note,
}) {
  const languages = <({String code, String native, String english, String mark})>[
    (code: 'fa', native: 'فارسی', english: 'Persian', mark: 'فا'),
    (code: 'en', native: 'English', english: 'English', mark: 'EN'),
    (code: 'tr', native: 'Türkçe', english: 'Turkish', mark: 'TR'),
    (code: 'ar', native: 'العربية', english: 'Arabic', mark: 'ع'),
    (code: 'de', native: 'Deutsch', english: 'German', mark: 'DE'),
    (code: 'fr', native: 'Français', english: 'French', mark: 'FR'),
  ];
  final textColor = dark ? const Color(0xFFEAF4F6)
      : const Color(0xFF213B46);
  final muted = dark ? const Color(0xFFAAC0CA)
      : const Color(0xFF617986);
  return showDialog<String>(
    context: context,
    barrierColor: Colors.black.withValues(alpha: .66),
    builder: (dialogContext) => Directionality(
      textDirection: rtl ? TextDirection.rtl : TextDirection.ltr,
      child: Dialog(
        key: const Key('devLanguageDialog'),
        backgroundColor: Colors.transparent,
        elevation: 0,
        insetPadding: const EdgeInsets.symmetric(
          horizontal: 20, vertical: 22),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: 540,
            maxHeight: MediaQuery.sizeOf(dialogContext).height - 44,
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(28),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(28),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft, end: Alignment.bottomRight,
                    colors: dark
                      ? const [Color(0xFF1E3946),
                          Color(0xFF13232F), Color(0xFF19343C)]
                      : const [Color(0xFFFFFFFF),
                          Color(0xFFF4FAFB), Color(0xFFEAF3F5)],
                  ),
                  border: Border.all(
                    color: dark ? const Color(0xFF5E8A98)
                        .withValues(alpha: .48)
                      : const Color(0xFFBCD5DD),
                    width: 1.1),
                  boxShadow: [BoxShadow(
                    color: Colors.black.withValues(alpha: dark ? .36 : .15),
                    blurRadius: 45, offset: const Offset(0, 18))],
                ),
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(children: [
                        Container(
                          width: 50, height: 50,
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(15),
                            gradient: LinearGradient(colors: [
                              primary.withValues(alpha: .32),
                              accent.withValues(alpha: .24),
                            ]),
                            border: Border.all(
                                color: accent.withValues(alpha: .52)),
                          ),
                          child: Icon(Icons.translate_rounded,
                            color: dark ? const Color(0xFF9AE0D8)
                              : const Color(0xFF3B8190), size: 25),
                        ),
                        const SizedBox(width: 13),
                        Expanded(child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(title, style: TextStyle(
                              fontSize: 20, fontWeight: FontWeight.w800,
                              color: textColor)),
                            const SizedBox(height: 4),
                            Text(subtitle, style: TextStyle(
                              fontSize: 12, color: muted)),
                          ],
                        )),
                        IconButton(
                          tooltip: 'Close',
                          onPressed: () => Navigator.of(dialogContext).pop(),
                          icon: Icon(Icons.close_rounded, color: muted),
                        ),
                      ]),
                      const SizedBox(height: 21),
                      LayoutBuilder(
                        builder: (context, constraints) {
                          final columns = constraints.maxWidth < 390 ? 1 : 2;
                          return GridView.builder(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            itemCount: languages.length,
                            gridDelegate:
                              SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: columns,
                                mainAxisExtent: 80,
                                mainAxisSpacing: 10,
                                crossAxisSpacing: 10),
                            itemBuilder: (context, index) {
                              final item = languages[index];
                              final active = selectedCode == item.code;
                              final surface = dark
                                ? const Color(0xFF223C47)
                                : const Color(0xFFF4FAFB);
                              return Material(
                                color: Colors.transparent,
                                child: InkWell(
                                  key: Key('languageChoice_' + item.code),
                                  borderRadius: BorderRadius.circular(17),
                                  onTap: () => Navigator.of(dialogContext)
                                      .pop(item.code),
                                  child: AnimatedContainer(
                                    duration: const Duration(
                                      milliseconds: 190),
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 12, vertical: 9),
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(17),
                                      gradient: LinearGradient(colors: active
                                        ? [
                                          primary.withValues(
                                            alpha: dark ? .31 : .18),
                                          accent.withValues(
                                            alpha: dark ? .26 : .14),
                                        ]
                                        : [
                                          surface.withValues(alpha: .97),
                                          (dark
                                            ? const Color(0xFF1B303A)
                                            : const Color(0xFFEBF4F6))
                                              .withValues(alpha: .95),
                                        ]),
                                      border: Border.all(
                                        color: active
                                          ? accent.withValues(alpha: .83)
                                          : (dark
                                            ? const Color(0xFF557482)
                                            : const Color(0xFFD2E1E6))
                                              .withValues(alpha: .68),
                                        width: active ? 1.5 : 1),
                                    ),
                                    child: Row(children: [
                                      Container(
                                        height: 44, width: 44,
                                        alignment: Alignment.center,
                                        decoration: BoxDecoration(
                                          borderRadius:
                                              BorderRadius.circular(13),
                                          color: active
                                            ? accent.withValues(
                                                alpha: dark ? .28 : .21)
                                            : (dark
                                              ? const Color(0xFF2E4A55)
                                              : const Color(0xFFE0EDF0)),
                                        ),
                                        child: Text(item.mark,
                                          style: TextStyle(
                                            fontWeight: FontWeight.w800,
                                            fontSize: 16,
                                            color: active
                                              ? (dark
                                                ? const Color(0xFFB6FFF0)
                                                : const Color(0xFF246879))
                                              : textColor)),
                                      ),
                                      const SizedBox(width: 10),
                                      Expanded(child: Column(
                                        mainAxisAlignment:
                                            MainAxisAlignment.center,
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(item.native,
                                            textDirection: item.code == 'fa' ||
                                                item.code == 'ar'
                                              ? TextDirection.rtl
                                              : TextDirection.ltr,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: TextStyle(
                                              color: textColor,
                                              fontWeight: FontWeight.w700,
                                              fontSize: 14)),
                                          const SizedBox(height: 3),
                                          Text(item.english,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: TextStyle(
                                              color: muted, fontSize: 11)),
                                        ],
                                      )),
                                      if (active)
                                        Icon(Icons.check_circle_rounded,
                                          size: 20,
                                          color: dark
                                            ? const Color(0xFF73DAC0)
                                            : const Color(0xFF278A7A)),
                                    ]),
                                  ),
                                ),
                              );
                            },
                          );
                        },
                      ),
                      const SizedBox(height: 19),
                      Row(children: [
                        Icon(Icons.check_circle_outline_rounded,
                          color: accent, size: 16),
                        const SizedBox(width: 7),
                        Expanded(child: Text(note,
                          style: TextStyle(color: muted, fontSize: 11))),
                      ]),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
