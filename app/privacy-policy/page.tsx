import type {Metadata} from "next";
import "./privacy-policy.css";

export const metadata:Metadata={
  title:"سیاست حفظ حریم خصوصی TwinConnect | Privacy Policy",
  description:"سیاست حفظ حریم خصوصی برنامه TwinConnect؛ اطلاعات حساب، اشتراک، اتصال VPN، نگهداری و درخواست حذف داده‌ها.",
  robots:{index:true,follow:true},
};

const contacts=[
  {label:"کانال اطلاع‌رسانی TwinPanel",href:"https://t.me/Twinpanel"},
  {label:"ربات پشتیبانی و لایسنس TwinPanel",href:"https://t.me/TwinPanelbot"},
  {label:"مخزن رسمی GitHub",href:"https://github.com/matin111/twinpanel"},
];

export default function PrivacyPolicyPage(){
  return <main className="privacy-page" dir="rtl">
    <header className="privacy-hero">
      <div className="privacy-brand">TWINCONNECT <span>by TwinPanel</span></div>
      <p className="privacy-eyebrow">TRANSPARENCY · SECURITY · CONTROL</p>
      <h1>سیاست حفظ حریم خصوصی</h1>
      <p className="privacy-lead">این صفحه توضیح می‌دهد TwinConnect هنگام ورود به حساب، دریافت تنظیمات و برقراری اتصال VPN چگونه با اطلاعات شما کار می‌کند.</p>
      <p className="privacy-date">آخرین به‌روزرسانی: ۴ آذر ۱۴۰۵ (۲۵ نوامبر ۲۰۲۶)</p>
    </header>

    <nav className="privacy-language" aria-label="زبان صفحه">
      <a href="#fa-policy">فارسی</a>
      <a href="#en-policy" dir="ltr">English</a>
    </nav>

    <article id="fa-policy" className="privacy-card">
      <p className="privacy-kicker">نسخه فارسی</p>
      <h2>۱. درباره این سیاست</h2>
      <p>این سیاست مربوط به برنامه <strong>TwinConnect</strong> و سرویس‌های مرتبط با آن در اکوسیستم TwinPanel است. با استفاده از برنامه، اطلاعات لازم برای ورود، بررسی دسترسی، دریافت پروفایل‌های اتصال و ایجاد تونل VPN پردازش می‌شود. این صفحه باید همراه با تنظیمات واقعی سرور پنل، سرویس لایسنس و نودهای اتصال خوانده شود.</p>

      <h2>۲. چه اطلاعاتی ممکن است پردازش شود؟</h2>
      <ul>
        <li><strong>اطلاعات حساب:</strong> نام کاربری یا شناسه حساب و اطلاعات احراز هویت موردنیاز برای ورود به پنل.</li>
        <li><strong>اطلاعات اشتراک:</strong> شناسه اشتراک، وضعیت و زمان اعتبار، حجم مصرفی یا باقی‌مانده، محدودیت دستگاه و پروتکل‌های مجاز.</li>
        <li><strong>اطلاعات اتصال:</strong> آدرس و مشخصات فنی سرور، پروتکل انتخاب‌شده و پارامترهای لازم برای برقراری اتصال. این اطلاعات ممکن است شامل داده‌های محرمانه پیکربندی باشد.</li>
        <li><strong>اطلاعات فنی و عیب‌یابی:</strong> نسخه برنامه و سیستم‌عامل، وضعیت اتصال، زمان رخداد خطا و گزارش‌هایی که برای بررسی مشکل در اختیار پشتیبانی قرار می‌دهید.</li>
        <li><strong>اطلاعات لایسنس:</strong> اطلاعات فنی لازم برای تشخیص نصب برنامه و بررسی معتبر بودن مجوز استفاده از قابلیت‌های TwinConnect.</li>
        <li><strong>داده‌های شبکه:</strong> هنگام فعال بودن VPN، ترافیک شبکه از مسیر سرور انتخاب‌شده عبور می‌کند. زیرساخت نود ممکن است فراداده‌های فنی لازم برای مسیریابی، امنیت و مدیریت اتصال را پردازش کند.</li>
      </ul>

      <h2>۳. هدف از پردازش اطلاعات</h2>
      <ul>
        <li>احراز هویت و حفظ نشست ورود شما؛</li>
        <li>بررسی لایسنس و دسترسی به قابلیت‌های برنامه؛</li>
        <li>دریافت اشتراک‌ها، سرورها و پروفایل‌های مجاز؛</li>
        <li>ایجاد، مدیریت و قطع اتصال VPN و اعمال محدودیت‌های اشتراک؛</li>
        <li>تشخیص خطا، حفظ امنیت سرویس و پاسخ‌گویی به درخواست‌های پشتیبانی.</li>
      </ul>

      <h2>۴. اشتراک‌گذاری اطلاعات با سرویس‌های دیگر</h2>
      <p>برای ارائه سرویس، بخشی از اطلاعات ضروری ممکن است با این دریافت‌کنندگان تبادل شود:</p>
      <ul>
        <li><strong>سرور پنل TwinPanel:</strong> برای ورود، دریافت اطلاعات حساب و اشتراک و مدیریت دسترسی‌ها.</li>
        <li><strong>سرویس اعتبارسنجی لایسنس:</strong> برای بررسی مجوز و وضعیت دسترسی برنامه.</li>
        <li><strong>نود VPN انتخاب‌شده:</strong> برای انتقال ترافیک و برقراری اتصال. محل نود انتخابی شما می‌تواند خارج از کشور محل اقامتتان باشد.</li>
        <li><strong>پشتیبانی:</strong> اطلاعاتی که خودتان در پیام یا گزارش عیب‌یابی برای پشتیبانی ارسال می‌کنید.</li>
      </ul>
      <p>اپراتور هر نود ممکن است تابع سیاست‌ها و الزامات قانونی محل فعالیت خود باشد. رویه نگهداری گزارش‌های نودها می‌تواند با تنظیمات و اپراتور همان زیرساخت متفاوت باشد. از ارسال رمز عبور، کلید خصوصی یا فایل کامل پیکربندی در گزارش عمومی یا کانال عمومی خودداری کنید.</p>

      <h2>۵. ترافیک اینترنت و فعالیت آنلاین</h2>
      <p>TwinConnect یک برنامه اتصال VPN است و ترافیک را مطابق پروتکل و سروری که انتخاب می‌کنید از تونل عبور می‌دهد. این موضوع به معنی آن نیست که برنامه برای نمایش تبلیغات یا ساخت پروفایل بازاریابی به محتوای ارتباطات شما نیاز دارد. با این حال، اپراتور زیرساخت VPN ممکن است برای انتقال بسته‌ها، جلوگیری از سوءاستفاده و عیب‌یابی، اطلاعات فنی اتصال را پردازش کند. رمزگذاری ارتباط شما تا مقصد نهایی به پروتکل انتخابی، تنظیمات تونل و رمزگذاری خود سرویس مقصد بستگی دارد.</p>

      <h2>۶. نگهداری و امنیت اطلاعات</h2>
      <p>اطلاعات حساب و اشتراک ممکن است تا زمانی که حساب یا اشتراک فعال است و پس از آن به میزان لازم برای سوابق عملیاتی، امنیتی و تعهدات قانونی در پنل نگهداری شود. گزارش‌های فنی و اتصال نیز ممکن است مطابق تنظیمات نگهداری سرور یا نود مربوطه حفظ شوند. اطلاعات ورود و پیکربندی ذخیره‌شده روی دستگاه را از دسترس دیگران محافظت کنید و در دستگاه‌های مشترک پس از پایان کار از حساب خارج شوید.</p>
      <p>برای کاهش خطر دسترسی غیرمجاز، دسترسی به اطلاعات باید به نیازهای عملیاتی سرویس محدود شود. هیچ روش انتقال یا ذخیره‌سازی داده‌ای را نمی‌توان کاملاً بدون ریسک تضمین کرد.</p>

      <h2>۷. درخواست دسترسی یا حذف اطلاعات</h2>
      <p>برای درخواست بررسی، اصلاح یا حذف اطلاعات مرتبط با حساب TwinPanel یا داده‌های پشتیبانی، از طریق ربات رسمی پیام دهید و نام کاربری یا شناسه اشتراک را ارائه کنید. ممکن است برای جلوگیری از حذف اطلاعات شخص دیگر، احراز مالکیت حساب لازم باشد. برخی سوابقی که برای امنیت، حسابداری، حل اختلاف یا الزام قانونی ضروری هستند ممکن است تا پایان دوره لازم نگهداری شوند. حذف برنامه از دستگاه به‌تنهایی اطلاعات ذخیره‌شده در سرور پنل یا نود را حذف نمی‌کند.</p>

      <h2>۸. کودکان</h2>
      <p>TwinConnect برای استفاده عمومی کودکان طراحی نشده است. اگر سرپرست قانونی هستید و معتقدید اطلاعات فرد کم‌سن بدون مجوز در اختیار سرویس قرار گرفته، از راه ارتباطی رسمی درخواست بررسی کنید.</p>

      <h2>۹. تغییرات این سیاست</h2>
      <p>در صورت تغییر قابلیت‌ها، زیرساخت یا الزامات قانونی، این صفحه ممکن است به‌روزرسانی شود. تاریخ آخرین تغییر در بالای صفحه درج می‌شود. ادامه استفاده از نسخه به‌روزشده برنامه پس از انتشار تغییرات، تابع نسخه جدید این سیاست خواهد بود.</p>

      <h2>۱۰. راه‌های ارتباط رسمی</h2>
      <ul className="privacy-contacts">
        {contacts.map(item=><li key={item.href}><a href={item.href} target="_blank" rel="noopener noreferrer">{item.label}</a></li>)}
      </ul>
    </article>

    <article id="en-policy" className="privacy-card privacy-english" dir="ltr">
      <p className="privacy-kicker">English version</p>
      <h2>1. About this policy</h2>
      <p>This Privacy Policy applies to the <strong>TwinConnect</strong> application and related services in the TwinPanel ecosystem. TwinConnect processes information needed to sign in, verify app access, retrieve eligible connection profiles and establish a VPN connection. This policy should be read together with the actual configuration of the relevant panel, licensing service and VPN nodes.</p>

      <h2>2. Information that may be processed</h2>
      <ul>
        <li><strong>Account information:</strong> your username or account identifier and authentication information required to sign in to your panel.</li>
        <li><strong>Subscription information:</strong> subscription identifier, status and validity period, traffic allowance or usage, device limits and permitted protocols.</li>
        <li><strong>Connection configuration:</strong> server addresses and technical settings, selected protocol and parameters required to establish a connection. These settings may include confidential configuration data.</li>
        <li><strong>Technical and diagnostic information:</strong> app and operating-system version, connection state, error events and diagnostic reports you choose to send to support.</li>
        <li><strong>License information:</strong> technical information needed to identify an app installation and validate entitlement to TwinConnect features.</li>
        <li><strong>Network data:</strong> while the VPN is active, network traffic is routed through the selected server. The node infrastructure may process technical connection metadata needed for routing, security and connection management.</li>
      </ul>

      <h2>3. Why information is processed</h2>
      <ul>
        <li>To authenticate you and maintain your sign-in session;</li>
        <li>To validate the app license and feature access;</li>
        <li>To retrieve subscriptions, servers and eligible connection profiles;</li>
        <li>To establish, manage and disconnect VPN sessions and enforce subscription limits;</li>
        <li>To diagnose errors, protect the service and respond to support requests.</li>
      </ul>

      <h2>4. Sharing with service providers</h2>
      <p>Information necessary to provide the service may be exchanged with:</p>
      <ul>
        <li><strong>TwinPanel panel server:</strong> for authentication, account and subscription information, and access management.</li>
        <li><strong>License validation service:</strong> to verify the app entitlement and license status.</li>
        <li><strong>Selected VPN node:</strong> to route traffic and establish the connection. Your selected node may be located in a different country from your place of residence.</li>
        <li><strong>Support:</strong> information you voluntarily include in a support message or diagnostic report.</li>
      </ul>
      <p>Each VPN node operator may be subject to the policies and legal requirements applicable to its infrastructure and location. Node logging and retention practices may vary by operator and configuration. Do not post passwords, private keys or complete connection profiles in public reports or channels.</p>

      <h2>5. Internet traffic and online activity</h2>
      <p>TwinConnect is a VPN client. It routes network traffic through the tunnel according to the protocol and server you select. The app does not need the contents of your communications for advertising or marketing profiling. However, the VPN infrastructure operator may process technical connection information for packet delivery, abuse prevention and troubleshooting. Encryption between your device and the final destination depends on the selected protocol, tunnel configuration and encryption used by the destination service.</p>

      <h2>6. Data retention and security</h2>
      <p>Account and subscription records may be retained while an account or subscription is active and afterwards for as long as needed for operational, security, accounting or legal purposes. Technical and connection logs may be retained according to the settings of the relevant server or node. Protect credentials and configuration data stored on your device, and sign out when using a shared device.</p>
      <p>Access to information should be limited to operational needs. No method of data transmission or storage can be guaranteed to be completely risk-free.</p>

      <h2>7. Access, correction and deletion requests</h2>
      <p>To request access to, correction of or deletion of information associated with your TwinPanel account or support records, contact us through the official bot and provide your username or subscription identifier. We may ask you to verify account ownership before acting on a request. Certain records may be retained for the period necessary for security, accounting, dispute resolution or legal obligations. Uninstalling the app does not by itself delete information stored on the panel server or VPN node.</p>

      <h2>8. Children</h2>
      <p>TwinConnect is not designed for general use by children. A parent or legal guardian who believes that a minor's information has been provided without appropriate authorization may contact us through the official support channel.</p>

      <h2>9. Changes to this policy</h2>
      <p>This policy may be updated when app features, infrastructure or legal requirements change. The latest revision date is shown at the top of this page. The updated policy applies from its publication date.</p>

      <h2>10. Official contact links</h2>
      <ul className="privacy-contacts">
        {contacts.map(item=><li key={item.href}><a href={item.href} target="_blank" rel="noopener noreferrer">{item.label}</a></li>)}
      </ul>
    </article>

    <footer className="privacy-footer">© TwinConnect · TwinPanel · All rights reserved.</footer>
  </main>;
}
