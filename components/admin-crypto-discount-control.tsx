"use client";

import {useCallback,useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";


type DiscountPayload={
  enabled:boolean;
  percent:number;
  max_percent:number;
  applies_to:string[];
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}

  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload
      ?String((payload as {detail:unknown}).detail)
      :`API error ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

export function AdminCryptoDiscountControl(){
  const {pick}=useI18n();
  const [host,setHost]=useState<Element|null>(null);
  const [percent,setPercent]=useState(0);
  const [maxPercent,setMaxPercent]=useState(50);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const findHost=useCallback(()=>{
    setHost(document.querySelector(".gatewayAutomation"));
  },[]);

  const load=useCallback(async()=>{
    try{
      const result=await request<DiscountPayload>("/v1/payments/admin/crypto-discount");
      setPercent(Number(result.percent||0));
      setMaxPercent(Number(result.max_percent||50));
      setError("");
    }catch(e){setError(e instanceof Error?e.message:String(e));}
  },[]);

  useEffect(()=>{
    findHost();
    const observer=new MutationObserver(findHost);
    observer.observe(document.body,{childList:true,subtree:true});
    return()=>observer.disconnect();
  },[findHost]);

  useEffect(()=>{void load();},[load]);

  const save=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      const result=await request<DiscountPayload>("/v1/payments/admin/crypto-discount",{
        method:"PUT",
        body:JSON.stringify({percent:Number(percent||0)})
      });
      setPercent(Number(result.percent||0));
      setMaxPercent(Number(result.max_percent||50));
      setOk(pick("تخفیف خرید با ارز دیجیتال ذخیره شد.","Crypto purchase discount saved."));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  if(!host)return null;

  return createPortal(
    <div className="cryptoDiscountControl">
      <div>
        <b>{pick("تخفیف خرید با ارز دیجیتال","Crypto purchase discount")}</b>
        <small>{pick("فقط خرید پلن با USDT، TRX و BNB؛ شارژ کیف پول شامل این تخفیف نیست.","Applies only to plan purchases paid with USDT, TRX or BNB; wallet top-ups are excluded.")}</small>
      </div>
      <div className="cryptoDiscountInput">
        <input
          type="number"
          min={0}
          max={maxPercent}
          step="0.1"
          value={percent}
          onChange={e=>setPercent(Math.max(0,Math.min(maxPercent,Number(e.target.value)||0)))}
        />
        <span>%</span>
        <button type="button" className="ghost" disabled={busy} onClick={()=>void save()}>{busy?"…":pick("ذخیره تخفیف","Save discount")}</button>
      </div>
      {percent>0&&<p>{pick("مثال: پلن ۱۰۰٬۰۰۰ تومانی با این تخفیف،", "Example: a 100,000 toman plan will cost")}{" "}<strong>{Math.ceil(100000*(100-percent)/100).toLocaleString("fa-IR")} {pick("تومان","toman")}</strong>{" "}{pick("و سپس با نرخ زنده همان ارز تبدیل می‌شود.","before conversion using the frozen live crypto rate.")}</p>}
      {error&&<div className="runtime-error">{error}</div>}
      {ok&&<div className="runtime-success">{ok}</div>}
    </div>,
    host
  );
}
