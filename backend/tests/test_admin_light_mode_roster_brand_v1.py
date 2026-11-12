"""Contrast and scope regression tests for three admin light-mode screens."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SUB=(ROOT/"components/legacy-subscriptions-exact.tsx").read_text(encoding="utf-8")
USERS=(ROOT/"components/admin-users-runtime.tsx").read_text(encoding="utf-8")
BRAND=(ROOT/"components/central-app-brand-studio.css").read_text(encoding="utf-8")
GUARD=(ROOT/"scripts/verify_release_ui_parity.py").read_text(encoding="utf-8")


def luminance(hex_color: str) -> float:
    values=[int(hex_color[i:i+2],16)/255 for i in (1,3,5)]
    channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(v*w for v,w in zip(channels,(.2126,.7152,.0722)))


def contrast(foreground: str, background: str) -> float:
    a,b=sorted((luminance(foreground),luminance(background)))
    return (b+.05)/(a+.05)


class AdminLightModeScreensTests(unittest.TestCase):
    def test_subscriptions_has_explicit_light_card_and_inherited_text(self):
        for marker in (
            'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-card',
            'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-identities b',
            'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-usage',
            'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-meta',
            'html[data-theme="light"] .legacy-subscriptions-page .subscription-presence-offline',
            'mobile-action-renew', 'mobile-action-connect', 'mobile-action-reset',
        ):
            self.assertIn(marker,SUB)

    def test_users_has_readable_actions_and_contact_panels(self):
        for marker in (
            'html[data-theme="light"] .admin-users-runtime .admin-user-card',
            'html[data-theme="light"] .admin-users-runtime .admin-user-names b',
            'html[data-theme="light"] .admin-users-runtime .admin-user-contact',
            'html[data-theme="light"] .admin-users-runtime .admin-user-account-count',
            'html[data-theme="light"] .admin-users-runtime .admin-user-action.danger',
            'adminApi.usersFastPage', 'adminApi.updateUser', 'adminApi.deleteUser',
        ):
            self.assertIn(marker,USERS)

    def test_brand_studio_light_mode_is_complete_but_preview_theme_is_independent(self):
        for marker in (
            'html[data-theme="light"] .tbs-page',
            '--tbs-input:#f8faff',
            'html[data-theme="light"] .tbs-page .tbs-tabs button.selected',
            'html[data-theme="light"] .tbs-page .tbs-upload',
            'html[data-theme="light"] .tbs-page .tbs-color-field',
            'html[data-theme="light"] .tbs-page .tbs-readonly',
            'html[data-theme="light"] .tbs-page .tbs-save:disabled',
        ):
            self.assertIn(marker,BRAND)
        # The simulated app should not be forcibly recolored to the panel theme.
        override=BRAND[BRAND.rfind('/* Readable Brand Studio in panel light mode'):]
        self.assertNotRegex(override,r'html\[data-theme="light"\]\s+\.tbs-page\s+\.tbs-device(?:\s|{)')
        self.assertIn('appearance?.background_color',(ROOT/"components/central-app-brand-manager.tsx").read_text())

    def test_contrast_is_sufficient_in_light_cards(self):
        for fg,bg in (
            ('#1c2941','#ffffff'),
            ('#51637e','#f8faff'),
            ('#1b2c48','#f7f9fe'),
            ('#20314c','#f8faff'),
            ('#536581','#ffffff'),
        ):
            with self.subTest(fg=fg,bg=bg):
                self.assertGreaterEqual(contrast(fg,bg),4.5)

    def test_dark_mode_rules_are_retained(self):
        self.assertIn('rgba(12,23,44,.96)',SUB)
        self.assertIn('rgba(12,23,44,.94)',USERS)
        self.assertIn('--tbs-pane:linear-gradient(145deg,#1b2437,#111827)',BRAND)

    def test_release_is_protected_against_style_reversions(self):
        for marker in (
            'components/legacy-subscriptions-exact.tsx',
            'components/admin-users-runtime.tsx',
            'components/central-app-brand-studio.css',
            'Subscription roster light-mode contrast',
            'User roster light-mode contrast',
            'App Brand Studio light-mode',
        ):
            self.assertIn(marker,GUARD)

if __name__=="__main__":
    unittest.main()
