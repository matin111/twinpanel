# TwinPanel Overview

TwinPanel is a self-hosted control panel for VPN services, users, resellers, commerce, payments, tunnels, and infrastructure. The product is designed so the Backend, Frontend, database, Redis, Nginx, systemd services, and operational tooling run on the customer server while day-to-day configuration is managed from the panel.

## Core capabilities

- User and subscription management
- Create, edit, renew, suspend, and remove subscriptions
- Cisco/OpenConnect, OpenVPN, WireGuard, L2TP/IPsec, and V2Ray/Xray
- Iran and Exit node management
- Tunnel, failover, and multi-transport management
- Panel-driven node provisioning and repair
- Domain and SSL management
- Store, plans, and payments
- Card-to-card plus USDT-BEP20, TRX, and BNB payments
- Live crypto market rates
- SMS Reader and automatic payment verification
- Reseller management, wallet, traffic credit, plan pricing, and permissions
- Telegram sales/management bot
- Support and notifications
- Download asset management
- Configurable branding
- Encrypted backup and restore
- Security, health, and diagnostics
- Persian RTL and English LTR
- Dark/Light mode
- In-panel updates with rollback and health verification
- Seven-day trial and paid license activation without reinstalling

## Installation model

Every TwinPanel deployment has its own Installation identity. Customer servers install only validated official releases. Experimental feature/fix branches are never direct installation sources.

## Updates

The installed version is shown in the panel footer. When a newer entitled release is available, the administrator receives a notification and can start Update from the panel. The update path must perform backup, package verification, build/install, service restart, health verification, and automatic rollback on failure.

## Licensing

A new installation may run as a seven-day trial. Trial state is authoritative on the vendor license service and is bound to the Installation identity, so deleting local files or reinstalling does not create a new trial. A paid license upgrades the same installation without changing users, nodes, tunnels, subscriptions, or the database.
