"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {parityApi,TelegramBotStatus} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";

type BotAction={
  icon:string;
  fa:string;
  en:string;
  subFa:string;
  subEn:string;
  href:string;
};

type BotStep={
  n:string;
  fa:string;
  en:string;
  subFa:string;
  subEn:string;
};

const salesSteps:BotStep[]=[
  {n:"01",fa:"شناسایی مشتری",en:"Identify customer",subFa:"Telegram ID ↔ User مرکزی",subEn:"Telegram ID ↔ central User"},
  {n:"02",fa:"خواندن پلن‌ها",en:"Load plans",subFa:"قیمت و محدودیت مستقیم از پنل",subEn:"Price and limits from the panel"},
  {n:"03",fa:"تأیید پرداخت",en:"Verify payment",subFa:"قبل از ساخت سرویس",subEn:"Before provisioning service"},
  {n:"04",fa:"ساخت اشتراک",en:"Create subscription",subFa:"در دیتابیس مرکزی",subEn:"In the central database"},
  {n:"05",fa:"تخصیص نود",en:"Assign node",subFa:"از سرورهای مجاز و سالم",subEn:"From healthy allowed nodes"},
  {n:"06",fa:"ساخت اکانت",en:"Create account",subFa:"Credential پروتکل انتخابی",subEn:"Selected protocol credential"},
  {n:"07",fa:"تحویل به مشتری",en:"Deliver",subFa:"سرور، اکانت و راهنما",subEn:"Server, account and guide"},
];

const botActions:BotAction[]=[
  {icon:"◈",fa:"دریافت پلن‌ها",en:"Load plans",subFa:"فقط پلن‌های فعال از API مرکزی",subEn:"Only active plans from the central API",href:"/admin/plans"},
  {icon:"♙",fa:"ساخت یا شناسایی مشتری",en:"Create or identify customer",subFa:"Telegram ID به User مرکزی متصل می‌شود",subEn:"Telegram ID is linked to the central User",href:"/admin/users"},
  {icon:"▱",fa:"ساخت و تمدید اشتراک",en:"Create and renew subscription",subFa:"بعد از تأیید قطعی پرداخت",subEn:"Only after confirmed payment",href:"/admin/subscriptions"},
  {icon:"▦",fa:"دریافت سرور و اکانت",en:"Resolve server and account",subFa:"نود، پروتکل و Credential از پنل",subEn:"Node, protocol and credential from the panel",href:"/admin/nodes"},
  {icon:"◫",fa:"پرداخت و رسید",en:"Payment and receipt",subFa:"روش پرداخت و وضعیت سفارش از پنل",subEn:"Payment method and order status from the panel",href:"/admin/payments"},
  {icon:"◌",fa:"پشتیبانی",en:"Support",subFa:"تیکت کاربر وارد پنل مدیریت می‌شود",subEn:"Customer tickets arrive in the admin panel",href:"/admin/support"},
];

const dataRows=[
  ["خرید سرویس","Buy service","Plan","خواندن پلن فعال","Read active plan","قیمت، حجم و مدت","Price, traffic and duration","بدون قیمت داخل کد ربات","No hard-coded bot pricing"],
  ["تأیید پرداخت","Verify payment","Payment + User","ثبت پرداخت و کاربر","Record payment and user","شماره سفارش","Order number","ساخت یکتا با Telegram ID","Unique by Telegram ID"],
  ["ساخت اکانت","Create account","Subscription","ایجاد و فعال‌سازی","Create and activate","وضعیت سرویس","Service status","فقط بعد از پرداخت موفق","Only after successful payment"],
  ["دریافت سرورها","Resolve server","Node + Tunnel","انتخاب نود مجاز","Select allowed node","سرور همان اشتراک","Assigned subscription server","بدون نمایش کل نودها","Never expose all nodes"],
  ["دریافت اتصال","Connection details","ProtocolCredential","ساخت یا دریافت Credential","Create or load credential","آدرس و اطلاعات اتصال","Connection address and credentials","فقط برای همان مشتری","Only for that customer"],
] as const;

