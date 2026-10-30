<p align="center">
  <img src="docs/assets/twinpanel-banner.svg" alt="TwinPanel — Self-hosted VPN Control Plane" width="100%" />
</p>

<p align="center">
  <a href="README.md"><strong>English</strong></a> · <a href="README_FA.md">فارسی</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Production-009688?logo=fastapi&logoColor=white" />
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-black?logo=next.js&logoColor=white" />
  <img alt="Ubuntu" src="https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420?logo=ubuntu&logoColor=white" />
  <img alt="Protocols" src="https://img.shields.io/badge/VPN%20Protocols-15-7C3AED" />
  <img alt="RTL" src="https://img.shields.io/badge/UI-Persian%20RTL%20%2B%20English-7C3AED" />
</p>

# TwinPanel

**TwinPanel is a self-hosted VPN sales, subscription, protocol, node and tunnel control plane built for operators who want the complete business and network stack under their own control.**

Instead of running a separate billing panel, reseller system, Telegram sales bot, VPN node manager and tunnel monitor, TwinPanel brings the entire operational flow into one product:

```text
Customer / Reseller / Telegram Bot / Web Store
                    ↓
            Plan & Subscription
                    ↓
            Credential Delivery
                    ↓
          15 VPN Protocols
                    ↓
        Iran / Relay / Exit Nodes
                    ↓
      Tunnel & Outbound Routing
                    ↓
          Internet / Services
```

TwinPanel is designed for real production operation: sales, customer delivery, quota accounting, multi-node infrastructure, tunnel health, failover, monitoring, support, backup, updates and day-to-day administration are managed from the same control plane.

## Quick install

Run the official public installer on a clean Ubuntu 22.04 or 24.04 server:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh | sudo bash
```

The installer resolves the published Stable manifest and fetches the exact validated public Git commit declared by that release. No GitHub account, SSH key, Deploy Key, Personal Access Token, manual clone or manual branch selection is required.

After installation, open the server management menu with:

```bash
twinpanel
```

Short alias:

```bash
tp
```

# Product capabilities

## 1. Web Store and Sales

TwinPanel includes a customer-facing sales flow for turning plans into active VPN subscriptions.

- public storefront;
- configurable plans and durations;
- traffic / volume limits;
- fixed-IP and regular service models;
- discounts and promotional flows;
- checkout and payment handling;
- payment receipt workflows;
- customer account creation and subscription delivery;
- automatic access to connection information after successful activation;
- customer-facing tutorials and client-download guidance;
- Persian RTL and English LTR interfaces;
- Light and Dark themes.

## 2. Telegram Sales Bot

The Telegram sales system can operate as a complete sales and customer-delivery channel alongside the web store.

- browse plans;
- purchase subscriptions;
- payment and receipt flows;
- deliver connection information;
- customer notifications;
- subscription status and renewal flows;
- configurable bot texts;
- operational notifications;
- integration with the same central subscription and quota model used by the web panel.

## 3. Reseller Platform

TwinPanel includes reseller workflows so operators can distribute services through independent sellers without creating a separate infrastructure stack.

- reseller accounts;
- reseller customers;
- reseller-specific pricing;
- wallet and credit management;
- traffic credit / allocation;
- subscription creation and renewal;
- reseller Telegram bot support;
- centralized accounting and service ownership;
- admin control over reseller activity.

## 4. Customer Panel

Each customer can manage the services assigned to their account from a dedicated panel.

- active subscriptions;
- service status;
- expiration information;
- traffic / quota information;
- connection profiles;
- protocol-specific credentials;
- client application guidance;
- subscription and multi-link access where supported.

# 15 VPN protocols

TwinPanel manages **15 protocol families** from one control surface.

## Classic protocols

| Protocol | Purpose |
|---|---|
| **Cisco / OpenConnect** | AnyConnect-compatible remote-access VPN |
| **OpenVPN** | Widely supported TLS-based VPN |
| **WireGuard** | Lightweight modern L3 VPN |
| **L2TP / IPsec** | Native compatibility with many operating systems |
| **V2Ray / Xray** | Flexible proxy/VPN profiles with modern transports |

## Modern protocols

| Protocol | Runtime / focus |
|---|---|
| **Hysteria2** | QUIC/UDP, high-loss and long-distance networks |
| **TUIC v5** | Low-latency QUIC transport |
| **AnyTLS** | TLS-oriented TCP transport for restricted networks |
| **NaiveProxy** | Browser-like HTTPS transport and camouflage |
| **ShadowTLS v3** | TLS camouflage transport |
| **Snell** | Lightweight encrypted proxy transport |
| **Mieru** | Modern encrypted proxy transport |
| **TrustTunnel** | Managed modern tunnel protocol integration |
| **AmneziaWG** | WireGuard-derived obfuscated VPN transport |
| **Sudoku** | Modern protocol integration managed by TwinPanel |

The protocol control surface exposes runtime readiness instead of pretending that an unavailable adapter is healthy. Protocol state, configuration and node capability are tracked centrally.

## Xray / V2Ray transport profiles

TwinPanel also supports managed Xray/V2Ray profile variants such as:

- WebSocket + TLS;
- XHTTP + REALITY;
- gRPC + REALITY;
- HTTPUpgrade + TLS;
- managed domains and TLS preparation;
- grouped customer configuration delivery;
- multi-server subscription presentation.

# Nodes and infrastructure

TwinPanel separates the **control plane** from the **VPN dataplane** and supports multiple infrastructure roles.

## Node roles

- Controller / Local Core;
- Iran nodes;
- Exit nodes;
- relay / transport roles where configured.

## Node management

- add and manage servers;
- protocol installation and repair;
- heartbeat and online/offline state;
- CPU, RAM and disk telemetry;
- active-user telemetry;
- protocol readiness;
- hostname and runtime information;
- provisioning over managed server connections;
- operational repair and recovery workflows.

# Tunnel control plane

TwinPanel includes a dedicated tunnel layer for carrying traffic between infrastructure nodes independently from customer credentials.

Typical topology:

```text
Client
  ↓
