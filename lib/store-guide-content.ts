export type StoreGuideProtocol="cisco"|"openvpn"|"wireguard"|"l2tp"|"v2ray";
export type StoreGuidePlatform="windows"|"android"|"ios"|"macos"|"linux";

export type StoreGuideStep={
  title:string;
  detail:string;
};

export type StoreGuideEntry={
  client:string;
  downloadUrl:string;
  downloadLabel:string;
  credential:string;
  warning?:string;
  steps:StoreGuideStep[];
  fixes:string[];
};

export type StoreGuidePlatformMeta={
  id:StoreGuidePlatform;
  fa:string;
  en:string;
  icon:string;
  hintFa:string;
  hintEn:string;
};

export const storeGuidePlatforms:StoreGuidePlatformMeta[]=[
  {id:"android",fa:"اندروید",en:"Android",icon:"◆",hintFa:"راهنمای واقعی Android",hintEn:"Real Android guide"},
  {id:"ios",fa:"آیفون / آیپد",en:"iPhone / iPad",icon:"●",hintFa:"راهنمای واقعی iOS",hintEn:"Real iOS guide"},
  {id:"windows",fa:"ویندوز",en:"Windows",icon:"⊞",hintFa:"راهنمای واقعی Windows",hintEn:"Real Windows guide"},
  {id:"macos",fa:"macOS",en:"macOS",icon:"⌘",hintFa:"راهنمای واقعی macOS",hintEn:"Real macOS guide"},
  {id:"linux",fa:"لینوکس",en:"Linux",icon:"⌁",hintFa:"راهنمای واقعی Linux",hintEn:"Real Linux guide"},
];