const customerMenu=[
  ["🏠","داشبورد","Dashboard","نمای کلی حساب و سرویس","Account and service overview"],
  ["🛒","خرید اشتراک","Buy subscription","انتخاب پلن، کد تخفیف و پرداخت","Plan, discount and payment"],
  ["📦","اشتراک‌های من","My subscriptions","حجم، انقضا، تمدید و اطلاعات اتصال","Traffic, expiry, renewal and connection"],
  ["💰","کیف پول","Wallet","موجودی و عملیات مالی","Balance and wallet operations"],
  ["📚","آموزش","Learning","آموزش اتصال و استفاده","Connection and usage guides"],
  ["⬇️","دانلود برنامه","Download app","فایل‌های دانلود تعریف‌شده در پنل","Downloads configured in the panel"],
  ["🎫","پشتیبانی","Support","ارسال درخواست به پنل مدیر","Send a ticket to the admin panel"],
  ["👤","حساب من","My account","هویت متصل به Telegram ID","Identity linked to Telegram ID"],
] as const;

const securityRules=[
  ["♙","اتصال هویت","Identity binding","Telegram ID فقط به یک User مرکزی متصل می‌شود.","A Telegram ID is bound to one central User."],
  ["◫","پرداخت یکتا","Idempotent payment","Retry نباید اشتراک تکراری یا کسر دوباره ایجاد کند.","Retries must not duplicate subscriptions or charges."],
  ["▦","عدم نمایش شبکه","No network exposure","کاربر فقط سرور تخصیص‌یافته به اشتراک خودش را می‌بیند.","Customers only see the server assigned to their subscription."],
  ["⌾","Credential امن","Secure credentials","توکن، رمز و کانفیگ حساس در UI یا لاگ عمومی نمایش داده نمی‌شود.","Tokens, passwords and sensitive configs are not exposed in the UI or public logs."],
] as const;

