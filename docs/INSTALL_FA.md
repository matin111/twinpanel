# راهنمای نصب TwinPanel

این راهنما برای نصب نسخه رسمی Self-Hosted پنل است. منبع نصب فقط شاخه/ریلیز رسمی TwinPanel است و نباید از Branchهای آزمایشی نصب انجام شود.

## پیش‌نیازها

- Ubuntu 22.04 یا 24.04 روی سرور تمیز
- دسترسی root
- حداقل 2GB RAM و 2 vCPU پیشنهاد می‌شود
- حداقل 20GB فضای آزاد
- دسترسی خروجی اینترنت برای دریافت بسته نصب و بروزرسانی
- پورت‌های 80 و 443 برای وب عمومی

## نصب سریع

دستور رسمی نصب عمومی از مخزن `matin111/tp27-core` اجرا می‌شود. این Bootstrap هیچ سورس خصوصی یا Secret را داخل مخزن عمومی نگه نمی‌دارد و بسته نصب را فقط از سرویس انتشار/لایسنس دریافت می‌کند.

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/install.sh | sudo bash
```

در صورت وارد نکردن License Key، یک Trial هفت‌روزه برای همان Installation درخواست می‌شود. Trial از اولین Activation موفق شروع می‌شود و با حذف فایل‌های محلی یا نصب مجدد نباید ریست شود.

## روند نصب

1. بررسی سیستم‌عامل، منابع و پورت‌ها
2. ساخت Installation ID و Fingerprint
3. فعال‌سازی License یا Trial هفت‌روزه
4. دریافت آخرین Release مجاز برای همان Installation
5. بررسی SHA256 بسته
6. نصب PostgreSQL، Redis، Python runtime، Node.js، Nginx و وابستگی‌ها
7. نصب Backend و Frontend
8. ساخت Secretهای محلی با Permission محدود
9. ساخت دیتابیس و Admin اولیه
10. نصب systemd serviceها
11. فعال‌سازی Nginx
12. Health Check نهایی Web/API/DB/Redis

## اطلاعات ورود اولیه

Installer یک رمز تصادفی برای Admin اولیه می‌سازد و آن را فقط در فایل زیر با Permission `0600` نگه می‌دارد:

```text
/root/twinpanel-initial-admin.txt
```

بعد از اولین ورود، Email و Password را تغییر دهید و فایل فوق را حذف کنید.

## دامنه و SSL

دامنه در زمان نصب اجباری نیست. پنل ابتدا با IP عمومی سرور قابل استفاده است. سپس از بخش «دامنه و SSL» دامنه‌های API/Web مدیریت می‌شوند.

## بروزرسانی

ادمین داخل پنل وضعیت نسخه را می‌بیند. وقتی نسخه جدید Stable منتشر شود، اعلان بروزرسانی نمایش داده می‌شود و دکمه «بروزرسانی» فرآیند زیر را آغاز می‌کند:

- Backup قبل از Upgrade
- دریافت Release مجاز از سرویس انتشار
- بررسی Hash
- Build/Install نسخه جدید
- Restart سرویس‌ها
- Health Check
- Rollback خودکار در صورت شکست

## Trial و License

- Trial: دقیقاً 7 روز از اولین Activation موفق
- 3 روز مانده: هشدار واضح
- 24 ساعت مانده: هشدار ثابت
- پایان Trial: ورود Admin، License Activation، Backup/Export و Diagnostics باز می‌ماند؛ عملیات مدیریتی جدید طبق Policy لایسنس محدود می‌شود
- قطع موقت License Server نباید ترافیک VPN موجود را ناگهانی قطع کند؛ برای قطعی موقت Grace محدود در نظر گرفته می‌شود

## مسیرهای مهم

```text
/opt/twinpanel/current                 نسخه فعال
/opt/twinpanel/releases                نسخه‌های نصب‌شده
/etc/twinpanel/backend.env             تنظیمات Backend
/etc/twinpanel/frontend.env            تنظیمات Frontend
/var/lib/twinpanel-backups             بکاپ‌ها
/var/lib/twinpanel-license             وضعیت محلی License
/root/twinpanel-initial-admin.txt      اطلاعات Admin اولیه
```

## نکته امنیتی

هیچ Token، License signing key، SSH private key، Telegram token، Database dump یا Production `.env` نباید داخل GitHub Commit شود.