const ciscoSystems:Record<StoreGuidePlatform,StoreGuideEntry>={
  windows:{client:"OpenConnect GUI",downloadUrl:"https://gui.openconnect-vpn.net/download/",downloadLabel:"دانلود رسمی OpenConnect برای Windows",credential:"Server + Username + Password",steps:[
    {title:"برنامه را نصب کن",detail:"نسخه 64-bit ویندوز را از صفحه رسمی OpenConnect GUI بگیر و با تنظیمات پیش‌فرض نصب کن."},
    {title:"پروفایل جدید بساز",detail:"OpenConnect GUI را باز کن؛ از File → Profiles → New profile یک پروفایل جدید بساز."},
    {title:"آدرس سرور را وارد کن",detail:"در Gateway فقط دامنه یا IP نمایش‌داده‌شده در پنل کاربری را وارد کن و پروفایل را ذخیره کن."},
    {title:"نام کاربری و رمز را بزن",detail:"پروفایل را انتخاب کن، Connect را بزن و Username/Password اختصاصی اشتراک را وارد کن."},
    {title:"اتصال را بررسی کن",detail:"بعد از سبزشدن وضعیت یک سایت را باز کن. اگر وصل نشد، برنامه را با Run as administrator اجرا کن."},
  ],fixes:["اگر Login failed دیدی، فاصله ابتدا/انتهای نام کاربری یا رمز را پاک کن.","اگر اتصال روی Connecting ماند، سرور جایگزین همان اشتراک را امتحان کن."]},
  android:{client:"OpenConnect",downloadUrl:"https://f-droid.org/packages/net.openconnect_vpn.android/",downloadLabel:"دانلود OpenConnect از F-Droid",credential:"Server + Username + Password",steps:[
    {title:"OpenConnect را نصب کن",detail:"نسخه مناسب دستگاه را از F-Droid نصب کن؛ برای نصب APK ممکن است اجازه Install unknown apps لازم باشد."},
    {title:"پروفایل بساز",detail:"دکمه + را بزن، یک نام برای پروفایل انتخاب کن و Server address پنل کاربری را وارد کن."},
    {title:"پروفایل را ذخیره کن",detail:"تنظیمات پیش‌فرض را تغییر نده؛ پروفایل ساخته‌شده را لمس کن."},
    {title:"اطلاعات حساب را وارد کن",detail:"نام کاربری و رمز اختصاصی را وارد و گواهی سرور را فقط اگر نام سرور درست است تأیید کن."},
    {title:"مجوز VPN را بده",detail:"پیام Connection request را OK کن؛ آیکون کلید بالای گوشی یعنی اتصال فعال است."},
  ],fixes:["Battery optimization را برای OpenConnect روی Unrestricted بگذار تا در پس‌زمینه قطع نشود.","در اینترنت همراه و Wi‑Fi جداگانه تست کن؛ بعضی شبکه‌ها یک مسیر را محدود می‌کنند."]},
  ios:{client:"Cisco Secure Client",downloadUrl:"https://apps.apple.com/us/app/cisco-secure-client/id1135064690",downloadLabel:"دریافت Cisco Secure Client از App Store",credential:"Server + Username + Password",steps:[
    {title:"برنامه رسمی Cisco را نصب کن",detail:"Cisco Secure Client را از App Store نصب و برنامه را باز کن."},
    {title:"Connection جدید اضافه کن",detail:"Connections → Add VPN Connection را بزن و یک Description دلخواه وارد کن."},
    {title:"Server Address را وارد کن",detail:"آدرس سرور نمایش‌داده‌شده در پنل کاربری را دقیق وارد و Save را بزن."},
    {title:"اتصال را روشن کن",detail:"کلید AnyConnect VPN را روشن و در پیام iOS گزینه Allow را انتخاب کن."},
    {title:"وارد حساب شو",detail:"Username و Password را وارد کن؛ علامت VPN بالای صفحه اتصال موفق را نشان می‌دهد."},
  ],fixes:["اگر Server Untrusted دیدی، آدرس سرور را با پنل کاربری تطبیق بده و بدون اطمینان ادامه نده.","اگر رمز ذخیره نمی‌شود طبیعی است؛ iOS ممکن است برای هر اتصال دوباره آن را بخواهد."]},
  macos:{client:"Cisco Secure Client",downloadUrl:"https://www.cisco.com/site/us/en/products/security/secure-client/index.html",downloadLabel:"صفحه رسمی Cisco Secure Client",credential:"Server + Username + Password",steps:[
    {title:"کلاینت Cisco را نصب کن",detail:"نسخه سازگار macOS را از منبع رسمی Cisco نصب کن."},
    {title:"مجوز شبکه را تأیید کن",detail:"در اولین اجرا اگر macOS درخواست Network Extension داد، آن را از Privacy & Security تأیید کن."},
    {title:"سرور را وارد کن",detail:"در کادر اتصال دامنه یا IP نمایش‌داده‌شده در پنل کاربری را بدون فاصله وارد کن."},
    {title:"Connect را بزن",detail:"نام کاربری و رمز اختصاصی را وارد و اتصال را تأیید کن."},
    {title:"وضعیت را کنترل کن",detail:"آیکون Cisco در نوار بالای macOS باید حالت Connected را نشان دهد."},
  ],fixes:["اگر System Extension مسدود شد، از Privacy & Security گزینه Allow را بزن و برنامه را دوباره باز کن.","اگر کلاینت Cisco سازگار نبود، OpenConnect را به‌عنوان جایگزین بررسی کن."]},
  linux:{client:"OpenConnect",downloadUrl:"https://www.infradead.org/openconnect/",downloadLabel:"مستندات رسمی OpenConnect",credential:"Server + Username + Password",steps:[
    {title:"بسته را نصب کن",detail:"در Ubuntu/Debian اجرا کن: sudo apt update && sudo apt install openconnect network-manager-openconnect-gnome"},
    {title:"روش گرافیکی را باز کن",detail:"Settings → Network → VPN → + را باز و Multi-protocol VPN client (openconnect) را انتخاب کن."},
    {title:"Gateway را وارد کن",detail:"آدرس سرور پنل کاربری را در Gateway بگذار و پروفایل را ذخیره کن."},
    {title:"وصل شو",detail:"پروفایل را روشن و Username/Password را وارد کن. روش ترمینال: sudo openconnect SERVER"},
    {title:"اتصال را قطع کن",detail:"در روش ترمینال Ctrl+C و در روش گرافیکی کلید VPN را خاموش کن."},
  ],fixes:["اگر گزینه OpenConnect در Settings نیست، یک‌بار NetworkManager را restart یا سیستم را reboot کن.","خطای certificate را با بررسی دقیق دامنه حل کن؛ تأیید کورکورانه امن نیست."]},
};

