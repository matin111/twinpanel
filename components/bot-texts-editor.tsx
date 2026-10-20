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
  label_fa:string;
  label_en:string;
  help_fa:string;
  help_en:string;
  max_length:number;
  default_text:string;
  custom_text:string|null;
  effective_text:string;
  is_custom:boolean;
};
type Catalog={scope:Scope;reseller_id?:number|null;items:TextItem[]};


async function botTextRequest<T>(scope:Scope,path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const prefix=scope==="admin"?"/v1/admin/telegram-bot/texts":"/v1/reseller/bot/texts";
  const response=await fetch(`${API_BASE}${prefix}${path}`,{...init,headers,cache:"no-store"});
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
    for(const item of data.items)next[item.key]=item.custom_text??"";
    setValues(next);
  };

  const load=async()=>{
    setError("");
    try{hydrate(await botTextRequest<Catalog>(scope,""));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  useEffect(()=>{void load();},[scope]);

  const changed=useMemo(()=>{
    if(!catalog)return false;
    return catalog.items.some(item=>(values[item.key]??"")!==(item.custom_text??""));
  },[catalog,values]);

  const save=async()=>{
    if(busy)return;
    setBusy("save");setError("");setOk("");
    try{
      const data=await botTextRequest<Catalog>(scope,"",{
        method:"PUT",
        body:JSON.stringify({texts:values}),
      });
      hydrate(data);
      setOk(pick("متن‌های ربات ذخیره شد.","Bot texts saved."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const reset=async(keys:string[]|null)=>{
    if(busy)return;
    const all=keys===null;
    if(!window.confirm(all?pick("همه متن‌ها به پیش‌فرض برگردند؟","Reset all bot texts to defaults?"):pick("این متن به پیش‌فرض برگردد؟","Reset this text to default?")))return;
    setBusy(all?"reset-all":`reset:${keys?.[0]||""}`);setError("");setOk("");
    try{
      const data=await botTextRequest<Catalog>(scope,"/reset",{
        method:"POST",
        body:JSON.stringify({keys}),
      });
      hydrate(data);
      setOk(pick("متن پیش‌فرض بازیابی شد.","Default text restored."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  return <div className="page">
    <div className="page-head">
      <div>
        <h1>{pick("متن‌های ربات","Bot Texts")}</h1>
        <small>{pick(
          "متن‌های ثابت را تغییر دهید؛ مبلغ، شماره سفارش، کارت، لینک اتصال و منطق خرید/پرداخت خودکار باقی می‌مانند.",
          "Edit static copy only; amounts, order IDs, payment details, connection links and purchase/payment logic remain automatic."
        )}</small>
      </div>
      <div className="action-row">
        <button className="ghost" type="button" disabled={Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
        <button className="ghost danger" type="button" disabled={Boolean(busy)||!catalog?.items.some(item=>item.is_custom)} onClick={()=>void reset(null)}>{pick("بازگردانی همه","Reset all")}</button>
        <button className="primary" type="button" disabled={Boolean(busy)||!changed} onClick={()=>void save()}>{busy==="save"?pick("در حال ذخیره...","Saving..."):pick("ذخیره تغییرات","Save changes")}</button>
      </div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
    {!catalog&&!error&&<div className="runtime-loading">{pick("در حال دریافت متن‌های ربات...","Loading bot texts...")}</div>}

    {catalog&&<div className="module-grid two">
      {catalog.items.map(item=>{
        const value=values[item.key]??"";
        const preview=value.trim()||item.default_text;
        return <Card key={item.key}>
          <div className="card-head">
            <div><b>{pick(item.label_fa,item.label_en)}</b><small>{pick(item.help_fa,item.help_en)}</small></div>
            <Badge tone={value.trim()?"violet":"ok"}>{value.trim()?pick("سفارشی","Custom"):pick("پیش‌فرض","Default")}</Badge>
          </div>
          <label className="field">
            <span>{pick("متن سفارشی","Custom text")}</span>
            <textarea
              rows={item.key==="welcome"?9:4}
              maxLength={item.max_length}
              value={value}
              onChange={event=>setValues(current=>({...current,[item.key]:event.target.value}))}
              placeholder={item.default_text}
            />
            <small dir="ltr">{value.length.toLocaleString("en-US")} / {item.max_length.toLocaleString("en-US")}</small>
          </label>
          <div className="runtime-choice-section">
            <b>{pick("پیش‌نمایش متن مؤثر","Effective preview")}</b>
            <pre className="runtime-log">{preview}</pre>
          </div>
          <div className="action-row">
            <button className="ghost" type="button" disabled={Boolean(busy)||(!item.is_custom&&!value.trim())} onClick={()=>void reset([item.key])}>{busy===`reset:${item.key}`?pick("در حال بازگردانی...","Resetting..."):pick("بازگردانی پیش‌فرض","Reset default")}</button>
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
