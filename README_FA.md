# TwinPanel

<div dir="rtl" align="right">

**فارسی** | [English](README.md)

# TwinPanel — پنل جامع فروش، مدیریت و زیرساخت VPN

**TwinPanel یک پلتفرم Self‑Hosted برای مدیریت کامل کسب‌وکار و زیرساخت VPN است؛ از فروشگاه و ربات فروش تا اشتراک، ۱۵ پروتکل، نودها، تانل‌ها، مسیر خروجی، Accounting، Quota، نمایندگی، پشتیبانی، بکاپ و بروزرسانی.**

هدف TwinPanel این است که اپراتور مجبور نباشد برای فروش، مدیریت کاربران، ربات تلگرام، پروتکل‌ها، سرورها و تانل‌ها چند سیستم جداگانه داشته باشد.

```text
کاربر / نماینده / ربات تلگرام / فروشگاه وب
                    ↓
                پلن و خرید
                    ↓
              ساخت اشتراک
                    ↓
           تحویل Credential
                    ↓
             ۱۵ پروتکل VPN
                    ↓
          نود ایران / Relay / Exit
                    ↓
             Tunnel / Outbound
                    ↓
                 اینترنت
```

---

## نصب سریع

روی Ubuntu 22.04 یا 24.04:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh | sudo bash
```

بعد از نصب، منوی مدیریت سرور با این دستور باز می‌شود:

```bash
twinpanel
```

یا:

```bash
tp
```

Installer نسخه Stable منتشرشده را از Manifest رسمی دریافت می‌کند و همان Source تأییدشده را نصب می‌کند؛ بدون Clone دستی، Deploy Key یا انتخاب Branch.

---

# امکانات اصلی TwinPanel

## ۱. فروشگاه وب

TwinPanel دارای فروشگاه عمومی برای فروش سرویس VPN است.

- نمایش پلن‌ها
- خرید اشتراک
- مدت و حجم سرویس
- سرویس عادی و IP ثابت
- تخفیف و کمپین فروش
- پرداخت و رسید
- ساخت خودکار اشتراک بعد از تأیید
- تحویل اطلاعات اتصال به مشتری
- آموزش اتصال
- راهنمای دانلود برنامه مناسب دستگاه
- فارسی RTL و انگلیسی LTR
- Light Mode و Dark Mode

---

## ۲. ربات فروش تلگرام

ربات تلگرام می‌تواند به‌عنوان کانال کامل فروش و تحویل سرویس استفاده شود.

- نمایش پلن‌ها
- ثبت سفارش
- پرداخت
- دریافت و بررسی رسید
- ساخت اشتراک
- تحویل اطلاعات اتصال
- تمدید سرویس
- اطلاع‌رسانی وضعیت اشتراک
- متن‌های قابل تنظیم ربات
- اعلان‌های مدیریتی
- استفاده از همان Subscription و Quota مرکزی پنل

---

## ۳. پنل نمایندگی

TwinPanel برای فروشندگان و نمایندگان هم پنل مستقل دارد.

- حساب نماینده
- مدیریت مشتری‌های نماینده
- قیمت‌گذاری اختصاصی
- موجودی و اعتبار
- اعتبار حجمی
- ساخت اشتراک
- تمدید سرویس
- مدیریت فروش
- ربات تلگرام نمایندگی
- Accounting مشترک با سیستم اصلی
- کنترل کامل نماینده از پنل ادمین

---

## ۴. پنل کاربر

هر مشتری می‌تواند سرویس‌های خودش را در پنل کاربری ببیند.

- اشتراک‌های فعال
- وضعیت سرویس
- زمان انقضا
- حجم و مصرف
- اطلاعات اتصال
- Credential هر پروتکل
- لینک اشتراک
- Multi Link در مسیرهای پشتیبانی‌شده
- آموزش اتصال
- دانلود برنامه مناسب سیستم‌عامل

---

# ۱۵ پروتکل VPN

TwinPanel در حال حاضر **۱۵ خانواده پروتکل** را از یک Control Plane مدیریت می‌کند.

## پروتکل‌های کلاسیک

| پروتکل | کاربرد |
|---|---|
| **Cisco / OpenConnect** | اتصال سازگار با AnyConnect |
| **OpenVPN** | VPN مبتنی بر TLS با پشتیبانی گسترده |
| **WireGuard** | VPN سبک و سریع لایه ۳ |
| **L2TP / IPsec** | سازگاری Native با سیستم‌عامل‌های مختلف |
| **V2Ray / Xray** | پروفایل‌های انعطاف‌پذیر VLESS/Xray و Transportهای مدرن |

## پروتکل‌های مدرن

| پروتکل | تمرکز اصلی |
|---|---|
| **Hysteria2** | QUIC/UDP، مناسب شبکه‌های Lossy و مسیرهای طولانی |
| **TUIC v5** | QUIC با Latency پایین |
| **AnyTLS** | TCP/TLS برای شبکه‌های محدود |
| **NaiveProxy** | HTTPS مرورگرمانند و Camouflage |
| **ShadowTLS v3** | TLS Camouflage |
| **Snell** | پراکسی رمزنگاری‌شده سبک |
| **Mieru** | پروتکل مدرن رمزنگاری‌شده |
| **TrustTunnel** | Tunnel مدرن مدیریت‌شده |
| **AmneziaWG** | نسخه Obfuscated مبتنی بر WireGuard |
| **Sudoku** | پروتکل مدرن مدیریت‌شده توسط TwinPanel |

TwinPanel وضعیت واقعی Adapter و Runtime هر پروتکل را نمایش می‌دهد و اگر Runtime آماده نباشد، آن را به‌صورت جعلی Online نشان نمی‌دهد.

---

## Xray / V2Ray مدرن

پروفایل‌های Xray/V2Ray شامل Transportهای مدرن زیر هستند:

- VLESS WebSocket + TLS
- VLESS XHTTP + REALITY
- VLESS gRPC + REALITY
- VLESS HTTPUpgrade + TLS
- مدیریت Domain
- آماده‌سازی TLS
- تحویل گروه‌بندی‌شده کانفیگ‌ها
- Multi Server
- لینک اشتراک
- نمایش Public Connect برای مشتری

---

# مدیریت نودها

TwinPanel زیرساخت را به نقش‌های مختلف تقسیم می‌کند.

## نقش‌های اصلی

- Controller / Local Core
- Iran Node
- Exit Node
- Relay / Transport Node در سناریوهای مربوطه

## امکانات مدیریت نود

- افزودن سرور
- حذف و ویرایش سرور
- Provision
- نصب پروتکل
- Repair
- Health Check
- Online / Offline / Maintenance
- Heartbeat
- CPU
- RAM
- Disk
- Hostname
- Active Users
- وضعیت پروتکل‌ها
- مدیریت Domain و TLS مربوط به Runtimeها
- Recovery و Diagnostics

---

# سیستم Tunnel

یکی از بخش‌های اصلی TwinPanel، لایه مستقل Tunnel بین ایران و Exit است.

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

این معماری باعث می‌شود تغییر یا Repair تانل، الزاماً Credential کاربر را تغییر ندهد.

## قابلیت‌های Tunnel

- ساخت Iran → Exit Pair
- Multi Transport
- Health Monitoring
- Latency Monitoring
- Heartbeat
- Route Priority
- Failover
- Auto Repair
- Recovery
- Transport Scoring در مسیرهای پشتیبانی‌شده
- مدیریت مسیر فعال
- جداسازی Dataplane تانل از Credential کاربران

## Transportهای پشتیبانی‌شده در معماری TwinPanel

- TP27
- VXLAN
- Spoof WG
- SSH TUN
- Backhaul
- Transportهای مدیریت‌شده دیگر در Runtime

---

# Outbound و Routing

TwinPanel دارای مرکز مستقل برای کنترل مسیر خروجی هر پروتکل است.

- Outbound Registry
- مسیر پیش‌فرض
- Policy اختصاصی هر پروتکل
- Routing Matrix
- Route Readiness
- Config Validation
- Atomic Apply
- Rollback
- Health Check
- Performance Measurement
- Latency
- Download / Upload
- Jitter
- Bufferbloat
- Stability
- Route Scoring

---

# مدیریت اشتراک

اشتراک در TwinPanel فقط یک Username/Password ساده نیست و Lifecycle مستقل دارد.

- Pending
- Active
- Suspended
- Expired
- Canceled
- تمدید
- انقضا
- حجم
- شروع از اولین اتصال در مسیرهای پشتیبانی‌شده
- Credential مجزای هر Subscription
- تحویل لینک اتصال
- Active Session
- Revoke / Restore
- اتصال به Customer / Reseller / Admin ownership

---

# Accounting و Quota Core

TwinPanel مصرف و Session را به‌صورت مرکزی مدیریت می‌کند.

- Usage Ledger
- Session Tracking
- Online Users
- Traffic Quota
- Device / Credential Mapping
- Usage Aggregation
- First Connected / First Use
- Reseller-aware Accounting
- Volume Enforcement Hooks
- Revoke / Restore
- مصرف پروتکل‌های مختلف در یک سیستم مرکزی

---

# داشبورد مدیریت

داشبورد ادمین اطلاعات عملیاتی اصلی را یکجا نمایش می‌دهد.

- تعداد کاربران
- اشتراک‌های فعال
- کاربران Online
- فروش و درآمد
- سلامت نودها
- وضعیت Tunnelها
- وضعیت هر ۱۵ پروتکل
- CPU سرور
- RAM سرور
- Disk سرور
- Uptime
- Notification
- Update Status

---

# پرداخت و فروش

TwinPanel لایه فروش را مستقیماً به Subscription متصل می‌کند.

- پلن‌ها
- سفارش
- تخفیف
- پرداخت
- رسید
- کیف پول
- شارژ
- تأیید مدیریتی
- Crypto Flow در مسیرهای پیکربندی‌شده
- ساخت سرویس بعد از تأیید پرداخت

---

# پشتیبانی و اعلان‌ها

- Support Inbox
- تیکت و پاسخ
- اعلان‌های مدیریتی
- وضعیت Read / Unread
- اعلان وضعیت Tunnel
- اعلان وضعیت زیرساخت
- رویدادهای مرتبط با Telegram

---

# Backup، Update و Recovery

TwinPanel برای Production از روش Release کنترل‌شده استفاده می‌کند.

```text
Stable Manifest
      ↓