const openvpnSystems:Record<StoreGuidePlatform,StoreGuideEntry>={
  windows:{client:"OpenVPN Connect",downloadUrl:"https://openvpn.net/client/",downloadLabel:"دانلود رسمی OpenVPN Connect",credential:"OVPN file + Username/Password (if requested)",steps:[
    {title:"OpenVPN Connect را نصب کن",detail:"نسخه Windows را از سایت رسمی بگیر، نصب کن و برنامه را باز کن."},
    {title:"فایل را دریافت کن",detail:"در پنل کاربری، پروتکل OpenVPN را باز و فایل .ovpn سرور موردنظر را دانلود کن."},
    {title:"پروفایل را Import کن",detail:"در OpenVPN Connect بخش Upload File را بزن یا فایل .ovpn را داخل پنجره برنامه بکش."},
    {title:"اطلاعات ورود را وارد کن",detail:"اگر برنامه درخواست کرد، Username و Password همان اشتراک را وارد کن؛ Save password فقط روی دستگاه شخصی."},
    {title:"پروفایل را روشن کن",detail:"کلید کنار پروفایل را روشن و پیام اتصال ویندوز را تأیید کن."},
  ],fixes:["Timeout معمولاً با انتخاب فایل TCP به‌جای UDP یا برعکس حل می‌شود.","فایل OVPN را ویرایش نکن؛ برای سرور دیگر فایل همان سرور را از پنل بگیر."]},
  android:{client:"OpenVPN Connect",downloadUrl:"https://play.google.com/store/apps/details?id=net.openvpn.openvpn",downloadLabel:"دریافت OpenVPN Connect از Google Play",credential:"OVPN file + Username/Password (if requested)",steps:[
    {title:"برنامه رسمی را نصب کن",detail:"OpenVPN Connect را از Google Play نصب و شرایط استفاده را تأیید کن."},
    {title:"فایل OVPN را دانلود کن",detail:"از پنل کاربری فایل سرور موردنظر را روی گوشی ذخیره کن."},
    {title:"Upload File را انتخاب کن",detail:"File → Browse را بزن، فایل .ovpn را انتخاب و OK کن."},
    {title:"نام پروفایل را ذخیره کن",detail:"در صورت نیاز نام کاربری را وارد و Add را بزن."},
    {title:"اتصال را فعال کن",detail:"کلید پروفایل را روشن، رمز را وارد و Connection request اندروید را OK کن."},
  ],fixes:["برای جلوگیری از قطع پس‌زمینه، Battery usage برنامه را روی Unrestricted بگذار.","اگر Import خطا داد، فایل را دوباره و مستقیماً از پنل دانلود کن."]},
  ios:{client:"OpenVPN Connect",downloadUrl:"https://apps.apple.com/us/app/openvpn-connect/id590379981",downloadLabel:"دریافت OpenVPN Connect از App Store",credential:"OVPN file + Username/Password (if requested)",steps:[
    {title:"OpenVPN Connect را نصب کن",detail:"برنامه رسمی را از App Store نصب و باز کن."},
    {title:"فایل را از پنل بگیر",detail:"روی Download OVPN بزن؛ از Share گزینه Open in OpenVPN را انتخاب کن."},
    {title:"پروفایل را اضافه کن",detail:"در صفحه Import روی Add بزن و در صورت نیاز Username را وارد کن."},
    {title:"اتصال را روشن کن",detail:"کلید پروفایل را روشن و پیام Add VPN Configurations را Allow کن."},
    {title:"رمز را وارد کن",detail:"Password اشتراک را وارد کن؛ نمایش علامت VPN یعنی اتصال برقرار است."},
  ],fixes:["اگر فایل با برنامه دیگری باز شد، از Files روی فایل نگه‌دار و Share → OpenVPN را بزن.","در صورت Timeout فایل TCP یا سرور جایگزین را از پنل دریافت کن."]},
  macos:{client:"OpenVPN Connect",downloadUrl:"https://openvpn.net/connect-docs/connect-for-macos.html",downloadLabel:"دانلود رسمی OpenVPN برای macOS",credential:"OVPN file + Username/Password (if requested)",steps:[
    {title:"نسخه macOS را نصب کن",detail:"فایل DMG رسمی را باز و OpenVPN Connect را به Applications منتقل کن."},
    {title:"فایل OVPN را بگیر",detail:"از پنل کاربری فایل کانفیگ سرور موردنظر را دانلود کن."},
    {title:"فایل را Import کن",detail:"فایل را روی OpenVPN Connect بکش یا از File → Browse انتخاب کن."},
    {title:"پروفایل را ذخیره کن",detail:"در صورت درخواست Username را وارد و Add را بزن."},
    {title:"وصل شو",detail:"کلید پروفایل را روشن، رمز را وارد و اجازه VPN سیستم را تأیید کن."},
  ],fixes:["اگر macOS اجازه نداد، Privacy & Security را باز و Network Extension را Allow کن.","برای قطع کامل، کلید پروفایل را خاموش کن؛ بستن پنجره برنامه کافی نیست."]},
  linux:{client:"OpenVPN Community",downloadUrl:"https://openvpn.net/community/",downloadLabel:"صفحه رسمی OpenVPN Community",credential:"OVPN file + Username/Password (if requested)",steps:[
    {title:"OpenVPN را نصب کن",detail:"در Ubuntu/Debian اجرا کن: sudo apt update && sudo apt install openvpn"},
    {title:"فایل را در مسیر امن بگذار",detail:"فایل .ovpn را از پنل بگیر و مثلاً در ~/Downloads/vpn.ovpn ذخیره کن."},
    {title:"اتصال را اجرا کن",detail:"ترمینال: sudo openvpn --config ~/Downloads/vpn.ovpn"},
    {title:"ورود را کامل کن",detail:"اگر خواسته شد Username و Password اشتراک را وارد کن؛ تا نمایش Initialization Sequence Completed صبر کن."},
    {title:"اتصال را قطع کن",detail:"در همان ترمینال Ctrl+C بزن."},
  ],fixes:["خطای AUTH_FAILED یعنی نام کاربری/رمز یا وضعیت اشتراک را بررسی کن.","TLS timeout را با فایل TCP یا سرور جایگزین امتحان کن."]},
};

