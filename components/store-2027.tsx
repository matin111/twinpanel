"use client";

import Link from "next/link";
import {useState} from "react";
import {Badge,Card} from "./ui";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";

const protocolDefs=[
  {id:"cisco",name:"Cisco / OpenConnect",icon:"◉",fa:"اتصال ساده با نام کاربری و رمز؛ مناسب استفاده روزمره و کاری.",en:"Simple username/password access for daily and work use."},
  {id:"openvpn",name:"OpenVPN",icon:"△",fa:"سازگاری گسترده و کانفیگ قابل حمل برای سیستم‌عامل‌های مختلف.",en:"Broad compatibility with portable configuration files."},
  {id:"wireguard",name:"WireGuard",icon:"⚡",fa:"سبک، سریع و مدرن با فایل یا QR برای اتصال سریع.",en:"Fast modern connectivity with file or QR delivery."},
  {id:"l2tp",name:"L2TP / IPsec",icon:"◎",fa:"بدون فایل کانفیگ؛ از تنظیمات داخلی بسیاری از دستگاه‌ها قابل راه‌اندازی است.",en:"No config file required; works through built-in VPN settings on many devices."},
  {id:"xray",name:"V2Ray / Xray",icon:"◇",fa:"انعطاف‌پذیر برای شبکه‌ها و شرایط اتصال متفاوت.",en:"Flexible connection options for changing network conditions."}
] as const;

type ProtocolId=typeof protocolDefs[number]["id"];
type PlatformId="windows"|"android"|"ios"|"macos"|"linux";

const platformDefs:[PlatformId,string,string][]=[
  ["windows","Windows","⊞"],["android","Android","◫"],["ios","iPhone / iPad","◉"],["macos","macOS","⌘"],["linux","Linux","◇"]
];

const guideClient:Record<ProtocolId,Record<PlatformId,string>>={
  cisco:{windows:"OpenConnect / compatible client",android:"OpenConnect compatible client",ios:"OpenConnect compatible client",macos:"OpenConnect",linux:"openconnect"},
  openvpn:{windows:"OpenVPN Connect",android:"OpenVPN Connect",ios:"OpenVPN Connect",macos:"OpenVPN Connect",linux:"OpenVPN"},
  wireguard:{windows:"WireGuard",android:"WireGuard",ios:"WireGuard",macos:"WireGuard",linux:"WireGuard"},
  l2tp:{windows:"Built-in VPN settings",android:"Built-in VPN settings",ios:"Built-in VPN settings",macos:"Built-in VPN settings",linux:"NetworkManager / IPsec"},
  xray:{windows:"Compatible Xray client",android:"Compatible Xray client",ios:"Compatible Xray client",macos:"Compatible Xray client",linux:"Compatible Xray client"}
};