Exact Source SHA
      ↓
Verified Package
      ↓
Backup / Safety Checks
      ↓
Atomic Switch
      ↓
Restart
      ↓
Health Check
      ↓
Rollback در صورت Failure
```

امکانات عملیاتی:

- Backup
- Restore
- Update Center
- Release Status
- Atomic Update
- Health Verification
- Rollback
- Repair
- Logs
- Diagnostics
- مدیریت از CLI با `twinpanel` و `tp`

---

# بخش‌های اصلی پنل

| بخش | کاربرد |
|---|---|
| داشبورد | وضعیت کلی سیستم |
| کاربران | مدیریت حساب‌های مشتری |
| اشتراک‌ها | Lifecycle، حجم و Credential |
| پلن‌ها | محصولات قابل فروش |
| فروشگاه | خرید عمومی |
| پرداخت | سفارش، پرداخت و رسید |
| نمایندگی | فروشندگان، مشتری و اعتبار |
| نودها | سرورهای ایران و Exit |
| پروتکل‌ها | مدیریت ۱۵ پروتکل |
| تانل‌ها | مسیرهای Iran → Exit |
| Outbound | Routing و Egress |
| پشتیبانی | تیکت و ارتباط با مشتری |
| اعلان‌ها | Notification Center |
| سیستم و نگهداری | تنظیمات، امنیت، Backup و Update Center |

---

# معماری کلی

```text
                               ┌──────────────────┐
                               │      مشتری       │
                               └────────┬─────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
      فروشگاه وب                   ربات تلگرام                  پنل نمایندگی
          │                             │                             │
          └─────────────────────────────┼─────────────────────────────┘
                                        │
                                TwinPanel Control Plane
                                        │
                ┌───────────────────────┼───────────────────────┐
                │                       │                       │
             Next.js                 FastAPI               Workers
                │                       │                       │
                └──────────────┬────────┴────────┬──────────────┘
                               │                 │
                          PostgreSQL           Redis
                               │                 │
              ┌────────────────┼─────────────────┼────────────────┐
              │                │                 │                │
           Users          Accounting           Nodes          Tunnels
              │                                  │                │
              └────────────── 15 Protocols ──────┴──── Outbound ─┘
                                                        │
                                                     Internet