const wireguardSystems:Record<StoreGuidePlatform,StoreGuideEntry>={
  windows:{client:"WireGuard",downloadUrl:"https://www.wireguard.com/install/",downloadLabel:"دانلود رسمی WireGuard",credential:"WireGuard .conf file",steps:[
    {title:"WireGuard را نصب کن",detail:"نسخه رسمی Windows را از سایت WireGuard نصب و برنامه را باز کن."},
    {title:"فایل کانفیگ را بگیر",detail:"در پنل کاربری، WireGuard را باز و فایل .conf سرور موردنظر را دانلود کن."},
    {title:"Tunnel را Import کن",detail:"Add Tunnel → Import tunnel(s) from file را بزن و فایل .conf را انتخاب کن."},
    {title:"Tunnel را فعال کن",detail:"پروفایل واردشده را انتخاب و Activate را بزن."},
    {title:"اتصال را بررسی کن",detail:"وضعیت باید Active شود و شمارنده Transfer شروع به تغییر کند؛ سپس IP را بررسی کن."},
  ],fixes:["اگر Handshake دیده نمی‌شود، یک سرور یا کانفیگ تازه از پنل بگیر.","اگر اینترنت بعد از فعال‌سازی قطع شد، Tunnel را Deactivate کن و MTU/مسیر را با پشتیبانی بررسی کن."]},
  android:{client:"WireGuard",downloadUrl:"https://www.wireguard.com/install/",downloadLabel:"دانلود رسمی WireGuard برای Android",credential:"WireGuard .conf file or QR",steps:[
    {title:"WireGuard را نصب کن",detail:"برنامه رسمی WireGuard را از لینک رسمی یا فروشگاه دستگاه نصب کن."},
    {title:"کانفیگ را از پنل بگیر",detail:"فایل WireGuard یا QR همان سرور را از پنل کاربری دریافت کن."},
    {title:"Tunnel جدید اضافه کن",detail:"دکمه + را بزن و Import from file or archive یا Scan from QR code را انتخاب کن."},
    {title:"مجوز VPN را تأیید کن",detail:"در اولین اتصال پیام Connection request اندروید را OK کن."},
    {title:"کلید اتصال را روشن کن",detail:"کلید کنار Tunnel را روشن کن؛ نمایش Handshake و Transfer یعنی مسیر برقرار است."},
  ],fixes:["Battery optimization را برای WireGuard محدود نکن تا اتصال پس‌زمینه پایدار بماند.","اگر QR اسکن نشد، فایل .conf را دانلود و Import کن."]},
  ios:{client:"WireGuard",downloadUrl:"https://www.wireguard.com/install/",downloadLabel:"دریافت WireGuard برای iPhone / iPad",credential:"WireGuard .conf file or QR",steps:[
    {title:"WireGuard را نصب کن",detail:"برنامه رسمی WireGuard را نصب و باز کن."},
    {title:"کانفیگ را دریافت کن",detail:"از پنل کاربری فایل .conf یا QR سرور موردنظر را دریافت کن."},
    {title:"Tunnel را اضافه کن",detail:"Add a tunnel را بزن و Create from file or archive یا Create from QR code را انتخاب کن."},
    {title:"اجازه VPN را بده",detail:"پیام Add VPN Configurations را Allow کن و در صورت نیاز رمز دستگاه را وارد کن."},
    {title:"Tunnel را فعال کن",detail:"کلید Tunnel را روشن کن و سپس IP اتصال را بررسی کن."},
  ],fixes:["اگر Tunnel روشن می‌شود ولی Transfer صفر است، کانفیگ همان سرور را دوباره از پنل بگیر.","اگر QR قدیمی است، آن را Refresh و دوباره اسکن کن."]},
  macos:{client:"WireGuard",downloadUrl:"https://www.wireguard.com/install/",downloadLabel:"دانلود رسمی WireGuard برای macOS",credential:"WireGuard .conf file",steps:[
    {title:"WireGuard را نصب کن",detail:"نسخه رسمی macOS را نصب و برنامه را باز کن."},
    {title:"فایل Tunnel را بگیر",detail:"فایل .conf سرور موردنظر را از پنل کاربری دانلود کن."},
    {title:"Tunnel را Import کن",detail:"Import tunnel(s) from file را انتخاب و فایل را وارد کن."},
    {title:"اجازه شبکه را تأیید کن",detail:"اگر macOS درخواست مجوز VPN یا Network Extension داد، آن را تأیید کن."},
    {title:"Activate را بزن",detail:"Tunnel را فعال کن و Handshake/Transfer را بررسی کن."},
  ],fixes:["اگر macOS مجوز نمی‌دهد، Privacy & Security را بررسی و برنامه را دوباره باز کن.","اگر Handshake ندارد، کانفیگ تازه یا سرور جایگزین را امتحان کن."]},
  linux:{client:"WireGuard / wg-quick",downloadUrl:"https://www.wireguard.com/install/",downloadLabel:"راهنمای رسمی نصب WireGuard",credential:"WireGuard .conf file",steps:[
    {title:"WireGuard را نصب کن",detail:"در Ubuntu/Debian اجرا کن: sudo apt update && sudo apt install wireguard"},
    {title:"فایل کانفیگ را بگیر",detail:"فایل .conf همان سرور را از پنل کاربری دریافت کن."},
    {title:"فایل را در /etc/wireguard بگذار",detail:"فایل را مثلاً به /etc/wireguard/wg0.conf منتقل و دسترسی آن را محدود کن."},
    {title:"Tunnel را بالا بیاور",detail:"sudo wg-quick up wg0 را اجرا کن و سپس sudo wg وضعیت Handshake را ببین."},
    {title:"Tunnel را پایین بیاور",detail:"برای قطع اتصال sudo wg-quick down wg0 را اجرا کن."},
  ],fixes:["اگر wg-quick خطای DNS داد، بسته resolvconf یا تنظیم DNS کانفیگ را بررسی کن.","اگر Latest handshake خالی است، endpoint/شبکه یا کانفیگ تازه را بررسی کن."]},
};

