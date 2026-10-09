"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card} from "./ui";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";
import {getCustomerToken} from "../lib/customer-api";
import {planProtocols,StorePlan,storeRuntimeApi} from "../lib/store-runtime-api";

const protocolMeta:Record<string,{name:string;icon:string;fa:string;en:string}>={
  cisco:{name:"Cisco / OpenConnect",icon:"◉",fa:"اتصال ساده با نام کاربری و رمز و سازگاری مناسب برای استفاده روزمره.",en:"Simple username/password access with broad day-to-day compatibility."},
  openvpn:{name:"OpenVPN",icon:"△",fa:"کانفیگ قابل حمل و پشتیبانی گسترده روی سیستم‌عامل‌های مختلف.",en:"Portable configuration with broad operating-system support."},
  wireguard:{name:"WireGuard",icon:"⚡",fa:"سبک و سریع با فایل یا QR برای اتصال ساده‌تر.",en:"Fast lightweight connectivity with file or QR delivery."},
  l2tp:{name:"L2TP / IPsec",icon:"◎",fa:"قابل استفاده از تنظیمات داخلی بسیاری از دستگاه‌ها.",en:"Works through built-in VPN settings on many devices."},
  v2ray:{name:"V2Ray / Xray",icon:"◇",fa:"گزینه انعطاف‌پذیر برای شرایط متفاوت شبکه.",en:"Flexible connectivity for changing network conditions."}
};
const platforms=["Windows","Android","iPhone / iPad","macOS","Linux"];
const money=(value:number)=>Number(value||0).toLocaleString("fa-IR");