Iran Node
  ↓
Managed Tunnel / Transport
  ↓
Exit Node
  ↓
Internet
```

Tunnel capabilities include:

- Iran → Exit tunnel pairs;
- multi-transport architecture;
- TP27 transport integration;
- VXLAN-based transport paths;
- Spoof WG / WireGuard-derived transport paths;
- SSH TUN transport;
- Backhaul transport integration;
- transport health monitoring;
- latency and availability status;
- tunnel heartbeat;
- route priority;
- automatic repair workflows;
- failover and recovery logic;
- transport scoring / health-aware selection where enabled;
- separation of customer VPN credentials from transport-layer tunnels.

This separation allows operators to repair or replace an Iran → Exit transport without rebuilding every customer account.

# Outbound and routing control

TwinPanel includes a dedicated outbound control surface for deciding how protocol traffic leaves the infrastructure.

- per-protocol outbound policy;
- default outbound selection;
- managed outbound registry;
- routing matrix;
- route readiness checks;
- configuration validation;
- guarded policy application;
- rollback-aware operations;
- outbound health and performance measurements;
- latency, throughput, jitter and stability measurements where available.

# Subscription lifecycle

Subscriptions are first-class objects rather than loose VPN credentials.

TwinPanel manages:

- pending / active / suspended / expired / canceled states;
- start-on-first-use workflows where configured;
- expiration and renewal;
- traffic quotas;
- protocol credentials bound to the subscription;
- connection delivery;
- active-session state;
- usage accounting;
- revoke / restore workflows;
- customer, reseller and admin ownership paths.

# Accounting and quota core

The accounting layer is designed to keep traffic and subscription state centralized even when users connect through different protocols or nodes.

- append-only usage accounting model;
- active session tracking;
- quota-aware subscriptions;
- protocol/device identity mapping;
- usage aggregation;
- reseller-aware accounting;
- traffic-limit enforcement hooks;
- online-user reporting;
- first-use activation support;
- central visibility across supported protocol runtimes.

# Admin dashboard and monitoring

The administration dashboard provides a live operational view of the platform.

- users and subscriptions;
- online sessions;
- node health;
- Controller CPU / RAM / disk / uptime;
- protocol health across all 15 protocols;
- tunnel state;
- infrastructure status;
- revenue and sales indicators;
- operational notifications;
- update status.

# Support and notifications

TwinPanel includes built-in operational communication surfaces.

- support inbox;
- customer support workflows;
- admin notifications;
- read/unread state;
- tunnel and infrastructure status notifications;
- Telegram-related operational messaging.

# Backup, update and recovery

Production upgrades are handled through a guarded release flow rather than replacing files manually.

```text
Stable manifest
      ↓
Exact source SHA
      ↓
Verified production package
      ↓
Backup / migration safety checks
      ↓
Atomic release switch
      ↓
Service restart
      ↓
Health verification
      ↓