export function AdminTelegramLegacyPage(){
  const {pick}=useI18n();
  const [status,setStatus]=useState<TelegramBotStatus|null>(null);
  const [logs,setLogs]=useState("");
  const [token,setToken]=useState("");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    try{
      setStatus(await parityApi.telegramStatus());
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }
  };

  useEffect(()=>{void load();},[]);

  const act=async(key:string,label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(key);
    setError("");
    setOk("");
    try{
      await fn();
      setOk(label);
      await load();
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      setBusy("");
    }
  };

  const state=String(status?.service_state||"not_installed").toLowerCase();
  const active=["active","running"].includes(state);
  const installed=Boolean(status?.installed);
  const tokenReady=Boolean(status?.token_configured);
  const runtimeReady=Boolean(status?.runtime_ready);
  const username=status?.bot?.username?`@${status.bot.username}`:"—";

  const stateLabel=active
    ?pick("فعال","Active")
    :installed
      ?pick("متوقف","Stopped")
      :pick("نصب نشده","Not installed");

  return <Shell active="/admin/telegram">
    <div className="page telegram-legacy">
      <section className="tg-legacy-hero">
        <div className="tg-legacy-hero-icon">✈</div>
        <div className="tg-legacy-hero-copy">
          <span>{pick("ربات فروش مرکزی","CENTRAL SALES BOT")}</span>
          <h1>{pick("ربات تلگرام","Telegram Bot")}</h1>
          <p>{pick("فروش، ساخت اکانت، تمدید، تحویل اتصال و پشتیبانی؛ همه با داده‌های پنل مرکزی و بدون دیتابیس جدا.","Sales, account creation, renewal, connection delivery and support, all backed by the central panel without a separate database.")}</p>
        </div>
        <div className="tg-legacy-hero-side">
          <Badge tone={active?"ok":installed?"warn":"bad"}>{stateLabel}</Badge>
          <small>{pick("منبع اطلاعات ربات","Bot data source")}</small>
          <b>TwinPanel Central API</b>
          <em><i/> {pick("بدون اکانت و دیتابیس تکراری","No duplicate accounts or database")}</em>
          <button className="tg-hero-refresh" disabled={Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی وضعیت","Refresh status")}</button>
        </div>
      </section>

      {error&&<div className="runtime-error">{error}</div>}
      {ok&&<div className="runtime-success">{ok}</div>}

      <div className="stats dashboard-stats tg-legacy-stats">
        <Stat label={pick("وضعیت سرویس","Service status")} value={stateLabel} icon="◉"/>
        <Stat label={pick("توکن","Token")} value={tokenReady?pick("تنظیم شده","Configured"):pick("تنظیم نشده","Missing")} icon="⌁"/>
        <Stat label={pick("Runtime","Runtime")} value={runtimeReady?pick("آماده","Ready"):pick("آماده نیست","Not ready")} icon="▦"/>
        <Stat label={pick("نام کاربری","Username")} value={username} icon="♙"/>
      </div>

      <section className="tg-legacy-card tg-service-card">
        <div className="tg-section-head">
          <div>
            <small>{pick("راه‌اندازی واقعی","LIVE SETUP")}</small>
            <h2>{pick("توکن، نصب و کنترل سرویس","Token, installation and service control")}</h2>
            <p>{pick("این همان مدیریت اجرایی ربات است؛ صفحه جداگانه مدیریت تلگرام دیگر لازم نیست.","This is the actual bot control surface; a separate Telegram Manager page is no longer needed.")}</p>
          </div>
          <Badge tone={active?"ok":"warn"}>{active?pick("در حال اجرا","Running"):pick("نیاز به بررسی","Attention")}</Badge>
        </div>

        <div className="tg-service-grid">
          <div className="tg-token-panel">
            <label className="field">
              <span>Bot Token</span>
              <input type="password" dir="ltr" value={token} onChange={e=>setToken(e.target.value)} placeholder="123456789:AA..." autoComplete="off"/>
            </label>
            <small>{pick("پس از ذخیره، Token دوباره در پنل نمایش داده نمی‌شود.","After saving, the token is never shown back in the panel.")}</small>
            <div className="tg-action-row">
              <button className="primary" disabled={Boolean(busy)||!token.trim()} onClick={()=>void act("token",pick("توکن با موفقیت ذخیره شد","Token saved"),async()=>{await parityApi.telegramSaveToken(token.trim());setToken("");})}>{busy==="token"?pick("در حال بررسی...","Checking..."):pick("ذخیره توکن","Save token")}</button>
              <button className="ghost" disabled={Boolean(busy)||!tokenReady} onClick={()=>void act("test",pick("اتصال ربات تأیید شد","Bot connection verified"),parityApi.telegramTest)}>{busy==="test"?pick("در حال تست...","Testing..."):pick("بررسی اتصال","Test connection")}</button>
            </div>
          </div>

          <div className="tg-runtime-panel">
            <div className="tg-runtime-row"><span><b>Runtime</b><small>Python / aiogram</small></span><Badge tone={runtimeReady?"ok":"bad"}>{runtimeReady?pick("آماده","Ready"):pick("آماده نیست","Not ready")}</Badge></div>
            <div className="tg-runtime-row"><span><b>Service</b><small dir="ltr">twinpanel-bot.service</small></span><Badge tone={installed?"ok":"warn"}>{installed?pick("نصب شده","Installed"):pick("نصب نشده","Not installed")}</Badge></div>
            <div className="tg-runtime-row"><span><b>{pick("وضعیت اجرا","Process state")}</b><small>{pick("وضعیت فعلی پردازش ربات","Current bot process state")}</small></span><Badge tone={active?"ok":"warn"}>{active?pick("فعال","Active"):pick("متوقف","Stopped")}</Badge></div>
            <div className="tg-action-row tg-service-actions">
              <button className="primary" disabled={Boolean(busy)||!tokenReady||!runtimeReady} onClick={()=>void act("install",pick("نصب / تعمیر ربات انجام شد","Bot install / repair completed"),parityApi.telegramInstall)}>{busy==="install"?pick("در حال نصب...","Installing..."):pick("نصب / تعمیر","Install / Repair")}</button>
              <button className="ghost" disabled={Boolean(busy)||!installed||active} onClick={()=>void act("start",pick("ربات شروع شد","Bot started"),parityApi.telegramStart)}>{pick("شروع","Start")}</button>
              <button className="ghost" disabled={Boolean(busy)||!installed} onClick={()=>void act("restart",pick("ربات راه‌اندازی مجدد شد","Bot restarted"),parityApi.telegramRestart)}>{pick("راه‌اندازی مجدد","Restart")}</button>
              <button className="ghost danger" disabled={Boolean(busy)||!installed||!active} onClick={()=>void act("stop",pick("ربات متوقف شد","Bot stopped"),parityApi.telegramStop)}>{pick("توقف","Stop")}</button>
            </div>
          </div>
        </div>
      </section>

      <section className="tg-legacy-card">
        <div className="tg-section-head">
          <div>
            <small>BOT SALES FLOW</small>
            <h2>{pick("از شروع خرید تا تحویل سرور","From purchase start to server delivery")}</h2>
            <p>{pick("جریان قدیمی پنل حفظ شده و همه مراحل به API مرکزی متصل هستند.","The legacy panel flow is preserved and every step is tied to the central API.")}</p>
          </div>
        </div>
        <div className="tg-sales-steps">{salesSteps.map(step=><article key={step.n}><i>{step.n}</i><b>{pick(step.fa,step.en)}</b><small>{pick(step.subFa,step.subEn)}</small></article>)}</div>
      </section>

      <section className="tg-legacy-card">
        <div className="tg-section-head">
          <div>
            <small>{pick("عملیات واقعی ربات","LIVE BOT OPERATIONS")}</small>
            <h2>{pick("هر بخش ربات به کدام قسمت پنل وصل است؟","Which panel section powers each bot operation?")}</h2>
          </div>
        </div>
        <div className="tg-operation-grid">{botActions.map(item=><Link href={item.href} key={item.href}><i>{item.icon}</i><span><b>{pick(item.fa,item.en)}</b><small>{pick(item.subFa,item.subEn)}</small></span><em>←</em></Link>)}</div>
      </section>

      <section className="tg-legacy-card tg-data-card">
        <div className="tg-section-head">
          <div>
            <small>TELEGRAM DATA MAP</small>
            <h2>{pick("اطلاعاتی که ربات می‌خواند یا می‌سازد","Data the bot reads or creates")}</h2>
          </div>
        </div>
        <div className="tg-data-table">
          <div className="tg-data-head"><span>{pick("فرمان مشتری","Customer action")}</span><span>{pick("منبع مرکزی","Central source")}</span><span>{pick("عملیات","Operation")}</span><span>{pick("پاسخ ربات","Bot response")}</span><span>{pick("قانون","Rule")}</span></div>
          {dataRows.map(row=><div className="tg-data-row" key={row[0]}><span><b>{pick(row[0],row[1])}</b></span><code>{row[2]}</code><span>{pick(row[3],row[4])}</span><span>{pick(row[5],row[6])}</span><small>{pick(row[7],row[8])}</small></div>)}
        </div>
      </section>

      <section className="tg-legacy-card">
        <div className="tg-section-head">
          <div>
            <small>{pick("منوی واقعی مشتری","CUSTOMER BOT MENU")}</small>
            <h2>{pick("منوی ربات فروش","Sales bot menu")}</h2>
            <p>{pick("اتصال و دریافت دوباره کانفیگ داخل «اشتراک‌های من» انجام می‌شود تا مالکیت و اعتبار همان سرویس دوباره بررسی شود.","Connection details and config re-delivery live under My subscriptions so ownership and validity are rechecked before delivery.")}</p>
          </div>
        </div>
        <div className="tg-customer-menu">{customerMenu.map(item=><article key={item[1]}><i>{item[0]}</i><span><b>{pick(item[1],item[2])}</b><small>{pick(item[3],item[4])}</small></span></article>)}</div>
      </section>

      <section className="tg-legacy-card">
        <div className="tg-section-head">
          <div>
            <small>{pick("ضد سوءاستفاده","ABUSE PROTECTION")}</small>
            <h2>{pick("ربات فقط سرویس پرداخت‌شده همان کاربر را تحویل می‌دهد","The bot only delivers a paid service to its owner")}</h2>
          </div>
        </div>
        <div className="tg-rule-grid">{securityRules.map(item=><article key={item[1]}><i>{item[0]}</i><span><b>{pick(item[1],item[2])}</b><small>{pick(item[3],item[4])}</small></span></article>)}</div>
      </section>

      <section className="tg-legacy-card tg-log-card">
        <div className="tg-section-head">
          <div><small>RUNTIME LOG</small><h2>{pick("لاگ سرویس","Service log")}</h2><p dir="ltr">twinpanel-bot.service</p></div>
          <button className="ghost" disabled={Boolean(busy)} onClick={()=>void act("logs",pick("لاگ بروزرسانی شد","Logs refreshed"),async()=>{const result=await parityApi.telegramLogs();setLogs(result.logs||"");})}>{busy==="logs"?pick("در حال دریافت...","Loading..."):pick("بروزرسانی لاگ","Refresh logs")}</button>
        </div>
        <pre className="tg-runtime-log" dir="ltr">{logs||pick("برای مشاهده خروجی سرویس، «بروزرسانی لاگ» را بزنید.","Click Refresh logs to load the latest service output.")}</pre>
      </section>
    </div>
  </Shell>;
}
