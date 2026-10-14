# Bilingual UI

TwinPanel 2027 supports Persian and English.

- Persian: `lang=fa`, `dir=rtl`
- English: `lang=en`, `dir=ltr`
- Language preference is isolated per portal:
  - `twinpanel.lang.admin`
  - `twinpanel.lang.reseller`
  - `twinpanel.lang.customer`
  - `twinpanel.lang.public`
- The reseller portal defaults to Persian when it has no reseller-specific preference. Changing the admin panel to English must not change the reseller portal language.
- The legacy `twinpanel.lang` value is retained only as a migration fallback for non-reseller scopes.
- The `FA / EN` control is available in the shared panel header, login page and storefront header.
- Routes and API endpoints are language-neutral and do not change when switching languages.
