"use client";

import {createPortal} from "react-dom";
import {useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

type Style="default"|"primary"|"success"|"danger";
type Styles={
  dashboard:Style;purchase:Style;subscriptions:Style;account_link:Style;wallet:Style;
  learning:Style;download:Style;reseller_request:Style;support:Style;account:Style;connect:Style;
};

const DEFAULTS:Styles={
  dashboard:"default",purchase:"success",subscriptions:"default",account_link:"success",wallet:"success",
  learning:"primary",download:"primary",reseller_request:"success",support:"default",account:"default",connect:"primary",
};
const CLEAN:Styles={dashboard:"default",purchase:"default",subscriptions:"default",account_link:"default",wallet:"default",learning:"default",download:"default",reseller_request:"default",support:"default",account:"default",connect:"default"};
const OPTIONS:{value:Style;label:string;hint:string}[]=[
  {value:"default",label:"پیش‌فرض",hint:"رنگ خود تلگرام"},
  {value:"primary",label:"آبی",hint:"Primary"},
  {value:"success",label:"سبز",hint:"Success"},
  {value:"danger",label:"قرمز",hint:"Danger"},
];
const MAIN_BUTTONS:{key:keyof Styles;label:string;emoji:string}[]=[
  {key:"purchase",label:"خرید اشتراک",emoji:"🛒"},{key:"dashboard",label:"داشبورد",emoji:"🏠"},
  {key:"subscriptions",label:"اشتراک‌های من",emoji:"📦"},{key:"account_link",label:"دریافت لینک اکانت",emoji:"🔗"},
  {key:"wallet",label:"کیف پول",emoji:"💰"},{key:"learning",label:"آموزش",emoji:"📚"},
  {key:"download",label:"دانلود برنامه",emoji:"⬇️"},{key:"reseller_request",label:"درخواست نمایندگی",emoji:"🤝"},
  {key:"support",label:"پشتیبانی",emoji:"🎫"},{key:"account",label:"حساب من",emoji:"👤"},
];
const BUTTONS:{key:keyof Styles;label:string;emoji:string}[]=[...MAIN_BUTTONS,{key:"connect",label:"اتصال حساب",emoji:"🔗"}];

function cls(style:Style){return `tg-style-${style}`;}

async function request(init:RequestInit={}):Promise<Styles>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body)headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}/v1/admin/telegram-bot/button-styles`,{...init,headers,cache:"no-store"});
  let payload:unknown=null;
  try{payload=await response.json();}catch{}
  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload
      ?String((payload as {detail:unknown}).detail)
      :`API error ${response.status}`;
    throw new Error(detail);
  }
  return payload as Styles;
}

export function AdminTelegramButtonStyleSettings(){
  const [host,setHost]=useState<Element|null>(null);
  const [styles,setStyles]=useState<Styles>(DEFAULTS);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState("");

  async function load(){
    setLoading(true);setMessage("");
    try{
      const data=await request();
      setStyles({...DEFAULTS,...data});
    }catch(error){setMessage(error instanceof Error?error.message:"خطا در دریافت تنظیمات");}
    finally{setLoading(false);}
  }
  async function save(){
    setSaving(true);setMessage("");
    try{
      const data=await request({method:"PATCH",body:JSON.stringify(styles)});
      setStyles({...DEFAULTS,...data});setMessage("تنظیمات رنگ دکمه‌ها ذخیره شد.");
    }catch(error){setMessage(error instanceof Error?error.message:"ذخیره تنظیمات انجام نشد");}
    finally{setSaving(false);}
  }
  useEffect(()=>{setHost(document.querySelector(".telegram-legacy"));void load();},[]);
  if(!host)return null;

  return createPortal(<>
    <section className="tg-legacy-card tg-button-style-card">
      <div className="tg-section-head tg-style-head">
        <div><small>BOT APPEARANCE</small><h2>ظاهر دکمه‌های ربات</h2><p>رنگ واقعی دکمه‌های منوی اصلی Telegram را انتخاب کنید.</p></div>
        <div className="tg-style-actions">
          <button type="button" className="btn ghost" onClick={()=>setStyles(CLEAN)} disabled={loading||saving}>همه پیش‌فرض</button>
          <button type="button" className="btn ghost" onClick={()=>setStyles(DEFAULTS)} disabled={loading||saving}>پیشنهاد TwinPanel</button>
          <button type="button" className="btn primary" onClick={save} disabled={loading||saving}>{saving?"در حال ذخیره...":"ذخیره رنگ‌ها"}</button>
        </div>
      </div>
      <div className="tg-style-layout">
        <div className="tg-style-controls">
          {BUTTONS.map((item)=><label className="tg-style-control" key={item.key}>
            <span><b>{item.emoji} {item.label}</b><small>{OPTIONS.find((x)=>x.value===styles[item.key])?.hint}</small></span>
            <select value={styles[item.key]} onChange={(e)=>setStyles((old)=>({...old,[item.key]:e.target.value as Style}))} disabled={loading||saving}>
              {OPTIONS.map((option)=><option value={option.value} key={option.value}>{option.label}</option>)}
            </select>
          </label>)}
        </div>
        <div className="tg-style-preview-wrap">
          <div className="tg-style-preview-title"><span>پیش‌نمایش منوی واقعی</span><small>همان ۱۰ دکمه /start</small></div>
          <div className="tg-style-preview">
            <button type="button" tabIndex={-1} className={`tg-preview-wide ${cls(styles.purchase)}`}>🛒 خرید اشتراک</button>
            <button type="button" tabIndex={-1} className={cls(styles.dashboard)}>🏠 داشبورد</button>
            <button type="button" tabIndex={-1} className={cls(styles.subscriptions)}>📦 اشتراک‌های من</button>
            <button type="button" tabIndex={-1} className={cls(styles.account_link)}>🔗 دریافت لینک اکانت</button>
            <button type="button" tabIndex={-1} className={cls(styles.wallet)}>💰 کیف پول</button>
            <button type="button" tabIndex={-1} className={cls(styles.learning)}>📚 آموزش</button>
            <button type="button" tabIndex={-1} className={cls(styles.download)}>⬇️ دانلود برنامه</button>
            <button type="button" tabIndex={-1} className={`tg-preview-wide ${cls(styles.reseller_request)}`}>🤝 درخواست نمایندگی</button>
            <button type="button" tabIndex={-1} className={cls(styles.support)}>🎫 پشتیبانی</button>
            <button type="button" tabIndex={-1} className={cls(styles.account)}>👤 حساب من</button>
          </div>
          <div className="tg-style-legend"><span className="tg-style-primary">آبی / Primary</span><span className="tg-style-success">سبز / Success</span><span className="tg-style-danger">قرمز / Danger</span><span className="tg-style-default">پیش‌فرض</span></div>
          <p>تنظیمات این بخش مستقیماً روی منوی ۱۰ دکمه‌ای /start اعمال می‌شود. برای دیدن تغییر در Telegram پس از ذخیره، یک منوی جدید باز کنید.</p>
        </div>
      </div>
      {message?<div className={message.includes("ذخیره شد")?"runtime-success":"runtime-error"}>{message}</div>:null}
    </section>
    <style>{`
      .telegram-legacy{gap:12px!important;max-width:1440px;margin-inline:auto}.tg-legacy-hero{padding:16px 18px!important;border-radius:16px!important;grid-template-columns:auto minmax(0,1fr) minmax(220px,280px)!important;gap:14px!important}.tg-legacy-hero-icon{width:50px!important;height:50px!important;border-radius:14px!important;font-size:22px!important}.tg-legacy-hero-copy h1{font-size:24px!important;margin:3px 0 5px!important}.tg-legacy-hero-copy p{line-height:1.7!important}.tg-legacy-hero-side{padding:10px 12px!important;gap:4px!important}.tg-legacy-card{border-radius:16px!important}.tg-section-head{padding:13px 16px 11px!important}.tg-token-panel,.tg-runtime-panel{padding:14px 16px!important}.tg-runtime-row{min-height:48px!important}.tg-action-row{margin-top:10px!important}.tg-customer-menu{padding:12px!important;gap:8px!important}.tg-customer-menu article{padding:10px!important;border-radius:12px!important}.tg-customer-menu article>i{width:32px!important;height:32px!important;flex-basis:32px!important}.tg-runtime-log{min-height:88px!important;max-height:180px!important;margin:12px!important;padding:12px!important}.tg-log-card .tg-runtime-log:empty{display:none}.setting-grid{gap:12px!important}.telegram-membership-settings{margin:0!important}.tg-button-style-card{order:6}.tg-style-head{align-items:center}.tg-style-actions{display:flex;gap:7px;flex-wrap:wrap}.tg-style-actions .btn{min-height:34px;padding:7px 11px;font-size:10px}.tg-style-layout{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(330px,.85fr);gap:14px;padding:14px 16px 16px}.tg-style-controls{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.tg-style-control{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 10px;border:1px solid var(--line);border-radius:12px;background:var(--surface2)}.tg-style-control>span{display:grid;gap:2px;min-width:0}.tg-style-control b{font-size:10px;color:var(--text);white-space:nowrap}.tg-style-control small{font-size:8px;color:var(--muted)}.tg-style-control select{min-width:88px;height:32px;border:1px solid var(--line);border-radius:9px;background:var(--surface);color:var(--text);font-size:9px;font-weight:800;padding-inline:7px}.tg-style-preview-wrap{padding:12px;border:1px solid color-mix(in srgb,var(--purple) 26%,var(--line));border-radius:14px;background:linear-gradient(180deg,color-mix(in srgb,var(--surface2) 94%,var(--purple) 6%),var(--surface2))}.tg-style-preview-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.tg-style-preview-title span{font-size:11px;font-weight:900;color:var(--text)}.tg-style-preview-title small{font-size:8px;color:var(--muted)}.tg-style-preview{direction:rtl;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;padding:10px;border-radius:12px;background:#172433}.tg-style-preview button{min-height:34px;border:0;border-radius:8px;padding:7px 9px;font-size:10px;font-weight:850;cursor:default}.tg-preview-wide{grid-column:1/-1}.tg-style-default{background:#26384a!important;color:#fff!important}.tg-style-primary{background:#2b86c5!important;color:#fff!important}.tg-style-success{background:#4fae4b!important;color:#fff!important}.tg-style-danger{background:#c94c53!important;color:#fff!important}.tg-style-legend{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}.tg-style-legend span{padding:4px 7px;border-radius:7px;font-size:8px;font-weight:800}.tg-style-preview-wrap>p{margin:8px 0 0;color:var(--muted);font-size:8px;line-height:1.7}.tg-button-style-card>.runtime-success,.tg-button-style-card>.runtime-error{margin:0 16px 14px;padding:8px 10px;font-size:9px}.tg-legacy-card textarea{min-height:120px!important}.telegram-legacy>.card{border-radius:16px!important}.telegram-legacy>.card .card-body{padding:14px 16px!important}@media(max-width:1100px){.tg-style-layout{grid-template-columns:1fr}.tg-style-controls{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.tg-legacy-hero{grid-template-columns:1fr!important}.tg-style-controls{grid-template-columns:1fr}.tg-style-head{align-items:flex-start}.tg-style-actions{width:100%}.tg-style-actions .btn{flex:1}.tg-style-layout{padding:12px}.tg-style-preview-wrap{padding:10px}}
    `}</style>
  </>,host);
}
