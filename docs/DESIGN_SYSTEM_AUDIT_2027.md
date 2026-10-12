# TwinPanel — Design System Audit 2027

Status: Phase 0 / Audit baseline
Branch: `design/2027-system-audit`
Base: `963266353d7698e21835cf00b74305c695ac1fa7`

## Objective

Move TwinPanel toward one maintainable Product Design System across Store, Customer, Reseller and Admin surfaces without changing healthy backend, routes, authentication or tunnel/subscription behavior.

Primary rule: **Refine > Rewrite**.

## Initial findings

### 1. CSS has multiple competing sources of truth

`app/layout.tsx` currently imports a long ordered chain of global CSS files, including foundational styles, page styles, runtime styles, light-mode fixes, final fixes, enhancement layers and parity layers.

Examples include:

- `core.css`
- `pages.css`
- `shell.css`
- `theme.css`
- `store-2027.css`
- `store-light.css`
- `store-light-final.css`
- `customer-runtime.css`
- `customer-dashboard-pro.css`
- `admin-runtime.css`
- `store-enhancements.css`
- `customer-delivery-enhancement.css`
- `parity-runtime.css`
- `subscriptions-full-runtime.css`
- `legacy-parity-batch1.css`

This makes CSS cascade order part of the application behavior and increases regression risk.

### 2. Existing tokens are incomplete and use legacy names

`app/core.css` has useful root variables, but they are not yet a full product token system. Current examples include `--bg`, `--surface`, `--surface2`, `--line`, `--text`, `--muted`, `--purple`, `--shadow`, `--r`, and `--side`.

The 2027 system should introduce semantic `--tp-*` tokens for color, typography, spacing, radius, shadow, border, motion, z-index and layout dimensions. Compatibility aliases can keep existing pages safe during migration.

### 3. Hard-coded colors remain inside shared primitives

Shared shell, navigation, card, table, badge, form and status styles still contain direct hex/rgba values. This makes Light/Dark consistency harder and is one reason later theme files need broad selector-level overrides.

### 4. Light mode is implemented partly as a repair layer

`app/theme.css` contains a large block explicitly described as complete light-mode coverage for formerly hard-coded dark components. This is useful as a safety layer today, but it confirms that primitives are not fully theme-token-driven yet.

Target state: primitives consume semantic tokens directly, reducing theme-specific component overrides.

### 5. Shell/navigation styles are duplicated across layers

`core.css` defines shell/sidebar/header/navigation behavior while `shell.css` defines newer sidebar/collapse/mobile behavior for overlapping selectors. This is a maintenance risk and should be consolidated carefully rather than patched again.

### 6. Typography is not yet product-grade Persian typography

The global font stack currently starts with `Tahoma` / `Segoe UI`. It works functionally, but there is no documented typography scale for Display, H1-H4, body, label, caption, metric and numeric data.

### 7. Layout values are partially tokenized but not standardized

Sidebar width and card radius have variables, while header height, content widths, form widths, spacing scale and responsive behavior are still distributed across files.

## Risk classification

### High risk — do not change during visual foundation work

- Backend tunnel provisioning / transport manager
- Subscription business logic
- Authentication
- Payment flows
- Route names / API contracts

### Medium risk

- Root providers
- Global shell DOM structure
- Support chat overlays
- Store/customer enhancement injectors

### Low risk / preferred first migration surface

- CSS design tokens
- Theme semantic aliases
- shared visual primitives when selectors remain backward compatible
- documentation / visual audit tooling

## Migration plan

### Phase 1 — Foundation

1. Add `app/tokens.css` as the semantic source of truth.
2. Keep compatibility aliases so current selectors continue working.
3. Define Dark and Light tokens in one place.
4. Add spacing, radius, typography, shadow, border, transition, z-index and layout tokens.
5. Import tokens before existing CSS.
6. No visual redesign in the same commit.

### Phase 2 — Shared primitives

Migrate in this order:

1. Buttons
2. Form controls
3. Cards
4. Badges/status
5. Table primitives
6. Page header
7. Empty/loading/error states

Every migration must preserve existing class compatibility where practical.

### Phase 3 — Shell

Consolidate overlapping shell/sidebar/topbar rules from `core.css` and `shell.css` after verifying all consuming components.

Goals:

- one sidebar implementation
- correct RTL collapse/drawer behavior
- consistent topbar action placement
- token-driven surfaces/borders

### Phase 4 — Product surfaces

Audit and refine in this order:

1. Customer panel
2. Admin panel
3. Reseller panel
4. Store/public pages
5. Support/chat

Each surface must share the same Color, Typography, Spacing, Radius, Button, Card, Form, Table, Icon, Motion and Feedback DNA.

### Phase 5 — Remove legacy repair layers

Only after visual/regression verification, remove obsolete `*-final`, `*-runtime`, parity or enhancement rules that are proven redundant.

Never remove a repair layer only because its name looks legacy.

## Validation gate for every implementation PR

- `npm run build`
- Desktop review: 1024 / 1280 / 1440 / 1920
- Mobile review: 390 / 768
- RTL review
- Dark mode review
- Light mode review
- Keyboard/focus review
- No unnecessary horizontal overflow
- No regression to Subscription/User/Server/Tunnel/Payment behavior
- Rollback is one Git revert / PR revert

## First implementation target

Create the semantic token layer only. Do not combine it with page redesigns. This gives TwinPanel a stable visual foundation while keeping production behavior unchanged.
