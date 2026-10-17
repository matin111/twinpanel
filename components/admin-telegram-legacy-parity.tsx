"use client";

import {useEffect,useState} from "react";
import {Badge,Shell,Stat} from "./ui";
import {parityApi,TelegramBotStatus} from "../lib/admin-parity-api";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

const customerMenu=[
  ["🛒","خرید اشتراک","Buy subscription"],
  ["📦","اشتراک‌های من","My subscriptions"],
  ["💰","کیف پول","Wallet"],
  ["📚","آموزش","Learning"],
  ["⬇️","دانلود برنامه","Download app"],
  ["🎫","پشتیبانی","Support"],
  ["👤","حساب من","My account"],
] as const;

type BroadcastTargets={total:number};
type BroadcastResult={ok:boolean;total:number;sent:number;failed:number;blocked:number};

async function telegramAdminRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let detail=`API error ${response.status}`;
    try{
      const payload=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof payload.detail==="string")detail=payload.detail;
      else if(typeof payload.message==="string")detail=payload.message;
    }catch{}
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function AdminTelegramLegacyPage(){
  const {pick}=useI18n();
  const [status,setStatus]=useState<TelegramBotStatus|null>(null);
  const [logs,setLogs]=useState("");
  const [token,setToken]=useState("");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [broadcastText,setBroadcastText]=useState("");
  const [broadcastTargets,setBroadcastTargets]=useState<number|null>(null);
  const [broadcastResult,setBroadcastResult]=useState<BroadcastResult|null>(null);

  const load=async()=>{
    setError("");
    try{
      setStatus(await parityApi.telegramStatus());
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }
    try{
      const targets=await telegramAdminRequest<BroadcastTargets>("/v1/admin/telegram-bot/broadcast/targets");
      setBroadcastTargets(Number(targets.total||0));
    }catch{
      setBroadcastTargets(null);
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

  const deleteToken=async()=>{
    if(busy||!status?.token_configured)return;
    const confirmed=window.confirm(
      pick(
        "توکن ذخیره‌شده حذف و سرویس ربات متوقف شود؟ نصب ربات و تنظیمات پنل حذف نمی‌شوند و بعداً می‌توانید توکن جدید ثبت کنید.",
        "Remove the saved token and stop the bot service? The bot installation and panel settings will stay in place so you can save a new token later.",
      ),
    );
    if(!confirmed)return;

    await act(
      "delete-token",
      pick("توکن ربات حذف شد","Bot token removed"),
      async()=>{
        await parityApi.telegramDeleteToken();
        setToken("");
      },
    );
  };

  const sendBroadcast=async()=>{
    if(busy||!broadcastText.trim())return;
    const total=broadcastTargets??0;
    const confirmed=window.confirm(
      pick(
        `این پیام برای ${total.toLocaleString("fa-IR")} کاربر تلگرام ارسال شود؟`,
        `Send this message to ${total.toLocaleString("en-US")} Telegram users?`,
      ),
    );
    if(!confirmed)return;

    setBusy("broadcast");
    setError("");
    setOk("");
    setBroadcastResult(null);
    try{
      const result=await telegramAdminRequest<BroadcastResult>("/v1/admin/telegram-bot/broadcast",{
        method:"POST",
        body:JSON.stringify({text:broadcastText.trim(),disable_web_page_preview:true}),
      });
      setBroadcastResult(result);
      setOk(pick("ارسال پیام همگانی انجام شد","Broadcast completed"));
      if(result.sent>0)setBroadcastText("");
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
          <span>{pick("ربات تلگرام","TELEGRAM BOT")}</span>
          <h1>{pick("ربات تلگرام","Telegram Bot")}</h1>
          <p>{pick("تنظیم، راه‌اندازی و کنترل ربات فروش و پشتیبانی تلگرام.","Configure, run and control the Telegram sales and support bot.")}</p>
        </div>
        <div className="tg-legacy-hero-side">
          <Badge tone={active?"ok":installed?"warn":"bad"}>{stateLabel}</Badge>
          <button className="tg-hero-refresh" disabled={Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی وضعیت","Refresh status")}</button>
        </div>
      </section>

      {error&&<div className="runtime-error">{error}</div>}
      {ok&&<div className="runtime-success">{ok}</div>}

      <div className="stats dashboard-stats tg-legacy-stats">
        <Stat label={pick("وضعیت ربات","Bot status")} value={stateLabel} icon="◉"/>
        <Stat label={pick("توکن","Token")} value={tokenReady?pick("تنظیم شده","Configured"):pick("تنظیم نشده","Missing")} icon="⌁"/>
        <Stat label={pick("آمادگی اجرا","Runtime")} value={runtimeReady?pick("آماده","Ready"):pick("آماده نیست","Not ready")} icon="▦"/>
        <Stat label={pick("نام کاربری","Username")} value={username} icon="♙"/>
      </div>

      <section className="tg-legacy-card tg-service-card">
        <div className="tg-section-head">
          <div>
            <small>{pick("تنظیمات ربات","BOT SETTINGS")}</small>
            <h2>{pick("توکن و کنترل ربات","Token and bot control")}</h2>
          </div>
          <Badge tone={active?"ok":"warn"}>{active?pick("در حال اجرا","Running"):pick("متوقف","Stopped")}</Badge>
        </div>

        <div className="tg-service-grid">
          <div className="tg-token-panel">
            <label className="field">
              <span>Bot Token</span>
              <input type="password" dir="ltr" value={token} onChange={e=>setToken(e.target.value)} placeholder="123456789:AA..." autoComplete="off"/>
            </label>
            <small>{pick("توکن ربات را از BotFather وارد کنید.","Enter the bot token from BotFather.")}</small>
            <div className="tg-action-row">
              <button className="primary" disabled={Boolean(busy)||!token.trim()} onClick={()=>void act("token",pick("توکن ذخیره شد","Token saved"),async()=>{await parityApi.telegramSaveToken(token.trim());setToken("");})}>{busy==="token"?pick("در حال بررسی...","Checking..."):pick("ذخیره توکن","Save token")}</button>
              <button className="ghost" disabled={Boolean(busy)||!tokenReady} onClick={()=>void act("test",pick("اتصال ربات تأیید شد","Bot connection verified"),parityApi.telegramTest)}>{busy==="test"?pick("در حال تست...","Testing..."):pick("تست اتصال","Test connection")}</button>
              <button className="ghost danger" disabled={Boolean(busy)||!tokenReady} onClick={()=>void deleteToken()}>{busy==="delete-token"?pick("در حال حذف...","Removing..."):pick("حذف توکن","Remove token")}</button>
            </div>
          </div>

          <div className="tg-runtime-panel">
            <div className="tg-runtime-row"><span><b>{pick("آمادگی اجرا","Runtime")}</b></span><Badge tone={runtimeReady?"ok":"bad"}>{runtimeReady?pick("آماده","Ready"):pick("آماده نیست","Not ready")}</Badge></div>
            <div className="tg-runtime-row"><span><b>{pick("نصب ربات","Bot install")}</b></span><Badge tone={installed?"ok":"warn"}>{installed?pick("نصب شده","Installed"):pick("نصب نشده","Not installed")}</Badge></div>
            <div className="tg-runtime-row"><span><b>{pick("وضعیت اجرا","Process state")}</b></span><Badge tone={active?"ok":"warn"}>{active?pick("فعال","Active"):pick("متوقف","Stopped")}</Badge></div>
            <div className="tg-action-row tg-service-actions">
              <button className="primary" disabled={Boolean(busy)||!tokenReady} onClick={()=>void act("install",pick("نصب / تعمیر ربات انجام شد","Bot install / repair completed"),parityApi.telegramInstall)}>{busy==="install"?pick("در حال نصب...","Installing..."):pick("نصب / تعمیر","Install / Repair")}</button>
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
            <small>{pick("امکانات ربات","BOT FEATURES")}</small>
            <h2>{pick("منوی کاربر در ربات","Customer bot menu")}</h2>
          </div>
        </div>
        <div className="tg-customer-menu">
          {customerMenu.map(item=><article key={item[1]}><i>{item[0]}</i><span><b>{pick(item[1],item[2])}</b></span></article>)}
        </div>
      </section>

      <section className="tg-legacy-card">
        <div className="tg-section-head">
          <div>
            <small>{pick("پیام همگانی","BROADCAST")}</small>
            <h2>{pick("ارسال پیام همگانی","Broadcast message")}</h2>
          </div>
          <Badge tone={(broadcastTargets??0)>0?"ok":"warn"}>
            {broadcastTargets===null
              ?pick("نامشخص","Unknown")
              :pick(`${broadcastTargets.toLocaleString("fa-IR")} کاربر`,`${broadcastTargets.toLocaleString("en-US")} users`)}
          </Badge>
        </div>
        <div className="tg-broadcast-panel">
          <label className="field tg-broadcast-field">
            <span>{pick("متن پیام","Message")}</span>
            <textarea
              value={broadcastText}
              maxLength={4000}
              rows={7}
              onChange={e=>setBroadcastText(e.target.value)}
              placeholder={pick("متن پیام همگانی را وارد کنید...","Write the broadcast message...")}
            />
          </label>
          <div className="tg-broadcast-footer">
            <small dir="ltr">{broadcastText.length.toLocaleString("en-US")} / 4000</small>
            <button
              className="primary"
              disabled={Boolean(busy)||!tokenReady||!broadcastText.trim()||(broadcastTargets!==null&&broadcastTargets<=0)}
              onClick={()=>void sendBroadcast()}
            >
              {busy==="broadcast"?pick("در حال ارسال...","Sending..."):pick("ارسال به همه کاربران","Send to all users")}
            </button>
          </div>
          {broadcastResult&&<div className="tg-broadcast-result">
            <span>{pick("کل","Total")}: <b>{broadcastResult.total.toLocaleString()}</b></span>
            <span>{pick("ارسال شد","Sent")}: <b>{broadcastResult.sent.toLocaleString()}</b></span>
            <span>{pick("ناموفق","Failed")}: <b>{broadcastResult.failed.toLocaleString()}</b></span>
            <span>{pick("مسدود کرده‌اند","Blocked")}: <b>{broadcastResult.blocked.toLocaleString()}</b></span>
          </div>}
        </div>
      </section>

      <section className="tg-legacy-card tg-log-card">
        <div className="tg-section-head">
          <div><small>{pick("لاگ ربات","BOT LOG")}</small><h2>{pick("لاگ سرویس","Service log")}</h2></div>
          <button className="ghost" disabled={Boolean(busy)} onClick={()=>void act("logs",pick("لاگ بروزرسانی شد","Logs refreshed"),async()=>{const result=await parityApi.telegramLogs();setLogs(result.logs||"");})}>{busy==="logs"?pick("در حال دریافت...","Loading..."):pick("بروزرسانی لاگ","Refresh logs")}</button>
        </div>
        <pre className="tg-runtime-log" dir="ltr">{logs||pick("برای مشاهده لاگ، دکمه بروزرسانی لاگ را بزنید.","Click Refresh logs to load the latest bot output.")}</pre>
      </section>
    </div>
  </Shell>;
}