```

---

# تکنولوژی‌ها

- Python 3.12
- FastAPI
- Next.js
- PostgreSQL
- Redis
- Nginx
- systemd
- Ubuntu 22.04 / 24.04
- Persian RTL
- English LTR
- Light / Dark Mode

---

# نیازمندی پیشنهادی

- Ubuntu 22.04 یا 24.04
- Root Access
- حداقل پیشنهادی 2 vCPU
- حداقل پیشنهادی 2 GB RAM
- حداقل 20 GB فضای آزاد
- دسترسی اینترنت خروجی
- پورت 80 و 443 برای Web

---

# مسیرهای مهم

| مسیر | کاربرد |
|---|---|
| `/opt/twinpanel/current` | نسخه فعال |
| `/etc/twinpanel/backend.env` | تنظیمات Backend |
| `/etc/twinpanel/install.env` | تنظیمات نصب و Release |
| `/var/lib/twinpanel-backups` | Backupها |
| `/root/twinpanel-initial-admin.txt` | اطلاعات اولیه Admin |
| `/usr/local/bin/twinpanel` | دستور مدیریت SSH |

---

# نکات امنیتی

- فایل‌های `.env` و Secretها را عمومی نکنید.
- Private Key و API Token را داخل Git Commit نکنید.
- رمز Admin اولیه را تغییر دهید.
- بعد از اولین ورود فایل Credential اولیه را حذف کنید.
- برای آپدیت از Update Center یا CLI رسمی استفاده کنید.
- فایل‌های Release فعال را مستقیم روی سرور ویرایش نکنید.
- قبل از تغییرات زیرساختی Backup بگیرید.

---

## مستندات

- [راهنمای نصب فارسی](docs/INSTALL_FA.md)
- [English installation guide](docs/INSTALL_EN.md)
- [README English](README.md)
- [Product Distribution](PRODUCT_DISTRIBUTION.md)

---

<p align="center"><strong>TwinPanel</strong><br/>فروش، مدیریت، اتصال و عملیات — در یک Control Plane</p>

</div>
