"use client";

import {useEffect,useMemo,useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {PortalShell} from "./portal-shells";
import {Badge,Card,Shell} from "./ui";


type Scope="admin"|"reseller";
type TextItem={
  key:string;
  title_fa:string;
  title_en:string;
  default:string;
  override:string|null;
  value:string;
  is_overridden:boolean;
  max_length:number;
};
type Catalog={scope:Scope;reseller_id?:number|null;items:TextItem[]};

type CopyHelp={fa:string;en:string};
const COPY_HELP:Record<string,CopyHelp>={
  welcome:{fa:"متن شروع ربات. نام کاربر/برند و وضعیت ساخت خودکار حساب همچنان توسط ربات مدیریت می‌شود.",en:"Bot start copy. Dynamic customer/brand and account-creation state remain automatic."},
  purchase_intro:{fa:"متن بالای فهرست پلن‌ها؛ خود پلن‌ها، قیمت‌ها و دکمه‌ها خودکار می‌مانند.",en:"Copy above the plan list; plans, prices and buttons remain automatic."},
  payment_instructions:{fa:"راهنمای انتخاب روش پرداخت؛ اطلاعات کارت، کیف پول و مبلغ از تنظیمات واقعی می‌آید.",en:"Payment-method prompt; card/wallet details and amounts remain dynamic."},
  receipt_prompt:{fa:"متن درخواست رسید. جریان Receipt-Only کارت و ثبت فایل پرداخت تغییر نمی‌کند.",en:"Receipt prompt. Card receipt-only behavior and proof storage remain unchanged."},
  pending_review:{fa:"پیام بعد از ثبت رسید/پرداخت؛ فقط متن وضعیت قابل تغییر است.",en:"Message after proof submission; only the review-status copy changes."},
  purchase_success:{fa:"عنوان پیام موفقیت؛ نام کاربری، مبلغ و لینک اتصال همچنان خودکار ساخته می‌شوند.",en:"Success copy; username, amount and connection link remain automatic."},
  payment_rejected:{fa:"متن رد پرداخت؛ دلیل رد واقعی همچنان از رکورد پرداخت نمایش داده می‌شود.",en:"Rejected-payment copy; the real rejection reason remains automatic."},
  renewal_intro:{fa:"عنوان بخش تمدید؛ پلن، حجم، روز و مبلغ خودکار باقی می‌مانند.",en:"Renewal heading; plan, traffic, duration and amount remain automatic."},
  support_intro:{fa:"عنوان پیام پشتیبانی؛ مسیر و دکمه‌های پشتیبانی تغییر نمی‌کنند.",en:"Support heading; support routing and buttons remain unchanged."},
};


function endpoint(scope:Scope){
  return scope==="admin"?"/v1/settings/general/bot-texts":"/v1/reseller/bot/texts";
}

async function authRequest<T>(path:string,init:RequestInit={}):Promise<T>{
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

async function restartMainBotIfRunning(){
  try{
    const status=await authRequest<{installed?:boolean;service_state?:string}>("/v1/admin/telegram-bot");
    const state=String(status.service_state||"").toLowerCase();
    if(status.installed&&["active","running"].includes(state)){
      await authRequest("/v1/admin/telegram-bot/restart",{method:"POST"});
    }
  }catch{
    // Text settings are already durable. Runtime control remains available on
    // the Telegram page if the service is temporarily unavailable.
  }
}


function BotTextsContent({scope}:{scope:Scope}){
  const {pick}=useI18n();
  const [catalog,setCatalog]=useState<Catalog|null>(null);
  const [values,setValues]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const hydrate=(data:Catalog)=>{
    setCatalog(data);
    const next:Record<string,string>={};
    for(const item of data.items)next[item.key]=item.override??"";
    setValues(next);
  };

  const load=async()=>{
    setError("");
    try{hydrate(await authRequest<Catalog>(endpoint(scope)));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  useEffect(()=>{void load();},[scope]);

  const changed=useMemo(()=>{
    if(!catalog)return false;
    return catalog.items.some(item=>(values[item.key]??"")!==(item.override??""));
  },[catalog,values]);

  const applyMutationResult=async(data:Catalog)=>{
    hydrate(data);
    if(scope==="admin")await restartMainBotIfRunning();
  };

  const save=async()=>{
    if(busy)return;
    setBusy("save");setError("");setOk("");
    try{
      const data=await authRequest<Catalog>(endpoint(scope),{
        method:"PUT",
        body:JSON.stringify({texts:values}),
      });
      await applyMutationResult(data);
      setOk(pick("متن‌های ربات ذخیره شد.","Bot texts saved."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const resetOne=async(key:string)=>{
    if(busy)return;
    if(!window.confirm(pick("این متن به پیش‌فرض برگردد؟","Reset this text to default?")))return;
    setBusy(`reset:${key}`);setError("");setOk("");
    try{
      const data=await authRequest<Catalog>(endpoint(scope),{
        method:"PUT",
        body:JSON.stringify({texts:{[key]:null}}),
      });
      await applyMutationResult(data);
      setOk(pick("متن پیش‌فرض بازیابی شد.","Default text restored."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const resetAll=async()=>{
    if(busy)return;
    if(!window.confirm(pick("همه متن‌ها به پیش‌فرض برگردند؟","Reset all bot texts to defaults?")))return;
    setBusy("reset-all");setError("");setOk("");
    try{
      const data=await authRequest<Catalog>(endpoint(scope),{method:"DELETE"});
      await applyMutationResult(data);
      setOk(pick("همه متن‌های پیش‌فرض بازیابی شد.","All default texts restored."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  return <div className="page">
    <div className="page-head">
      <div>
        <h1>{pick("متن‌های ربات","Bot Texts")}</h1>
        <small>{pick(
          "فقط متن‌های ثابت تغییر می‌کنند؛ مبلغ، شماره سفارش، اطلاعات پرداخت، لینک اتصال و منطق خرید/رسید خودکار باقی می‌مانند.",
          "Only static copy changes; amounts, order IDs, payment details, connection links and purchase/receipt logic remain automatic."
        )}</small>
      </div>
      <div className="action-row">
        <button className="ghost" type="button" disabled={Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
        <button className="ghost danger" type="button" disabled={Boolean(busy)||!catalog?.items.some(item=>item.is_overridden)} onClick={()=>void resetAll()}>{pick("بازگردانی همه","Reset all")}</button>
        <button className="primary" type="button" disabled={Boolean(busy)||!changed} onClick={()=>void save()}>{busy==="save"?pick("در حال ذخیره...","Saving..."):pick("ذخیره تغییرات","Save changes")}</button>
      </div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
    {!catalog&&!error&&<div className="runtime-loading">{pick("در حال دریافت متن‌های ربات...","Loading bot texts...")}</div>}

    {catalog&&<div className="module-grid two">
      {catalog.items.map(item=>{
        const custom=values[item.key]??"";
        const preview=custom.trim()||item.default||pick("متن فعلی داخلی ربات استفاده می‌شود.","The bot's built-in text is used.");
        const help=COPY_HELP[item.key]||{fa:"متن ثابت این بخش قابل ویرایش است.",en:"The static copy for this section is editable."};
        return <Card key={item.key}>
          <div className="card-head">
            <div><b>{pick(item.title_fa,item.title_en)}</b><small>{pick(help.fa,help.en)}</small></div>
            <Badge tone={custom.trim()?"violet":"ok"}>{custom.trim()?pick("سفارشی","Custom"):pick("پیش‌فرض","Default")}</Badge>
          </div>
          <label className="field">
            <span>{pick("متن سفارشی","Custom text")}</span>
            <textarea
              rows={item.key==="welcome"?9:4}
              maxLength={item.max_length}
              value={custom}
              onChange={event=>setValues(current=>({...current,[item.key]:event.target.value}))}
              placeholder={item.default||pick("برای استفاده از متن فعلی ربات خالی بگذارید.","Leave empty to use the current built-in bot text.")}
            />
            <small dir="ltr">{custom.length.toLocaleString("en-US")} / {item.max_length.toLocaleString("en-US")}</small>
          </label>
          <div className="runtime-choice-section">
            <b>{pick("پیش‌نمایش متن مؤثر","Effective preview")}</b>
            <pre className="runtime-log">{preview}</pre>
          </div>
          <div className="action-row">
            <button className="ghost" type="button" disabled={Boolean(busy)||(!item.is_overridden&&!custom.trim())} onClick={()=>void resetOne(item.key)}>{busy===`reset:${item.key}`?pick("در حال بازگردانی...","Resetting..."):pick("بازگردانی پیش‌فرض","Reset default")}</button>
          </div>
        </Card>;
      })}
    </div>}
  </div>;
}


export function AdminBotTextsEditor(){
  return <Shell active="/admin/bot-texts"><BotTextsContent scope="admin"/></Shell>;
}


export function ResellerBotTextsEditor(){
  return <PortalShell type="reseller" active="/reseller/bot-texts"><BotTextsContent scope="reseller"/></PortalShell>;
}