const l2tpSystems:Record<StoreGuidePlatform,StoreGuideEntry>={
  windows:{client:"VPN داخلی Windows",downloadUrl:"",downloadLabel:"بدون نصب برنامه",credential:"Server + Username + Password + PSK",steps:[
    {title:"تنظیمات VPN را باز کن",detail:"Windows 11: Settings → Network & internet → VPN → Add VPN را باز کن."},
    {title:"نوع اتصال را انتخاب کن",detail:"VPN provider را Windows (built-in) و VPN type را L2TP/IPsec with pre-shared key بگذار."},
    {title:"Server و PSK را وارد کن",detail:"Connection name دلخواه، Server name از پنل و Pre-shared key را از اطلاعات اشتراک وارد کن."},
    {title:"اطلاعات حساب را ثبت کن",detail:"Type of sign-in info را Username and password بگذار و اطلاعات اشتراک را وارد و Save کن."},
    {title:"Connect را بزن",detail:"از فهرست VPN روی پروفایل ساخته‌شده → Connect بزن."},
  ],fixes:["خطای Security layer معمولاً از PSK اشتباه، ساعت نادرست سیستم یا مسدودبودن UDP 500/4500 است.","اگر سرور پشت NAT است ممکن است تنظیم اضافی Windows لازم شود؛ قبل از تغییر Registry با پشتیبانی هماهنگ کن."]},
  android:{client:"VPN داخلی Android (فقط نسخه‌های پشتیبانی‌شده)",downloadUrl:"",downloadLabel:"سازگاری محدود در Android جدید",credential:"Server + Username + Password + PSK",warning:"Android 12 و جدیدتر در نسخه استاندارد، L2TP/IPsec را از VPN داخلی حذف کرده‌اند. اگر گزینه L2TP را نمی‌بینی از OpenVPN، WireGuard یا V2Ray استفاده کن.",steps:[
    {title:"نسخه Android را بررسی کن",detail:"در Settings → About phone نسخه Android را ببین. این راهنما برای دستگاهی است که گزینه L2TP/IPsec PSK دارد."},
    {title:"VPN را باز کن",detail:"Settings → Network & internet / Connections → VPN → Add VPN."},
    {title:"نوع L2TP را انتخاب کن",detail:"Type را L2TP/IPsec PSK بگذار و Server address پنل را وارد کن."},
    {title:"PSK و حساب را وارد کن",detail:"IPsec pre-shared key، Username و Password را دقیق از پنل کپی کن."},
    {title:"ذخیره و اتصال",detail:"Save را بزن، پروفایل را باز و Connect را انتخاب کن."},
  ],fixes:["اگر گزینه L2TP وجود ندارد، مشکل از حذف این قابلیت در Android جدید است نه اکانت.","در این حالت OpenVPN، WireGuard یا V2Ray انتخاب مطمئن‌تری است."]},
  ios:{client:"VPN داخلی iPhone / iPad",downloadUrl:"",downloadLabel:"بدون نصب برنامه",credential:"Server + Account + Password + Secret",steps:[
    {title:"بخش VPN را باز کن",detail:"Settings → General → VPN & Device Management → VPN → Add VPN Configuration."},
    {title:"Type را L2TP بگذار",detail:"Description دلخواه و Server را از پنل کاربری وارد کن."},
    {title:"Account و Password را وارد کن",detail:"Username را در Account و رمز اشتراک را در Password قرار بده."},
    {title:"Secret را ثبت کن",detail:"کلید PSK پنل را در Secret وارد کن و Send All Traffic را روشن بگذار."},
    {title:"Done و Connect",detail:"Done را بزن و کلید Status را روشن کن؛ علامت VPN اتصال موفق را نشان می‌دهد."},
  ],fixes:["اگر Authentication failed دیدی Account، Password و Secret را دوباره کپی کن.","اگر گزینه L2TP در نسخه دستگاهت وجود ندارد، از OpenVPN یا WireGuard استفاده کن."]},
  macos:{client:"VPN داخلی macOS",downloadUrl:"",downloadLabel:"بدون نصب برنامه",credential:"Server + Account + Password + Shared Secret",steps:[
    {title:"VPN جدید اضافه کن",detail:"System Settings → VPN → Add VPN Configuration → L2TP over IPSec را انتخاب کن."},
    {title:"Server و Account را وارد کن",detail:"Display Name دلخواه، Server Address و Account Name را از پنل وارد کن."},
    {title:"Authentication Settings",detail:"Password اشتراک و Shared Secret همان PSK پنل را ثبت کن."},
    {title:"مسیر کامل را فعال کن",detail:"در Advanced، گزینه Send all traffic over VPN connection را روشن کن."},
    {title:"Create و Connect",detail:"پروفایل را ذخیره و کلید اتصال را روشن کن."},
  ],fixes:["اگر Add VPN نوع L2TP را نشان نمی‌دهد، نسخه macOS یا سیاست دستگاه را بررسی و OpenVPN را جایگزین کن.","PSK و Password دو مقدار جدا هستند؛ آن‌ها را جابه‌جا وارد نکن."]},
  linux:{client:"NetworkManager L2TP",downloadUrl:"https://github.com/nm-l2tp/NetworkManager-l2tp",downloadLabel:"پروژه NetworkManager-l2tp",credential:"Gateway + Username + Password + PSK",steps:[
    {title:"افزونه L2TP را نصب کن",detail:"Ubuntu/Debian: sudo apt update && sudo apt install network-manager-l2tp network-manager-l2tp-gnome"},
    {title:"VPN جدید بساز",detail:"Settings → Network → VPN → + → Layer 2 Tunneling Protocol (L2TP)."},
    {title:"Gateway و حساب",detail:"Gateway، Username و Password را از پنل کاربری وارد کن."},
    {title:"IPsec را تنظیم کن",detail:"IPsec Settings را باز، Enable IPsec tunnel را روشن و Pre-shared key را وارد کن."},
    {title:"ذخیره و اتصال",detail:"Save را بزن و پروفایل را روشن کن؛ در صورت نبودن گزینه یک‌بار سیستم را reboot کن."},
  ],fixes:["اگر سرویس xl2tpd تداخل دارد، log سیستم را بررسی کن و هم‌زمان دو کلاینت L2TP اجرا نکن.","اگر شبکه UDP 500/4500 را می‌بندد، OpenVPN TCP را جایگزین کن."]},
};

