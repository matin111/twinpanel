# TwinPanel

<div dir="rtl" align="right">

**فارسی** | [English](README.md)

# TwinPanel — پنل جامع Self‑Hosted مدیریت VPN

TwinPanel یک پلتفرم Self‑Hosted برای مدیریت کامل سرویس VPN است؛ از مدیریت کاربران و اشتراک‌ها تا نودها، تانل‌ها، پروتکل‌ها، فروشگاه، پرداخت، نمایندگان، کیف پول، ربات تلگرام، پشتیبانی، بکاپ، بروزرسانی و License.

هدف پروژه این است که بخش‌های اصلی سرویس روی سرور خود شما اجرا شوند و عملیات روزمره از داخل یک پنل یکپارچه انجام شود.

> نسخه انگلیسی، README پیش‌فرض مخزن است. برای برگشت به نسخه انگلیسی روی **English** در بالای صفحه کلیک کنید.

---

## نصب سریع

مشتری فقط همین یک دستور را اجرا می‌کند:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh | sudo bash
```

برای نصب نیازی به GitHub Account، SSH Key، Deploy Key، Token، Clone دستی یا انتخاب Branch/Commit نیست. Installer فایل `releases/stable.json` را می‌خواند و دقیقاً Commit عمومی تأییدشده داخل Manifest را نصب می‌کند.

راهنمای کامل نصب فارسی:

[`docs/INSTALL_FA.md`](docs/INSTALL_FA.md)

---

## مدیریت SSH

بعد از پایان نصب، برای باز کردن منوی مدیریت TwinPanel داخل SSH فقط این دستور را اجرا کنید:

```bash
twinpanel
```

نام کوتاه همان منو نیز قابل استفاده است:

```bash
tp
```

از این منو می‌توان وضعیت پنل و سرویس‌ها، ادمین، پروتکل‌ها، بروزرسانی، بکاپ، لاگ و Diagnostics، دامنه/SSL و اطلاعات نسخه را مدیریت کرد.

---

## فهرست مطالب

- [نصب سریع](#نصب-سریع)
- [مدیریت SSH](#مدیریت-ssh)
- [نمای کلی](#نمای-کلی)
- [امکانات اصلی](#امکانات-اصلی)
- [مدیریت کاربران و اشتراک‌ها](#مدیریت-کاربران-و-اشتراکها)
- [پروتکل‌های VPN](#پروتکلهای-vpn)
- [Xray / V2Ray مدرن](#xray--v2ray-مدرن)
- [نودها، تانل‌ها و Failover](#نودها-تانلها-و-failover)
- [فروشگاه و پرداخت](#فروشگاه-و-پرداخت)
- [کیف پول](#کیف-پول)
- [پنل نمایندگی](#پنل-نمایندگی)
- [ربات تلگرام](#ربات-تلگرام)
- [صفحه اتصال و تحویل اکانت](#صفحه-اتصال-و-تحویل-اکانت)
- [پشتیبانی و اعلان‌ها](#پشتیبانی-و-اعلانها)
- [دامنه، SSL و برندینگ](#دامنه-ssl-و-برندینگ)
- [بکاپ، امنیت و Diagnostics](#بکاپ-امنیت-و-diagnostics)
- [بروزرسانی و Rollback](#بروزرسانی-و-rollback)
- [Trial و License](#trial-و-license)
- [رابط کاربری](#رابط-کاربری)
- [معماری](#معماری)
- [نیازمندی‌ها](#نیازمندیها)
- [مسیرهای مهم](#مسیرهای-مهم)
- [قوانین امنیتی](#قوانین-امنیتی)

---

## نمای کلی

TwinPanel برای سناریوهایی طراحی شده که اپراتور می‌خواهد Backend، Frontend، دیتابیس، Redis، Nginx، سرویس‌های systemd و ابزارهای عملیاتی روی زیرساخت خودش اجرا شوند و مدیریت از داخل پنل انجام شود.

بخش‌های اصلی محصول شامل موارد زیر هستند:

- پنل مدیریت مرکزی
- پنل کاربر
- پنل نمایندگی
- فروشگاه و خرید اشتراک
- مدیریت پرداخت و رسید
- کیف پول
- ربات تلگرام فروش و مدیریت
- مدیریت سرورهای ایران و خارج
- مدیریت تانل و Transport
- Provision و Repair نودها
- تحویل کانفیگ و لینک اتصال
- پشتیبانی و اعلان‌ها
- Backup / Restore
- License و بروزرسانی
- فارسی RTL و انگلیسی LTR

---

## امکانات اصلی

| بخش | قابلیت‌ها |
|---|---|
| کاربران | ساخت و مدیریت کاربر، وضعیت حساب، دسترسی‌ها و جداسازی نقش‌ها |
| اشتراک‌ها | ساخت، تمدید، ویرایش، تعلیق، حذف، زمان و حجم، تحویل اتصال |
| پروتکل‌ها | Cisco/OpenConnect، OpenVPN، WireGuard، L2TP/IPsec، V2Ray/Xray |
| نودها | مدیریت نود ایران و Exit، وضعیت، Provision، Repair و Recovery |
| تانل | ساخت و مدیریت مسیر ایران → خارج، Health، Latency، Failover و Multi‑Transport |
| Xray مدرن | XHTTP/REALITY، gRPC/REALITY، WebSocket/TLS، HTTPUpgrade/TLS |
| فروش | پلن‌ها، Storefront، سفارش، تخفیف و پرداخت |
| پرداخت | کارت‌به‌کارت، USDT‑BEP20، TRX، BNB، نرخ بازار و رسید |
| SMS Reader | تطبیق پیامک بانکی با پرداخت پلن یا شارژ کیف پول |
| کیف پول | موجودی، شارژ، بررسی و تأیید پرداخت، اصلاح مدیریتی موجودی |
| نمایندگی | اعتبار حجمی، پلن اختصاصی، قیمت‌گذاری، فروش و مدیریت مشتری |
| Telegram | ربات فروش/مدیریت، سفارش، پرداخت، Wallet Top‑up و اعلان |
| پشتیبانی | تیکت، پاسخ مدیریت، Notification Center |
| دامنه و SSL | مدیریت دامنه و TLS از داخل پنل |
| برندینگ | نام، ظاهر و تنظیمات برند قابل تغییر |
| Backup | بکاپ و بازیابی با فرآیند مدیریتی |
| Release | نمایش نسخه، Update کنترل‌شده، Health Check و Rollback |
| License | زیرساخت Trial هفت‌روزه و فعال‌سازی License بدون نصب مجدد |

---

## مدیریت کاربران و اشتراک‌ها

TwinPanel مدیریت چرخه کامل کاربر و اشتراک را پوشش می‌دهد:

- ایجاد و مدیریت کاربران
- ساخت اشتراک جدید
- تمدید اشتراک
- ویرایش مشخصات اشتراک
- تعلیق یا فعال‌سازی مجدد
- حذف اشتراک
- مدیریت تاریخ انقضا
- مدیریت حجم و مصرف
- تخصیص پروتکل‌ها به اشتراک
- تخصیص نود/مسیر اتصال
- تولید Credentialهای لازم برای هر پروتکل
- نمایش اطلاعات اتصال در پنل کاربر
- لینک عمومی امن برای تحویل سرویس
- اعمال محدودیت‌ها و Enforcement اشتراک
- ثبت رویدادهای مصرف برای Quota و نمایندگی

---

## پروتکل‌های VPN

TwinPanel از چند خانواده پروتکل پشتیبانی می‌کند تا یک سرویس مجبور به وابستگی به یک روش اتصال نباشد:

### Cisco / OpenConnect

- ساخت Credential
- مدیریت پورت و Endpoint
- تحویل اطلاعات اتصال به کاربر
- استفاده در سناریوی Direct یا مسیر Tunnel

### OpenVPN

- مدیریت Credential و Client Identity
- تحویل فایل/اطلاعات اتصال
- پشتیبانی از PKI مرکزی در Runtime فعلی
- استفاده روی Windows، macOS، Android، iOS و Linux

### WireGuard

- ساخت و تحویل تنظیمات WireGuard
- QR/اطلاعات مناسب برای Client
- مدیریت Endpoint از طریق نود یا مسیر Tunnel

### L2TP/IPsec

- مدیریت اطلاعات L2TP
- مدیریت PSK در لایه زیرساخت
- تحویل اطلاعات اتصال مورد نیاز کاربر

### V2Ray / Xray

- پشتیبانی از Credentialهای VLESS/Xray
- پروفایل‌های قدیمی برای سازگاری
- پروفایل‌های مدرن مجزا برای اتصال‌های جدید

---

## Xray / V2Ray مدرن

Runtime جدید Xray چند پروفایل مستقل دارد:

- **VLESS XHTTP + REALITY**
- **VLESS gRPC + REALITY**
- **VLESS WebSocket + TLS**
- **VLESS HTTPUpgrade + TLS**

در طراحی فعلی، پروفایل قدیمی Plain برای سازگاری باقی می‌ماند اما Credentialهای جدید می‌توانند از Listenerهای مدرن جداگانه استفاده کنند.

در صورت وجود Domain و Certificate معتبر روی Exit، پروفایل‌های TLS می‌توانند از همان دامنه استفاده کنند. پروفایل‌های REALITY نیز برای سناریوهای بدون دامنه در نظر گرفته شده‌اند.

---

## نودها، تانل‌ها و Failover

### مدیریت نود

- نودهای **Iran** و **Exit**
- ثبت اطلاعات اتصال مدیریتی
- نمایش وضعیت نود
- Provision سرویس‌ها از پنل
- Node Recovery و Repair
- مدیریت Protocol Configuration هر نود
- Health و Diagnostics عملیاتی

### مدیریت تانل

- ساخت مسیر بین نود ایران و Exit
- نمایش Transport فعال
- نگهداری وضعیت Online / Offline / Degraded
- ثبت Latency و خطا
- Watchdog پس‌زمینه
- Managed Tunnel orchestration
- نصب/حذف Transportهای قابل مدیریت
- Failover بین Transportهای پشتیبانی‌شده
- تست Canary قبل از Promotion در Transportهای جدید
- حفظ مسیرهای قدیمی برای Compatibility در زمان Migration

این ساختار اجازه می‌دهد لایه VPN از لایه انتقال بین ایران و Exit جدا بماند و تغییر Transport الزاماً باعث تغییر اکانت کاربران نشود.

---

## فروشگاه و پرداخت

TwinPanel Storefront برای فروش مستقیم سرویس طراحی شده است.

### فروشگاه

- نمایش پلن‌ها
- خرید اشتراک
- تنظیمات Storefront
- مدیریت محتوای فروشگاه
- تخفیف
- Checkout
- وضعیت سفارش و پرداخت

### روش‌های پرداخت

Runtime فعلی شامل مسیرهای پرداخت برای موارد زیر است:

- کارت‌به‌کارت / رسید دستی
- USDT روی **BEP20**
- TRX Native
- BNB Native

### نرخ بازار

- دریافت نرخ بازار ارزهای دیجیتال
- ساخت Quote پرداخت
- جلوگیری از تغییر Quote ثبت‌شده در فرآیند پرداخت
- نمایش وضعیت Runtime پرداخت

### رسید و بررسی پرداخت

- ثبت رسید
- بررسی رسید توسط مدیریت
- پشتیبانی از Receiptهای محلی و جریان‌های Telegram
- اعلان نتیجه پرداخت

---

## SMS Reader

ماژول SMS Reader برای اتوماسیون پرداخت بانکی طراحی شده است:

- دریافت رویداد پیامک بانکی
- نمایش Dashboard عملیاتی SMS Reader
- تلاش برای تطبیق پرداخت
- پشتیبانی از پرداخت خرید اشتراک
- پشتیبانی از شارژ کیف پول
- جلوگیری از مصرف هم‌زمان یک پیامک برای دو عملیات متفاوت

---

## کیف پول

سیستم Wallet شامل عملیات کاربر و مدیریت است:

- نمایش موجودی
- درخواست شارژ کیف پول
- ثبت پرداخت برای Wallet Top‑up
- بررسی و تأیید یا رد توسط مدیریت
- افزایش موجودی بعد از تأیید معتبر
- اصلاح دستی موجودی توسط مدیریت
- ثبت و نمایش رویدادهای مرتبط
- اعلان تغییرات مهم کیف پول
- اتصال جریان Wallet به SMS Reader و Telegram در Runtimeهای مربوطه

---

## پنل نمایندگی

TwinPanel فقط یک پنل فروش مرکزی نیست و لایه Reseller مستقل دارد.

قابلیت‌ها شامل:

- ایجاد و مدیریت نماینده
- پروفایل نماینده
- پنل اختصاصی نماینده
- فروش اشتراک به مشتری نماینده
- مدیریت مشتریان و اشتراک‌های نماینده
- اعتبار حجمی / Traffic Credit
- خرید ترافیک
- Pool اشتراکی مصرف
- پلن‌های متعلق به نماینده
- قیمت‌گذاری و تنظیمات فروش نماینده
- تمدید و تغییر حجم اشتراک‌ها
- اعلان‌های مخصوص نماینده
- جریان سفارش و پرداخت در ربات نمایندگی

در Runtime جدید، مصرف واقعی می‌تواند مبنای کسر Traffic Pool قرار بگیرد و صرف ساخت اکانت الزاماً به معنی مصرف ترافیک نیست.

---

## ربات تلگرام

ماژول Telegram برای فروش و عملیات روزمره در کنار پنل وب وجود دارد:

- اتصال Bot به TwinPanel
- فروش اشتراک
- مدیریت سفارش
- جریان پرداخت
- ثبت/ارسال رسید
- سفارش‌های نمایندگی
- Wallet Top‑up نماینده
- ارسال اعلان
- Broadcast مدیریتی در بخش‌های مربوطه

Telegram جایگزین پنل اصلی نیست؛ هر دو از Backend مشترک استفاده می‌کنند تا داده‌ها از هم جدا نشوند.

---

## صفحه اتصال و تحویل اکانت

برای هر اشتراک می‌توان اطلاعات اتصال را در قالب صفحه عمومی کنترل‌شده تحویل داد.

قابلیت‌ها:

- Share Token / Share Code پایدار
- صفحه اتصال برای کاربر
- نمایش وضعیت فعال یا منقضی بودن اشتراک
- تولید QR در مسیرهای پشتیبانی‌شده
- ارائه Credential و Connection Info
- لینک‌های دانلود Client برای سیستم‌عامل‌های مختلف
- Windows
- macOS
- Android
- iOS
- Linux

Clientهای معرفی‌شده در Runtime شامل ابزارهایی مثل OpenVPN Connect، WireGuard، Cisco Secure Client، v2rayN و Hiddify هستند؛ بسته به سیستم‌عامل و پروتکل.

---

## پشتیبانی و اعلان‌ها

- سیستم Support برای کاربران
- مسیر مدیریتی پاسخ به درخواست‌ها
- User Notification Center
- Admin Notification Center
- Reseller Notifications
- اعلان رویدادهای عملیاتی
- Background Watch برای اعلان‌های مدیریتی

---

## دامنه، SSL و برندینگ

### Domain & SSL

- پنل می‌تواند ابتدا با IP سرور بالا بیاید
- دامنه را می‌توان بعداً تنظیم کرد
- مدیریت Domain و TLS از داخل بخش مربوطه
- استفاده از Domain در پروفایل‌های Xray TLS در صورت معتبر بودن Certificate

### Branding

- تنظیم نام و هویت محصول
- مدیریت تنظیمات برند از پنل
- جلوگیری از وابستگی رابط به نام ثابت در بخش‌های قابل تنظیم

---

## بکاپ، امنیت و Diagnostics

### Backup

- مسیر مدیریت Backup در Backend
- فرآیند Backup قبل از Upgrade
- امکان Restore بر اساس ابزارهای نسخه محصول
- نگهداری Backupها در مسیر اختصاصی نصب

### Security

- Authentication و Role checks
- Admin-only API routes برای عملیات حساس
- 2FA در Runtime محصول
- License mutation guard
- Quota / Security routes
- Isolation مسیرهای مدیریتی کاربران و نمایندگان
- تولید Secretهای محلی با Permission محدود در Installer

### Health & Diagnostics

- `/health`
- `/health/ready`
- بررسی Database
- بررسی Redis
- Health Verification بعد از Update
- Runtime status برای بخش‌های عملیاتی

---

## بروزرسانی و Rollback

TwinPanel برای Update دستی فایل‌ها طراحی نشده است. مسیر عمومی بروزرسانی شامل این مراحل است:

1. شناسایی نسخه نصب‌شده
2. دریافت Manifest نسخه Stable منتشرشده
3. Backup قبل از بروزرسانی
4. دریافت دقیق Commit عمومی معرفی‌شده در Manifest
5. بررسی SHA واقعی Git و فایل `VERSION`
6. نصب یا Build نسخه جدید
7. تعویض اتمیک `/opt/twinpanel/current`
8. Restart سرویس‌ها
9. Health Check
10. Rollback خودکار در صورت Fail شدن Health

نسخه نصب‌شده در پنل قابل نمایش است و بروزرسانی مشتری فقط از Manifest رسمی Stable انجام می‌شود.

---

## Trial و License

TwinPanel زیرساخت Trial هفت‌روزه و License پولی را نگه می‌دارد. نسخه عمومی فعلی `1.1.0-rc.1` بدون اجبار License Server قابل نصب است (`license_required: false`) تا نصب عمومی مستقل از سرویس Vendor قابل آزمایش و استفاده باشد.

معماری License برای مراحل بعدی این قابلیت‌ها را در نظر گرفته است:

- اتصال Trial به Installation Identity
- فعال‌سازی License پولی بدون حذف کاربران، اشتراک‌ها، نودها، تانل‌ها یا دیتابیس
- Signed Entitlement
- Grace محدود در قطعی موقت License Server
- بازماندن مسیرهایی مثل Login مدیریت، Activation، Backup/Export و Diagnostics طبق Policy محصول

جزئیات بیشتر:

- [`LICENSE_TRIAL_SPEC.md`](LICENSE_TRIAL_SPEC.md)
- [`PRODUCT_DISTRIBUTION.md`](PRODUCT_DISTRIBUTION.md)

---

## رابط کاربری

TwinPanel رابط‌های مختلف را در یک Design System مشترک نگه می‌دارد:

- **English LTR**
- **فارسی RTL واقعی**
- Dark Mode
- Light Mode
- پنل Admin
- پنل Customer
- پنل Reseller
- Storefront
- صفحات عمومی اتصال
- طراحی Responsive برای استفاده روی Desktop و Mobile

---

## معماری

```text
Internet
   |
 Nginx :80 / :443
   |----------------------> Next.js Web :3000
   |                           |
   |                           +--> same-origin /v1/*
   |
   +------------------------> FastAPI :8095
                                |
                      +---------+---------+
                      |                   |
                PostgreSQL :5432      Redis :6379
                      |
                      +--> Users / Subscriptions / Store / Payments
                      +--> Resellers / Wallet / Notifications / Runtime state

FastAPI
   |
   +--> Node provisioning / recovery
   +--> Tunnel management / watchdog / transports
   +--> VPN protocol credentials
   +--> Xray modern profiles
   +--> Telegram / SMS Reader / support
   +--> Backup / release / license
```

Frontend و API به‌صورت محلی اجرا می‌شوند و Nginx Endpoint عمومی را Publish می‌کند.

---

## نیازمندی‌ها

برای نصب رسمی فعلی:

- Ubuntu 22.04 یا 24.04 تمیز
- دسترسی root
- حداقل پیشنهادی 2GB RAM
- حداقل پیشنهادی 2 vCPU
- حداقل 20GB فضای خالی
- دسترسی خروجی اینترنت برای Download و Update
- پورت‌های 80 و 443 برای Web Endpoint

در هنگام نصب، Runtimeهای لازم مثل PostgreSQL، Redis، Python، Node.js، Nginx و سرویس‌های systemd آماده می‌شوند.

---

## فرآیند نصب

Installer عمومی به‌صورت خلاصه این مراحل را انجام می‌دهد:

1. بررسی Ubuntu و دسترسی root
2. دریافت Manifest رسمی Stable
3. خواندن Version و Commit دقیق نسخه
4. دریافت همان Commit با HTTPS
5. بررسی SHA واقعی Git و فایل `VERSION`
6. نصب Dependencyها و Runtimeها
7. نصب Backend و Frontend
8. ساخت Secretهای محلی
9. Initialize دیتابیس
10. ساخت Admin اولیه
11. نصب systemd serviceها
12. نصب منوی SSH با دستور `twinpanel` و `tp`
13. تنظیم Nginx
14. اجرای Health Check نهایی

Password اولیه Admin در فایل root-only زیر نگهداری می‌شود:

```text
/root/twinpanel-initial-admin.txt
```

پس از اولین ورود، مدیر Email و Password خودش را تغییر می‌دهد و می‌تواند فایل را حذف کند. Reinstall یا Update نیز Admin موجود را بدون اجازه تغییر نمی‌دهد.

---

## مسیرهای مهم

```text
/opt/twinpanel/current                 نسخه فعال
/opt/twinpanel/releases                Releaseهای نصب‌شده
/opt/twinpanel/venv                    محیط Python
/etc/twinpanel/backend.env             Environment بک‌اند
/etc/twinpanel/frontend.env            Environment فرانت‌اند
/etc/twinpanel/install.env             تنظیمات Install/Release
/var/lib/twinpanel-backups             Backupها
/var/lib/twinpanel-license             وضعیت Release/License/Update
/root/twinpanel-initial-admin.txt      اطلاعات Admin اولیه
/usr/local/bin/twinpanel               دستور مدیریت SSH
/usr/local/bin/tp                      نام کوتاه دستور مدیریت
```

---

## Source of Truth نسخه‌ها

Branch اصلی مخزن و صفحه پیش‌فرض پروژه:

```text
main
```

Release قابل نصب مشتری از فایل [`releases/stable.json`](releases/stable.json) انتخاب می‌شود و به یک Commit دقیق و اعتبارسنجی‌شده قفل است. Branchهای آزمایشی مثل `feat/*`، `fix/*`، `preview/*` یا Branchهای Local Production منبع مستقیم نصب مشتری نیستند.

نسخه محصول در فایل زیر نگهداری می‌شود:

[`VERSION`](VERSION)

---

## قوانین امنیتی

هرگز موارد زیر را داخل GitHub Commit نکنید:

- Production secrets
- License signing keys
- Telegram bot tokens
- SSH private keys
- Certificate private keys
- `.env` production files
- Database dumps
- اطلاعات محرمانه مشتریان

در معماری Production، Web/API داخلی می‌توانند روی Loopback اجرا شوند و Nginx Endpoint عمومی را Publish کند.

---

## مستندات بیشتر

- [راهنمای نصب فارسی](docs/INSTALL_FA.md)
- [معرفی محصول فارسی](docs/PRODUCT_FA.md)
- [راهنمای نصب انگلیسی](docs/INSTALL_EN.md)
- [معرفی محصول انگلیسی](docs/PRODUCT_EN.md)
- [مشخصات Trial و License](LICENSE_TRIAL_SPEC.md)
- [مدل انتشار محصول](PRODUCT_DISTRIBUTION.md)

---

**TwinPanel** — یک Control Plane یکپارچه برای مدیریت VPN، زیرساخت، فروش و عملیات سرویس.

</div>
