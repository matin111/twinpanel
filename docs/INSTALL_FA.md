# راهنمای نصب TwinPanel

این راهنما برای نصب رسمی Self-Hosted پنل است. نصب مشتری مستقیماً از مخزن عمومی `matin111/twinpanel` و Manifest نسخه Stable تأییدشده انجام می‌شود و Branchهای آزمایشی `feat/*`، `fix/*` و مشابه آن منبع نصب مشتری نیستند.

## پیش‌نیازها

- Ubuntu 22.04 یا 24.04 روی سرور تمیز
- دسترسی root
- حداقل 2GB RAM و 2 vCPU پیشنهاد می‌شود
- حداقل 20GB فضای آزاد
- دسترسی خروجی اینترنت برای دریافت سورس و بروزرسانی
- پورت‌های 80 و 443 برای وب عمومی

## نصب سریع

مشتری فقط همین یک دستور را اجرا می‌کند:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh | sudo bash
```

برای نصب نیازی به GitHub Account، SSH Key، Deploy Key، Personal Access Token، Clone دستی، انتخاب Branch یا واردکردن Commit نیست.

Installer ابتدا Manifest رسمی Stable را از مسیر زیر می‌خواند:

```text
https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json
```

Manifest به یک Commit عمومی و تأییدشده قفل است. Installer همان Commit را با HTTPS دریافت می‌کند و SHA واقعی Git را قبل از نصب بررسی می‌کند؛ بنابراین نصب مشتری با هر Commit جدید `main` به‌صورت ناخواسته تغییر نمی‌کند.

## روند نصب

1. بررسی Ubuntu پشتیبانی‌شده و دسترسی root
2. دریافت Manifest نسخه Stable منتشرشده
3. خواندن Version و Commit دقیق نسخه
4. دریافت مخزن عمومی TwinPanel با HTTPS
5. بررسی SHA واقعی Commit با مقدار Manifest
6. بررسی فایل `VERSION`
7. نصب PostgreSQL، Redis، Python runtime، Node.js، Nginx و وابستگی‌ها
8. نصب Backend و Frontend
9. ساخت Secretهای محلی با Permission محدود
10. ساخت دیتابیس و Admin اولیه
11. نصب سرویس‌های systemd
12. نصب منوی SSH با دستورهای `twinpanel` و `tp`
13. فعال‌سازی Nginx و سرویس‌ها
14. Health Check نهایی Web و API

## اطلاعات ورود اولیه

Installer برای اولین ورود یک رمز تصادفی Admin می‌سازد و آن را فقط در فایل زیر با Permission `0600` ذخیره می‌کند:

```text
/root/twinpanel-initial-admin.txt
```

این حساب فقط برای ورود اولیه است. بعد از ورود، مدیر Email و Password خودش را تغییر می‌دهد و می‌تواند فایل اطلاعات اولیه را حذف کند.

در Reinstall یا Update، اگر Admin از قبل وجود داشته باشد، رمز آن بدون اجازه تغییر نمی‌کند.

## مدیریت از SSH

بعد از نصب کافی است اجرا شود:

```bash
twinpanel
```

یا:

```bash
tp
```

منوی SSH شامل وضعیت پنل و سرویس‌ها، مدیریت Admin، مدیریت جداگانه پروتکل‌ها، بروزرسانی، بکاپ، لاگ و Diagnostics، اطلاعات Version و ابزارهای عملیاتی مرتبط است.

## دامنه و SSL

دامنه در نصب اولیه اجباری نیست. پنل ابتدا با IP عمومی سرور قابل استفاده است و دامنه/TLS را می‌توان بعداً از تنظیمات محصول مدیریت کرد.

## بروزرسانی

پنل همان Manifest رسمی Stable را بررسی می‌کند. وقتی نسخه جدید تأیید و منتشر شود، Updater دقیقاً Commit معرفی‌شده در Manifest را دریافت می‌کند.

فرآیند بروزرسانی شامل موارد زیر است:

- Backup قبل از Update
- دریافت Commit دقیق نسخه با HTTPS
- بررسی SHA واقعی Git
- بررسی Version
- نصب وابستگی‌ها و Build
- تعویض اتمیک `/opt/twinpanel/current`
- Restart سرویس‌ها
- Health Check وب و API
- Rollback خودکار به نسخه قبلی در صورت شکست Health Check

## لایسنس

نسخه عمومی فعلی `1.1.0-rc.1` بدون اجبار به License Server قابل نصب است (`license_required: false`). زیرساخت Trial/License داخل محصول باقی می‌ماند تا بعداً بتوان سرویس مرکزی لایسنس را بدون تغییر دستور نصب یک‌خطی مشتری فعال کرد.

## مسیرهای مهم

```text
/opt/twinpanel/current                 نسخه فعال
/opt/twinpanel/releases                نسخه‌های نصب‌شده
/opt/twinpanel/venv                    محیط Python
/etc/twinpanel/backend.env             تنظیمات Backend
/etc/twinpanel/frontend.env            تنظیمات Frontend
/etc/twinpanel/install.env             تنظیمات Install/Release
/var/lib/twinpanel-backups             بکاپ‌ها
/var/lib/twinpanel-license             وضعیت Release/License/Update
/root/twinpanel-initial-admin.txt      اطلاعات Admin اولیه
/usr/local/bin/twinpanel               دستور مدیریت SSH
/usr/local/bin/tp                      نام کوتاه دستور مدیریت
```

## نکته امنیتی

هیچ Production Secret، کلید خصوصی امضای License، SSH Private Key، Telegram Token، فایل `.env` واقعی، کلید خصوصی Certificate، Database Dump یا اطلاعات محرمانه مشتری نباید داخل GitHub Commit شود.
