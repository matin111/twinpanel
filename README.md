# TwinPanel

Self-hosted VPN control plane for users, subscriptions, nodes, tunnels, resellers, payments, Telegram, backups, and storefront operations.

TwinPanel is bilingual: Persian RTL and English LTR.

## فارسی

TwinPanel یک پنل Self-Hosted برای مدیریت کاربران، اشتراک‌ها، نودها، تانل‌ها، پروتکل‌ها، نمایندگان، فروش، پرداخت، ربات تلگرام، پشتیبانی، بکاپ و فروشگاه است.

### نصب سریع

نصب مشتری باید فقط از Bootstrap عمومی رسمی انجام شود:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/install.sh | sudo bash
```

راهنمای کامل فارسی: [`docs/INSTALL_FA.md`](docs/INSTALL_FA.md)

معرفی امکانات فارسی: [`docs/PRODUCT_FA.md`](docs/PRODUCT_FA.md)

## English

TwinPanel is a self-hosted control panel for VPN users, subscriptions, nodes, tunnels, protocols, resellers, commerce, payments, Telegram, support, backups, and storefront operations.

### Quick install

Customer installations must use the official public bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/install.sh | sudo bash
```

Full English installation guide: [`docs/INSTALL_EN.md`](docs/INSTALL_EN.md)

English product overview: [`docs/PRODUCT_EN.md`](docs/PRODUCT_EN.md)

## Release source of truth

Customer-installable code is promoted through the canonical release branch and versioned releases. Experimental `feat/*`, `fix/*`, `deploy/*`, `preview/*`, and local production branches are not installation sources.

Current canonical integration branch:

```text
release/stable-v1
```

The panel version is stored in [`VERSION`](VERSION).

## Runtime architecture

```text
Internet
   |
 Nginx :80/:443
   |--------------------> Next.js Web :3000
   |                         |
   |                         +--> same-origin /v1/*
   |
   +----------------------> FastAPI :8095
                              |
                    +---------+---------+
                    |                   |
              PostgreSQL :5432      Redis :6379
```

## Trial and licensing

New installations may request a seven-day trial. Trial state is authoritative on the vendor license service and is bound to the installation identity. Paid activation upgrades the same installation without reinstalling or deleting users, nodes, tunnels, subscriptions, or database data.

See [`LICENSE_TRIAL_SPEC.md`](LICENSE_TRIAL_SPEC.md) and [`PRODUCT_DISTRIBUTION.md`](PRODUCT_DISTRIBUTION.md).

## Security rules

- Never commit production secrets, license signing keys, Telegram tokens, SSH private keys, certificate private keys, `.env` files, or database dumps.
- Web/API services listen on loopback; Nginx publishes public endpoints.
- Every production fix must be committed to the canonical product source before customer deployment.
