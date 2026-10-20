# TwinPanel Store Theme Engine

The storefront is split into two layers:

1. **Commerce/runtime data** — plans, prices, traffic, duration, device limits, protocol availability, authentication and purchase/order flow. This remains shared and backend-driven.
2. **Theme presentation/content** — visual tokens, copy, section visibility/order and any theme-specific options. This is isolated per theme.

## Persistence

The existing `storefront_settings.content` JSON remains the storage record. Theme settings live under the reserved `_template_options` namespace, keyed by theme ID. Adding a built-in theme does not require a database migration.

Global storefront saves preserve `_template_options`. Switching the active theme never deletes another theme's configuration.

Public storefront runtime can read the theme namespace. Mutating or resetting a theme requires an admin bearer token.

## Theme package contract

A built-in theme has three registrations:

- `lib/store-template-registry.ts` — catalog metadata and activation identity.
- `lib/store-template-options.ts` — isolated defaults and schema-driven customizer fields.
- `components/store-template-runtime-registry.tsx` — runtime renderer registration.

Its React/CSS implementation can live in dedicated files such as:

- `components/store-template-<theme>.tsx`
- `components/store-template-<theme>.module.css`

The runtime registry receives a `themeOptions` namespace in addition to the shared `StoreTemplateProps`, so a future theme can introduce settings that do not exist in the legacy/global `StorefrontSettings` model. This is the extension point for genuinely different layouts and behavior such as card density, hero variants, decoration modes, navigation style or theme-only blocks.

## Admin behavior

`Storefront Manager -> Templates` is the theme control surface:

- Activate theme
- Customize theme
- Live preview
- Save isolated theme settings
- Reset/remove only that theme's customization

The customizer is schema-driven. Supported field primitives currently include:

- text
- textarea
- color
- toggle
- select
- section order

Each theme may expose a different set of groups and controls.

## Backward compatibility

Existing installations keep using their current shared storefront content until a per-theme configuration is explicitly saved. This prevents an update from unexpectedly rewriting a live store.

Shared content/settings remain as a compatibility fallback and for truly shared integrations such as social URLs and domain-level SEO.

## Adding another theme

1. Create the theme component and isolated CSS module.
2. Add catalog metadata using a stable unique theme ID.
3. Add a theme option definition with its own defaults/groups.
4. Register its renderer in the runtime registry.
5. Verify RTL/LTR, dark/light, mobile/desktop, empty/loading/error states and real plan data.
6. Open a PR and require the frontend build and backend/API CI to pass before merge/release.

Do not duplicate pricing, plan availability, payment or order logic inside a theme renderer. Themes consume the common commerce engine; they only own presentation and theme-specific content/options.