export function StoreRuntime2027(){
  const {pick}=useI18n();
  const {brand}=useBranding();
  const [plans,setPlans]=useState<StorePlan[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [buying,setBuying]=useState<number|null>(null);
  const [message,setMessage]=useState("");
  const [guideProtocol,setGuideProtocol]=useState("wireguard");
  const [guidePlatform,setGuidePlatform]=useState("Windows");

  const load=async()=>{
    setLoading(true);setError("");
    try{setPlans((await storeRuntimeApi.plans()).filter(p=>p.is_active));}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const availableProtocols=useMemo(()=>{
    const set=new Set<string>();plans.forEach(plan=>planProtocols(plan).forEach(p=>set.add(p)));
    return Object.keys(protocolMeta).filter(p=>set.size===0||set.has(p));
  },[plans]);

  const buy=async(plan:StorePlan)=>{
    const token=getCustomerToken();
    if(!token){window.location.href=`/login?next=${encodeURIComponent(`/store?plan=${plan.id}`)}`;return;}
    if(buying)return;
    setBuying(plan.id);setError("");setMessage("");
    try{
      const order=await storeRuntimeApi.createOrder(plan.id,planProtocols(plan));
      setMessage(`${pick("سفارش ساخته شد","Order created")} #${order.id}`);
      window.setTimeout(()=>window.location.href="/panel/orders",700);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBuying(null);}
  };

  return <div className="store store2027 store-conversion">
    <header className="store-nav">
      <div className="brand"><img src={brand.logoUrl} alt={brand.name}/><div><b>{brand.name}</b></div></div>
      <nav><a href="#plans">{pick("پلن‌ها","Plans")}</a><a href="#protocols">{pick("پروتکل‌ها","Protocols")}</a><a href="#guides">{pick("آموزش اتصال","Setup guides")}</a><a href="#faq">FAQ</a><Link href="/reseller">{pick("نمایندگی","Reseller")}</Link></nav>
      <div className="store-actions"><LanguageSwitch compact/><ThemeSwitch compact/><Link className="ghost" href="/login">{pick("ورود","Sign in")}</Link><a className="primary" href="#plans">{pick("خرید سرویس","Buy now")}</a></div>
    </header>

    <main>
      <section className="store-hero-pro">
        <div className="hero-copy">
          <div className="eyebrow"><span className="live-dot"/>{pick("پلن‌های واقعی · تحویل داخل پنل · مدیریت یکپارچه","Live plans · in-panel delivery · unified management")}</div>
          <h1>{pick("سرویس را انتخاب کن،","Choose your service,")} <span>{pick("داخل پنل تحویل بگیر","receive it in your panel")}</span></h1>
          <p>{pick("قیمت، مدت، حجم و پروتکل‌های هر پلن مستقیم از پنل مدیریت دریافت می‌شود. بعد از ثبت سفارش، وضعیت پرداخت و تحویل اکانت را از پنل کاربری دنبال می‌کنی.","Price, duration, traffic and protocols come directly from the management backend. After ordering, track payment and account delivery in your customer panel.")}</p>
          <div className="hero-actions"><a href="#plans" className="primary xl">{pick("مشاهده پلن‌های فعال","View active plans")}</a><Link href="/panel" className="ghost xl">{pick("پنل کاربری","Customer panel")}</Link></div>
          <div className="proof-grid"><div><b>{plans.length||"—"}</b><span>{pick("پلن فعال","active plans")}</span></div><div><b>{availableProtocols.length||"—"}</b><span>{pick("پروتکل موجود","available protocols")}</span></div><div><b>QR / File</b><span>{pick("تحویل اتصال","connection delivery")}</span></div><div><b>FA / EN</b><span>{pick("رابط دو زبانه","bilingual UI")}</span></div></div>
        </div>
        <Card className="hero-product-card"><div className="hero-card-top"><span>{pick("مسیر خرید","Purchase flow")}</span><Badge tone="violet">Live API</Badge></div><div className="delivery-list"><div><span>01</span><b>{pick("انتخاب پلن","Choose plan")}</b><small>{pick("اطلاعات واقعی Backend","Live backend data")}</small></div><div><span>02</span><b>{pick("ثبت سفارش","Create order")}</b><small>{pick("داخل حساب کاربری","Inside your account")}</small></div><div><span>03</span><b>{pick("پرداخت و تحویل","Pay & receive")}</b><small>{pick("پیگیری در پنل کاربری","Track in customer panel")}</small></div></div><Link className="primary full xl" href="/login?next=%2Fstore">{pick("ورود و شروع خرید","Sign in and start")}</Link></Card>
      </section>

      {error&&<div className="runtime-error">{error}</div>}{message&&<div className="runtime-success">{message}</div>}

      <section className="store-block plans-section" id="plans">
        <div className="section-title left"><small>{pick("پلن‌های فعال","ACTIVE PLANS")}</small><h2>{pick("پلن‌هایی که همین الان در Backend فعال‌اند","Plans currently active in the backend")}</h2><p>{pick("هیچ قیمت یا حجم نمونه‌ای در این صفحه استفاده نمی‌شود.","No sample price or quota is used on this page.")}</p></div>
        {loading?<div className="runtime-loading">{pick("در حال دریافت پلن‌ها...","Loading plans...")}</div>:plans.length===0?<Card><p>{pick("در حال حاضر پلن فعالی برای فروش وجود ندارد.","There are currently no active plans for sale.")}</p></Card>:<div className="pricing pricing-pro conversion-pricing">{plans.map((plan,index)=>{
          const protocols=planProtocols(plan);
          return <Card key={plan.id} className={`${index===Math.floor(plans.length/2)?"featured ":""}sales-plan`}>
            {index===Math.floor(plans.length/2)&&plans.length>1&&<div className="recommend-ribbon">{pick("انتخاب میانی","Balanced option")}</div>}
            <div className="plan-head"><Badge tone={index===Math.floor(plans.length/2)?"violet":"ok"}>{pick("فعال","Active")}</Badge><span>{plan.duration_days.toLocaleString("fa-IR")} {pick("روز","days")}</span></div>
            <h3>{plan.name}</h3>{plan.description&&<p className="muted">{plan.description}</p>}
            <div className="plan-price"><strong>{money(plan.price_toman)}</strong><span>{pick("تومان","Toman")}</span></div>
            <div className="plan-facts"><span><b>{plan.traffic_gb.toLocaleString("fa-IR")} GB</b>{pick("حجم","Traffic")}</span><span><b>{plan.device_limit.toLocaleString("fa-IR")}</b>{pick("دستگاه","Devices")}</span></div>
            <ul>{protocols.map(p=><li key={p}><i>✓</i>{protocolMeta[p]?.name||p}</li>)}</ul>
            <button className={index===Math.floor(plans.length/2)?"primary full xl":"ghost full xl"} disabled={buying===plan.id} onClick={()=>void buy(plan)}>{buying===plan.id?pick("در حال ثبت سفارش...","Creating order..."):pick("انتخاب و ادامه خرید","Choose and continue")}</button>
            <small className="plan-note">#{plan.id} · {protocols.length.toLocaleString("fa-IR")} {pick("پروتکل","protocols")}</small>
          </Card>;
        })}</div>}
      </section>

      <section className="store-block" id="protocols"><div className="section-title"><small>PROTOCOLS</small><h2>{pick("پروتکل‌های موجود در پلن‌های فعال","Protocols available in active plans")}</h2></div><div className="protocol-grid">{availableProtocols.map(id=>{const p=protocolMeta[id];return <Card key={id}><span className="protocol-icon">{p.icon}</span><h3>{p.name}</h3><p>{pick(p.fa,p.en)}</p><Badge tone="ok">{pick("قابل ارائه","Available")}</Badge></Card>})}</div></section>

      <section className="store-block guide-studio" id="guides"><div className="section-title"><small>SETUP GUIDE</small><h2>{pick("راهنمای سریع اتصال","Quick connection guide")}</h2></div><div className="guide-pickers"><div>{platforms.map(p=><button key={p} className={guidePlatform===p?"active":""} onClick={()=>setGuidePlatform(p)}>{p}</button>)}</div><div>{availableProtocols.map(id=><button key={id} className={guideProtocol===id?"active":""} onClick={()=>setGuideProtocol(id)}>{protocolMeta[id].name}</button>)}</div></div><div className="module-grid three"><Card><span className="module-icon">1</span><h3>{pick("کلاینت مناسب را نصب کن","Install a compatible client")}</h3><p>{guidePlatform}</p></Card><Card><span className="module-icon">2</span><h3>{pick("اطلاعات اتصال را از پنل بگیر","Get connection details from the panel")}</h3><p>{protocolMeta[guideProtocol]?.name}</p></Card><Card><span className="module-icon">3</span><h3>{pick("کانفیگ را اضافه و متصل شو","Import the config and connect")}</h3><p>{pick("فایل، QR، لینک یا اطلاعات ورود بر اساس پروتکل نمایش داده می‌شود.","File, QR, link or credentials are shown based on the protocol.")}</p></Card></div></section>

      <section className="store-block" id="faq"><div className="section-title"><small>FAQ</small><h2>{pick("سؤال‌های پرتکرار","Frequently asked questions")}</h2></div><div className="faq-grid"><Card><h3>{pick("بعد از خرید چه می‌شود؟","What happens after purchase?")}</h3><p>{pick("سفارش در پنل کاربری ثبت می‌شود و وضعیت پرداخت، ساخت اشتراک و اطلاعات اتصال همان‌جا نمایش داده می‌شود.","The order appears in your customer panel, where payment, provisioning and connection delivery are tracked.")}</p></Card><Card><h3>{pick("قیمت‌ها از کجا می‌آیند؟","Where do prices come from?")}</h3><p>{pick("مستقیم از پلن‌های فعال Backend؛ این صفحه قیمت ثابت یا آزمایشی ندارد.","Directly from active backend plans; this page does not use hard-coded sample pricing.")}</p></Card><Card><h3>{pick("برای خرید باید حساب داشته باشم؟","Do I need an account to buy?")}</h3><p>{pick("بله. سفارش به حساب کاربری متصل است تا پرداخت و تحویل امن و قابل پیگیری باشد.","Yes. Orders are linked to your account so payment and delivery remain secure and traceable.")}</p></Card></div></section>
    </main>

    <footer className="store-footer"><div className="brand"><img src={brand.logoUrl} alt={brand.name}/><b>{brand.name}</b></div><div><Link href="/login">{pick("ورود","Sign in")}</Link><Link href="/panel">{pick("پنل کاربری","Customer panel")}</Link><Link href="/reseller">{pick("نمایندگی","Reseller")}</Link></div></footer>
  </div>;
}