const v2raySystems:Record<StoreGuidePlatform,StoreGuideEntry>={
  windows:{client:"v2rayN",downloadUrl:"https://github.com/2dust/v2rayN/releases",downloadLabel:"دانلود رسمی v2rayN برای Windows",credential:"Subscription URL or VLESS/VMess/Trojan link",steps:[
    {title:"v2rayN را دانلود کن",detail:"از GitHub Releases بسته Windows 64 desktop را بگیر، از ZIP خارج و v2rayN.exe را اجرا کن."},
    {title:"لینک را از حساب کپی کن",detail:"در پنل کاربری روی Copy subscription یا Copy config بزن؛ لینک را کامل کپی کن."},
    {title:"کانفیگ را وارد کن",detail:"برای یک لینک از Servers → Import share links from clipboard استفاده کن؛ برای Subscription از Subscription group settings آن را اضافه کن."},
    {title:"سرور را انتخاب کن",detail:"روی سرور راست‌کلیک و Set as active server را بزن؛ سپس Test servers real delay را اجرا کن."},
    {title:"پروکسی سیستم را روشن کن",detail:"System proxy را روی Set system proxy بگذار؛ برای عبور همه برنامه‌ها در صورت نیاز TUN Mode را با دسترسی Administrator روشن کن."},
  ],fixes:["اگر کانفیگ وارد نشد، مطمئن شو لینک کامل و بدون فاصله کپی شده است.","اگر مرورگر وصل می‌شود ولی برنامه دیگر نه، TUN Mode یا تنظیم Proxy همان برنامه را بررسی کن."]},
  android:{client:"v2rayNG",downloadUrl:"https://github.com/2dust/v2rayNG/releases",downloadLabel:"دانلود رسمی v2rayNG برای Android",credential:"Subscription URL or VLESS/VMess/Trojan link",steps:[
    {title:"v2rayNG را نصب کن",detail:"از GitHub Releases فایل universal یا نسخه مناسب معماری گوشی را دانلود و نصب کن."},
    {title:"لینک را کپی کن",detail:"از پنل کاربری لینک Subscription یا کانفیگ را کامل Copy کن."},
    {title:"وارد برنامه کن",detail:"دکمه + را بزن؛ Import config from Clipboard یا Scan QR code را انتخاب کن."},
    {title:"پروفایل را انتخاب کن",detail:"روی نام سرور بزن تا انتخاب شود؛ از منو Real delay all configuration را برای تست پینگ اجرا کن."},
    {title:"اتصال را روشن کن",detail:"دکمه دایره‌ای پایین را بزن و Connection request اندروید را OK کن."},
  ],fixes:["اگر Test connection خطا داد، کانفیگ را از پنل Refresh و دوباره Import کن.","Battery optimization را برای v2rayNG غیرفعال کن تا اتصال در پس‌زمینه قطع نشود."]},
  ios:{client:"Streisand",downloadUrl:"https://apps.apple.com/tr/app/streisand/id6450534064",downloadLabel:"دریافت Streisand از App Store",credential:"Subscription URL or VLESS/VMess/Trojan link",steps:[
    {title:"Streisand را نصب کن",detail:"برنامه را از App Store نصب و باز کن؛ این برنامه از VLESS، VMess و Trojan پشتیبانی می‌کند."},
    {title:"لینک را کپی کن",detail:"در پنل کاربری روی لینک اشتراک یا کانفیگ بزن و Copy را انتخاب کن."},
    {title:"کانفیگ را اضافه کن",detail:"در Streisand دکمه + را بزن و Import from Clipboard را انتخاب کن؛ برای QR از Scan استفاده کن."},
    {title:"سرور را انتخاب کن",detail:"پروفایل واردشده را لمس کن تا فعال شود و نام آن در صفحه اصلی دیده شود."},
    {title:"اتصال را روشن کن",detail:"دکمه اتصال را بزن و پیام Add VPN Configurations را Allow کن."},
  ],fixes:["اگر App Store منطقه برنامه را نشان نداد، از کلاینت سازگار دیگری که در دسترس حسابت است استفاده کن.","اگر لینک Subscription بروزرسانی نشد، گزینه Update/Refresh را بزن."]},
  macos:{client:"v2rayN",downloadUrl:"https://github.com/2dust/v2rayN/releases",downloadLabel:"دانلود رسمی v2rayN برای macOS",credential:"Subscription URL or VLESS/VMess/Trojan link",warning:"برای مک حتماً فایل متناسب با پردازنده را بگیر: arm64 برای Apple Silicon و 64 برای Intel.",steps:[
    {title:"نسخه درست را دانلود کن",detail:"از Releases فایل macOS arm64 یا macOS 64 را مطابق پردازنده بگیر و برنامه را به Applications منتقل کن."},
    {title:"اجازه اجرای برنامه",detail:"اگر macOS مانع اجرا شد، Privacy & Security را باز و Open Anyway را فقط برای فایل رسمی GitHub بزن."},
    {title:"لینک را Import کن",detail:"لینک حساب را کپی و در v2rayN از Import share links from clipboard وارد کن."},
    {title:"پروفایل را فعال کن",detail:"سرور را Active و سپس System Proxy را روشن کن."},
    {title:"اتصال را تست کن",detail:"مرورگر را باز و IP را بررسی کن؛ در صورت نیاز بین سرورهای حساب جابه‌جا شو."},
  ],fixes:["خطای damaged app را فقط برای نسخه رسمی با Open Anyway بررسی کن؛ فایل ناشناس را اجرا نکن.","اگر برنامه‌ها از پروکسی سیستم پیروی نمی‌کنند از TUN Mode سازگار استفاده کن."]},
  linux:{client:"v2rayN",downloadUrl:"https://github.com/2dust/v2rayN/releases",downloadLabel:"دانلود رسمی v2rayN برای Linux",credential:"Subscription URL or VLESS/VMess/Trojan link",steps:[
    {title:"بسته مناسب را بگیر",detail:"برای Ubuntu/Debian فایل linux-64.deb یا linux-arm64.deb را از Releases دانلود کن."},
    {title:"بسته را نصب کن",detail:"در پوشه دانلود اجرا کن: sudo apt install ./v2rayN-linux-64.deb"},
    {title:"لینک را وارد کن",detail:"لینک حساب را کپی و در برنامه با Import from Clipboard یا Subscription وارد کن."},
    {title:"پروفایل را فعال کن",detail:"یک سرور را Active و System Proxy یا TUN Mode را متناسب با دسکتاپ روشن کن."},
    {title:"وضعیت را بررسی کن",detail:"تاخیر سرورها و Log برنامه را ببین؛ برای قطع اتصال Proxy/TUN را خاموش کن."},
  ],fixes:["اگر بسته نصب نشد sudo apt --fix-broken install را اجرا و دوباره تلاش کن.","برای TUN ممکن است دسترسی ریشه یا مجوز شبکه لازم باشد."]},
};