export function StorePage2027(){
  const {pick}=useI18n();
  const {brand}=useBranding();
  const initial=(brand.shortName||brand.name||"P").trim().charAt(0).toUpperCase();
  const [guidePlatform,setGuidePlatform]=useState<PlatformId>("windows");
  const [guideProtocol,setGuideProtocol]=useState<ProtocolId>("wireguard");

  const plans=[
    {name:pick("اقتصادی","Basic"),price:pick("۹۰,۰۰۰","90,000"),period:pick("۳۰ روز","30 days"),traffic:"50GB",devices:pick("۱ دستگاه","1 device"),features:[pick("پروتکل‌های اصلی","Core protocols"),pick("پنل کاربری و مشاهده مصرف","Customer panel & usage"),pick("دریافت فایل و اطلاعات اتصال","Connection delivery")],featured:false},
    {name:pick("حرفه‌ای","Professional"),price:pick("۲۴۰,۰۰۰","240,000"),period:pick("۹۰ روز","90 days"),traffic:pick("نامحدود","Unlimited"),devices:pick("۳ دستگاه","3 devices"),features:[pick("هر ۵ پروتکل","All 5 protocols"),pick("انتخاب چند نود","Multi-node access"),pick("پشتیبانی با اولویت","Priority support")],featured:true},
    {name:pick("ویژه","Premium"),price:pick("۴۲۰,۰۰۰","420,000"),period:pick("۱۸۰ روز","180 days"),traffic:pick("نامحدود","Unlimited"),devices:pick("۵ دستگاه","5 devices"),features:[pick("همه امکانات حرفه‌ای","Everything in Professional"),pick("IP اختصاصی اختیاری","Optional dedicated IP"),pick("پشتیبانی ویژه","Priority assistance")],featured:false}
  ];

  const selectedProtocol=protocolDefs.find(x=>x.id===guideProtocol)!;
  const selectedPlatform=platformDefs.find(x=>x[0]===guidePlatform)!;
  const steps=[
    {n:"01",title:pick("کلاینت مناسب را آماده کن","Prepare the right client"),text:pick(`برای ${selectedPlatform[1]} از ${guideClient[guideProtocol][guidePlatform]} استفاده کن.`,`Use ${guideClient[guideProtocol][guidePlatform]} on ${selectedPlatform[1]}.`)},
    {n:"02",title:pick("اطلاعات اتصال را از پنل بگیر","Get connection details from your panel"),text:pick(guideProtocol==="l2tp"?"آدرس سرور، نام کاربری، رمز و کلید IPsec را از بخش اتصال بردار.":"فایل، QR یا لینک اتصال مربوط به اشتراکت را از پنل کاربری دریافت کن.",guideProtocol==="l2tp"?"Copy server address, username, password and IPsec key from the connection section.":"Download the file, QR code or connection link for your subscription.")},
    {n:"03",title:pick("اضافه کن و متصل شو","Import and connect"),text:pick(guideProtocol==="l2tp"?"VPN جدید بساز، نوع L2TP/IPsec را انتخاب کن و اطلاعات را وارد کن.":"کانفیگ را Import کن، سرور را انتخاب کن و اتصال را بزن.",guideProtocol==="l2tp"?"Create a new VPN, select L2TP/IPsec and enter the provided details.":"Import the configuration, choose the server and connect.")}
  ];

  return <div className="store store2027 store-conversion">
    <header className="store-nav">
      <div className="brand"><img src={brand.logoUrl} alt={brand.name}/><div><b>{brand.name}</b></div></div>
      <nav><a href="#plans">{pick("پلن‌ها","Plans")}</a><a href="#protocols">{pick("پروتکل‌ها","Protocols")}</a><a href="#guides">{pick("آموزش اتصال","Setup guides")}</a><a href="#faq">FAQ</a><Link href="/reseller">{pick("نمایندگی","Reseller")}</Link></nav>
      <div className="store-actions"><LanguageSwitch compact/><ThemeSwitch compact/><Link className="ghost" href="/login">{pick("ورود","Sign in")}</Link><a className="primary" href="#plans">{pick("خرید سرویس","Buy now")}</a></div>
    </header>

    <main>
      <section className="store-hero-pro">
        <div className="hero-copy">
          <div className="eyebrow"><span className="live-dot"/>{pick("۵ پروتکل · پنل کاربری · تحویل اتصال","5 protocols · customer panel · connection delivery")}</div>
          <h1>{pick("اتصال حرفه‌ای که","Professional connectivity that")} <span>{pick("خرید و راه‌اندازی‌اش ساده است","is simple to buy and set up")}</span></h1>
          <p>{pick("پلن را انتخاب کن، سرویس را داخل پنل تحویل بگیر و با راهنمای مرحله‌به‌مرحله روی دستگاهت متصل شو. همه چیز از خرید تا تمدید و پشتیبانی در یک مسیر مشخص قرار دارد.","Choose a plan, receive your service in the customer panel and connect with step-by-step setup guidance. Purchase, renewal and support stay in one clear flow.")}</p>
          <div className="hero-actions"><a href="#plans" className="primary xl">{pick("پلن مناسبم را پیدا کن","Find my plan")}</a><a href="#guides" className="ghost xl">{pick("اول آموزش اتصال را ببین","See setup guides first")}</a></div>
          <div className="proof-grid"><div><b>5</b><span>{pick("پروتکل قابل انتخاب","protocols")}</span></div><div><b>QR / File</b><span>{pick("تحویل اتصال در پنل","delivery in panel")}</span></div><div><b>FA / EN</b><span>{pick("رابط دو زبانه","bilingual UI")}</span></div><div><b>24/7</b><span>{pick("دسترسی به پنل و راهنما","panel & guides")}</span></div></div>
        </div>
        <div className="hero-product-card">
          <div className="hero-card-top"><span>{pick("بعد از خرید","After purchase")}</span><Badge tone="violet">{pick("همه چیز یکجا","Everything in one place")}</Badge></div>
          <div className="product-preview"><div className="preview-brand">{initial}</div><div><small>{pick("اشتراک فعال","Active subscription")}</small><b>{pick("پلن حرفه‌ای","Professional plan")}</b><span>{pick("اتصال آماده است","Connection ready")}</span></div></div>
          <div className="delivery-list"><div><span>01</span><b>{pick("سرور و پروتکل","Server & protocol")}</b><small>{pick("انتخاب‌های مجاز اشتراک","Available for your plan")}</small></div><div><span>02</span><b>{pick("فایل، QR یا اطلاعات ورود","File, QR or credentials")}</b><small>{pick("متناسب با پروتکل","Based on protocol")}</small></div><div><span>03</span><b>{pick("مصرف و تاریخ انقضا","Usage & expiry")}</b><small>{pick("همیشه داخل پنل","Always visible in panel")}</small></div></div>
          <Link className="primary full xl" href="/login">{pick("ورود / ثبت‌نام و شروع خرید","Sign in / register and start")}</Link>
        </div>
      </section>

      <section className="value-strip"><div><span>✓</span><b>{pick("انتخاب روشن","Clear choice")}</b><small>{pick("تفاوت پلن‌ها مشخص است","Know what each plan includes")}</small></div><div><span>✓</span><b>{pick("تحویل متمرکز","Central delivery")}</b><small>{pick("اطلاعات اتصال داخل پنل","Connection details in your panel")}</small></div><div><span>✓</span><b>{pick("آموزش قدم‌به‌قدم","Step-by-step guides")}</b><small>{pick("برای دستگاه و پروتکل خودت","For your device and protocol")}</small></div><div><span>✓</span><b>{pick("تمدید و پشتیبانی","Renewal & support")}</b><small>{pick("بدون خروج از حساب","Without leaving your account")}</small></div></section>

      <section className="store-block plans-section" id="plans">
        <div className="section-title left"><small>{pick("انتخاب سرویس","CHOOSE YOUR PLAN")}</small><h2>{pick("پلنی که دقیقاً می‌فهمی چه چیزی می‌خری","Plans that make it clear what you get")}</h2><p>{pick("اگر مطمئن نیستی، پلن حرفه‌ای انتخاب متعادلی برای بیشتر استفاده‌هاست.","If you are unsure, Professional is the balanced option for most use cases.")}</p></div>
        <div className="pricing pricing-pro conversion-pricing">{plans.map((p)=><Card key={p.name} className={p.featured?"featured sales-plan":"sales-plan"}>{p.featured&&<div className="recommend-ribbon">{pick("پیشنهاد برای اکثر کاربران","Recommended for most users")}</div>}<div className="plan-head"><Badge tone={p.featured?"violet":"ok"}>{p.featured?pick("پیشنهادی","Recommended"):pick("قابل خرید","Available")}</Badge><span>{p.period}</span></div><h3>{p.name}</h3><div className="plan-price"><strong>{p.price}</strong><span>{pick("تومان","Toman")}</span></div><div className="plan-facts"><span><b>{p.traffic}</b>{pick("حجم","Traffic")}</span><span><b>{p.devices}</b>{pick("دستگاه","Devices")}</span></div><ul>{p.features.map(f=><li key={f}><i>✓</i>{f}</li>)}</ul><Link href="/login" className={p.featured?"primary full xl":"ghost full xl"}>{pick("انتخاب و ادامه خرید","Choose and continue")}</Link><small className="plan-note">{pick("قبل از پرداخت جزئیات کامل سفارش را می‌بینی.","Review the full order before payment.")}</small></Card>)}</div>
        <div className="purchase-path"><div><span>1</span><b>{pick("پلن را انتخاب کن","Choose a plan")}</b><small>{pick("مدت، حجم و امکانات را مقایسه کن","Compare term, traffic and features")}</small></div><i>←</i><div><span>2</span><b>{pick("وارد حساب شو","Sign in")}</b><small>{pick("سفارش و پرداخت داخل حساب ثبت می‌شود","Order and payment stay in your account")}</small></div><i>←</i><div><span>3</span><b>{pick("سرویس را تحویل بگیر","Receive service")}</b><small>{pick("اطلاعات اتصال و راهنما را ببین","Get connection details and guidance")}</small></div></div>
      </section>

      <section className="store-block alt" id="protocols">
        <div className="section-title"><small>{pick("پروتکل‌ها","PROTOCOLS")}</small><h2>{pick("یک سرویس، چند روش اتصال","One service, multiple ways to connect")}</h2><p>{pick("نوع دستگاه یا شبکه‌ات عوض شد؟ پروتکل مناسب را انتخاب کن و از همان پنل اطلاعات اتصال را بگیر.","When your device or network changes, choose the right protocol and get its connection details from the same panel.")}</p></div>
        <div className="protocol-grid five">{protocolDefs.map((p)=><Card key={p.id} className="protocol-card sales-protocol"><span className="product-icon">{p.icon}</span><h3>{p.name}</h3><p>{pick(p.fa,p.en)}</p><div className="protocol-meta"><Badge tone="violet">{pick("پشتیبانی شده","Supported")}</Badge><button onClick={()=>{setGuideProtocol(p.id);document.getElementById("guides")?.scrollIntoView({behavior:"smooth"})}}>{pick("آموزش اتصال","Setup guide")} →</button></div></Card>)}</div>
      </section>

      <section className="store-block guide-section" id="guides">
        <div className="section-title left"><small>{pick("آموزش اتصال","SETUP GUIDES")}</small><h2>{pick("قبل یا بعد از خرید، دقیقاً بدان چطور متصل می‌شوی","Know exactly how to connect before or after purchase")}</h2><p>{pick("دستگاه و پروتکل را انتخاب کن؛ راهنمای کوتاه همان ترکیب را می‌بینی.","Choose your device and protocol to see the matching quick setup flow.")}</p></div>
        <div className="guide-shell">
          <div className="guide-selectors"><div><small>{pick("۱. دستگاه","1. Device")}</small><div className="guide-tabs">{platformDefs.map(([id,label,icon])=><button key={id} className={guidePlatform===id?"active":""} onClick={()=>setGuidePlatform(id)}><span>{icon}</span>{label}</button>)}</div></div><div><small>{pick("۲. پروتکل","2. Protocol")}</small><div className="guide-tabs protocol-tabs">{protocolDefs.map(p=><button key={p.id} className={guideProtocol===p.id?"active":""} onClick={()=>setGuideProtocol(p.id)}>{p.name}</button>)}</div></div></div>
          <div className="guide-result"><div className="guide-result-head"><div><span className="guide-device-icon">{selectedPlatform[2]}</span><div><small>{selectedPlatform[1]}</small><h3>{selectedProtocol.name}</h3></div></div><Badge tone="violet">{guideClient[guideProtocol][guidePlatform]}</Badge></div><div className="guide-steps">{steps.map(s=><div key={s.n}><span>{s.n}</span><div><b>{s.title}</b><p>{s.text}</p></div></div>)}</div><div className="guide-help"><div><b>{pick("اطلاعات اتصال کجاست؟","Where are my connection details?")}</b><p>{pick("بعد از آماده‌شدن سفارش، از پنل کاربری وارد اشتراک شو و بخش اتصال را باز کن. اطلاعات مربوط به هر پروتکل همان‌جا نمایش داده می‌شود.","After the order is ready, open your subscription in the customer panel and go to Connection. Each protocol shows its own delivery details there.")}</p></div><Link href="/panel" className="ghost">{pick("مشاهده پنل کاربری","Open customer panel")}</Link></div></div>
        </div>
      </section>

      <section className="store-block dedicated"><Card className="dedicated-card conversion-dedicated"><div><small>DEDICATED IP</small><h2>{pick("IP ثابت برای زمانی که ثبات هویت شبکه مهم است","Static IP when network identity needs to stay consistent")}</h2><p>{pick("برای سناریوهایی که تغییر مداوم IP مناسب نیست، IP اختصاصی را هنگام سفارش یا از طریق پشتیبانی درخواست کن.","For workflows where frequent IP changes are undesirable, request a dedicated IP during ordering or through support.")}</p><div className="chips"><span>{pick("منطقه قابل انتخاب","Selectable region")}</span><span>{pick("اختصاص به سرویس","Assigned to your service")}</span><span>{pick("مدیریت از پنل","Managed from panel")}</span></div></div><Link href="/login" className="primary">{pick("درخواست IP اختصاصی","Request dedicated IP")}</Link></Card></section>

      <section className="store-block faq-sales" id="faq">
        <div className="section-title"><small>FAQ</small><h2>{pick("قبل از خرید چه سوالی داری؟","Questions before buying?")}</h2></div>
        <div className="faq-accordion">{[
          [pick("نمی‌دانم کدام پروتکل برای من بهتر است.","I do not know which protocol is best for me."),pick("لازم نیست از ابتدا فقط یک پروتکل را بلد باشی. در پلن‌های دارای چند پروتکل می‌توانی بر اساس دستگاه و شرایط شبکه از Cisco/OpenConnect، OpenVPN، WireGuard، L2TP/IPsec یا V2Ray/Xray استفاده کنی.","You do not need to master one protocol first. Multi-protocol plans let you use Cisco/OpenConnect, OpenVPN, WireGuard, L2TP/IPsec or V2Ray/Xray based on your device and network.")],
          [pick("بعد از خرید اطلاعات اتصال را چطور می‌گیرم؟","How do I receive connection details after purchase?"),pick("اطلاعات اتصال در پنل کاربری همان اشتراک نمایش داده می‌شود؛ بسته به پروتکل می‌تواند شامل فایل، QR، لینک یا نام کاربری و رمز باشد.","Connection details appear inside the subscription in your customer panel. Depending on the protocol, delivery can include a file, QR code, link or username/password.")],
          [pick("اگر دستگاه را عوض کنم چه می‌شود؟","What if I change devices?"),pick("از پنل کاربری دوباره اطلاعات اتصال را دریافت کن و راهنمای دستگاه جدید را از همین بخش آموزش دنبال کن. محدودیت تعداد دستگاه بر اساس پلن اعمال می‌شود.","Get the connection details again from your panel and follow the guide for the new device. Device limits depend on your plan.")],
          [pick("تمدید و مصرف را از کجا می‌بینم؟","Where can I see usage and renewal?"),pick("پنل کاربری وضعیت اشتراک، مصرف، تاریخ انقضا و مسیر تمدید را در اختیار کاربر قرار می‌دهد.","The customer panel shows subscription status, usage, expiry and renewal flow.")],
          [pick("اگر در اتصال مشکل داشتم چه کار کنم؟","What if I have a connection problem?"),pick("ابتدا راهنمای همان پروتکل را بررسی کن؛ سپس از بخش پشتیبانی پنل تیکت ثبت کن تا اطلاعات اشتراک و مشکل در همان حساب قابل پیگیری باشد.","Check the guide for that protocol first, then open a support ticket from your panel so the issue stays linked to your account and subscription.")]
        ].map(([q,a],i)=><details key={q} open={i===0}><summary><span>{q}</span><b>＋</b></summary><p>{a}</p></details>)}</div>
      </section>

      <section className="store-cta conversion-cta"><div><small>{pick("آماده‌ای شروع کنی؟","READY TO START?")}</small><h2>{pick("پلن را انتخاب کن؛ بقیه مسیر داخل پنل مشخص است.","Choose a plan. The rest of the flow is clear inside your panel.")}</h2><p>{pick("خرید، تحویل اتصال، راهنما، مصرف، تمدید و پشتیبانی در یک تجربه یکپارچه.","Purchase, delivery, setup guides, usage, renewal and support in one connected experience.")}</p></div><div><a href="#plans" className="primary xl">{pick("مشاهده پلن‌ها","View plans")}</a><a href="#guides" className="ghost xl">{pick("مشاهده آموزش‌ها","View guides")}</a></div></section>
    </main>

    <footer className="store-footer"><div className="brand"><img src={brand.logoUrl} alt={brand.name}/><div><b>{brand.name}</b></div></div><div><b>{pick("خرید","Purchase")}</b><a href="#plans">{pick("پلن‌ها","Plans")}</a><a href="#protocols">{pick("پروتکل‌ها","Protocols")}</a><Link href="/reseller">{pick("نمایندگی","Reseller")}</Link></div><div><b>{pick("راهنما","Help")}</b><a href="#guides">{pick("آموزش اتصال","Setup guides")}</a><a href="#faq">FAQ</a><a href={brand.supportLink}>{pick("پشتیبانی","Support")}</a></div><div><b>{pick("حساب","Account")}</b><Link href="/login">{pick("ورود / ثبت‌نام","Sign in / Register")}</Link><Link href="/panel">{pick("پنل کاربری","Customer panel")}</Link><Link href="/reseller">{pick("پنل نمایندگی","Reseller panel")}</Link></div><div className="copyright">© {new Date().getFullYear()} {brand.name}</div></footer>
  </div>;
}