Automatic rollback on failed health
```

Operational tools include:

- backup and restore;
- release status;
- guarded updates;
- atomic release activation;
- service health checks;
- rollback;
- repair actions;
- logs and diagnostics;
- terminal management through `twinpanel` / `tp`.

# Admin surfaces

TwinPanel ships multiple product surfaces instead of one monolithic admin page:

| Surface | Purpose |
|---|---|
| **Admin Dashboard** | Platform-wide status and operational overview |
| **Users** | Customer accounts and access state |
| **Subscriptions** | Lifecycle, quota, expiration and delivery |
| **Plans / Store** | Commercial products and public sales |
| **Resellers** | Seller accounts, pricing and credit |
| **Nodes** | Infrastructure servers and protocol runtime |
| **Protocols** | 15-protocol control surface |
| **Tunnels** | Iran/Exit transport management |
| **Outbounds** | Egress and per-protocol routing policy |
| **Payments** | Payment and receipt operations |
| **Support** | Support and communication workflows |
| **System & Maintenance** | Settings, backup, security and Update Center |

# Architecture

```text
                                   ┌─────────────────────┐
                                   │     Customers       │
                                   └──────────┬──────────┘
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              │                               │                               │
        Web Store / Panel               Telegram Bot                    Reseller Panel
              │                               │                               │
              └───────────────────────────────┼───────────────────────────────┘
                                              │
                                      TwinPanel Control Plane
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
               Next.js Web               FastAPI API              Background Workers
                    │                         │                         │
                    └───────────────┬─────────┴─────────┬───────────────┘
                                    │                   │
                              PostgreSQL              Redis
                                    │                   │
                 ┌──────────────────┼───────────────────┼──────────────────┐
                 │                  │                   │                  │
             Accounts          Accounting          Nodes             Tunnels
                 │                                      │                  │
                 │                                 Iran / Exit ───── Transport
                 │                                      │                  │
                 └────────────── 15 VPN Protocols ──────┴────── Outbound ──┘
                                                                │
                                                             Internet
```

# Server management

The `twinpanel` / `tp` terminal menu provides fast access to:

- panel and service health;
- safe API/Web/Nginx restart;
- VPN protocol management;
- update and release status;
- administrator tools;
- backups;
- logs and diagnostics;
- version and GitHub information.

# Installation requirements

- Ubuntu **22.04** or **24.04**;
- root access;
- **2 GB RAM** recommended minimum;
- **2 vCPU** recommended minimum;
- at least **20 GB** free disk space;
- outbound Internet access;
- ports **80** and **443** for the public web endpoint.

The installer prepares PostgreSQL, Redis, Python, Node.js, Nginx and systemd services as part of the deployment flow.

# Technology stack

- **Backend:** Python 3.12 + FastAPI
- **Frontend:** Next.js
- **Database:** PostgreSQL
- **Cache / runtime state:** Redis
- **Reverse proxy:** Nginx
- **Service management:** systemd
- **Deployment:** immutable release directories + atomic activation
- **UI:** Persian RTL + English LTR, Light / Dark modes

# Documentation

- [English installation guide](docs/INSTALL_EN.md)
- [راهنمای نصب فارسی](docs/INSTALL_FA.md)
- [Persian repository overview](README_FA.md)
- [Trial / licensing specification](LICENSE_TRIAL_SPEC.md)
- [Product distribution notes](PRODUCT_DISTRIBUTION.md)

# Important paths

| Path | Purpose |
|---|---|
| `/opt/twinpanel/current` | Active application release |
| `/etc/twinpanel/backend.env` | Backend runtime configuration |
| `/etc/twinpanel/install.env` | Installation/release settings |
| `/var/lib/twinpanel-backups` | Backup storage |
| `/root/twinpanel-initial-admin.txt` | First-login credentials when initially created |
| `/usr/local/bin/twinpanel` | SSH management command |

# Security notes

- Keep `/etc/twinpanel/*.env` and installation secrets private.
- Change the initial administrator credentials after first login.
- Remove `/root/twinpanel-initial-admin.txt` after the first-login credentials are no longer needed.
- Use the guarded update path instead of editing production release files directly.
- Back up the system before infrastructure-level changes.
- Never commit production credentials, API tokens, private keys or server secrets to the repository.

---

<p align="center">
  <img src="docs/assets/twinpanel-logo.svg" alt="TwinPanel logo" width="86" />
</p>

<p align="center"><strong>TwinPanel</strong><br/>Sales. Control. Connect. Operate.</p>