export const storeGuideContent:Record<StoreGuideProtocol,{summary:string;systems:Record<StoreGuidePlatform,StoreGuideEntry>}>= {
  cisco:{summary:"برای Cisco/OpenConnect سه مورد از پنل کاربری لازم است: آدرس سرور، نام کاربری و رمز عبور.",systems:ciscoSystems},
  openvpn:{summary:"برای OpenVPN فایل اختصاصی .ovpn را از پنل کاربری دریافت می‌کنی؛ بعضی پلن‌ها علاوه بر فایل، نام کاربری و رمز هم می‌خواهند.",systems:openvpnSystems},
  wireguard:{summary:"برای WireGuard فایل اختصاصی .conf یا QR همان سرور را از پنل کاربری می‌گیری و داخل کلاینت رسمی Import می‌کنی.",systems:wireguardSystems},
  l2tp:{summary:"برای L2TP/IPsec چهار مقدار لازم است: Server، Username، Password و IPsec Pre-Shared Key (Secret).",systems:l2tpSystems},
  v2ray:{summary:"برای V2Ray/Xray یک لینک اشتراک یا لینک کانفیگ از نوع VLESS/VMess/Trojan از پنل کاربری دریافت می‌کنی.",systems:v2raySystems},
};

const LEGACY_APP_IMAGE_BASE="https://movilineapp.com/learning/apps";
const LEGACY_STEP_IMAGE_BASE="https://movilineapp.com/learning/screenshots";

export function storeGuideAppImage(platform:StoreGuidePlatform,protocol:StoreGuideProtocol):string{
  if(protocol==="openvpn")return `${LEGACY_APP_IMAGE_BASE}/openvpn.png`;
  if(protocol==="wireguard")return `${LEGACY_APP_IMAGE_BASE}/wireguard.png`;
  if(protocol==="cisco")return `${LEGACY_APP_IMAGE_BASE}/${platform==="ios"||platform==="macos"?"cisco":"openconnect"}.png`;
  if(protocol==="v2ray"){
    if(platform==="android")return `${LEGACY_APP_IMAGE_BASE}/v2rayng.png`;
    if(platform==="ios")return `${LEGACY_APP_IMAGE_BASE}/hiddify.png`;
    return `${LEGACY_APP_IMAGE_BASE}/v2rayn.png`;
  }
  return "";
}

export function storeGuideScreenshot(platform:StoreGuidePlatform,protocol:StoreGuideProtocol,index:number):string{
  return `${LEGACY_STEP_IMAGE_BASE}/${platform}/${protocol}/${String(index+1).padStart(2,"0")}.webp`;
}
