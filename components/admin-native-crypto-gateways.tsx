"use client";

import {useCallback,useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";


type NativeSettings={
  trx_tron_enabled:boolean;
  trx_tron_address:string;
  bnb_bsc_enabled:boolean;
  bnb_bsc_address:string;
};

const empty:NativeSettings={
  trx_tron_enabled:false,
  trx_tron_address:"",
  bnb_bsc_enabled:false,
  bnb_bsc_address:""
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");

  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers,
    cache:"no-store"
  });

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

function Toggle({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}){
  return <label className="payGatewayToggle">
    <span><b>{label}</b></span>
    <input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/>
    <i/>
  </label>;
}

export function AdminNativeCryptoGateways(){
  const {pick}=useI18n();
  const [host,setHost]=useState<Element|null>(null);
  const [settings,setSettings]=useState<NativeSettings>(empty);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const hideRemovedTrc20=useCallback(()=>{
    const grid=document.querySelector(".gatewayGrid");
    if(!grid)return;

    for(const node of Array.from(grid.children)){
      if(node.textContent?.includes("USDT · TRC20")){
        (node as HTMLElement).style.display="none";
        (node as HTMLElement).dataset.removedGateway="usdt-trc20";
      }
    }
  },[]);

  const findHost=useCallback(()=>{
    const grid=document.querySelector(".gatewayGrid");
    setHost(grid);
    hideRemovedTrc20();
  },[hideRemovedTrc20]);

  const load=useCallback(async()=>{
    try{
      const payload=await request<Partial<NativeSettings>>("/v1/payments/admin/native-gateways");
      setSettings({...empty,...payload});
      setError("");
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }
  },[]);

  const save=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      const payload=await request<NativeSettings>(
        "/v1/payments/admin/native-gateways",
        {method:"PUT",body:JSON.stringify(settings)}
      );
      setSettings({...empty,...payload});
      setOk(pick("درگاه‌های TRX و BNB ذخیره شدند.","TRX and BNB gateways saved."));
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      setBusy(false);
    }
  };

  useEffect(()=>{
    findHost();
    const observer=new MutationObserver(findHost);
    observer.observe(document.body,{childList:true,subtree:true});
    return()=>{
      observer.disconnect();
      document.querySelectorAll<HTMLElement>('[data-removed-gateway="usdt-trc20"]').forEach(node=>{
        node.style.display="";
        delete node.dataset.removedGateway;
      });
    };
  },[findHost]);

  useEffect(()=>{void load();},[load]);

  if(!host)return null;

  return createPortal(<>
    <section className={`card gatewayCard ${settings.trx_tron_enabled?"enabled":""}`}>
      <div className="gatewayHead">
        <div className="gatewayIcon">T</div>
        <div><b>TRX · TRON</b><small>TRON Native Coin</small></div>
        <span className={`badge ${settings.trx_tron_enabled?"ok":"bad"}`}>{settings.trx_tron_enabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</span>
      </div>
      <Toggle label={pick("فعال بودن پرداخت TRX","Enable TRX payments")} checked={settings.trx_tron_enabled} onChange={v=>setSettings(s=>({...s,trx_tron_enabled:v}))}/>
      <label className="payField"><span>{pick("آدرس کیف پول TRON","TRON wallet address")}</span><textarea dir="ltr" rows={3} value={settings.trx_tron_address} onChange={e=>setSettings(s=>({...s,trx_tron_address:e.target.value.trim()}))}/></label>
      <small className="muted">{pick("مبلغ هر پلن از نرخ زنده TRX محاسبه و هنگام ساخت پرداخت ثابت می‌شود.","Each plan is converted using the live TRX rate and frozen when the payment is created.")}</small>
    </section>

    <section className={`card gatewayCard ${settings.bnb_bsc_enabled?"enabled":""}`}>
      <div className="gatewayHead">
        <div className="gatewayIcon">B</div>
        <div><b>BNB · BSC</b><small>BNB Smart Chain Native Coin</small></div>
        <span className={`badge ${settings.bnb_bsc_enabled?"ok":"bad"}`}>{settings.bnb_bsc_enabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</span>
      </div>
      <Toggle label={pick("فعال بودن پرداخت BNB","Enable BNB payments")} checked={settings.bnb_bsc_enabled} onChange={v=>setSettings(s=>({...s,bnb_bsc_enabled:v}))}/>
      <label className="payField"><span>{pick("آدرس کیف پول BSC","BSC wallet address")}</span><textarea dir="ltr" rows={3} value={settings.bnb_bsc_address} onChange={e=>setSettings(s=>({...s,bnb_bsc_address:e.target.value.trim()}))}/></label>
      <small className="muted">{pick("مبلغ هر پلن با نرخ زنده BNB تا ۸ رقم اعشار محاسبه و ثابت می‌شود.","Each plan is converted using the live BNB rate, up to 8 decimals, and then frozen.")}</small>
    </section>

    <section className="card gatewayCard nativeGatewaySaveCard">
      <div className="gatewayHead"><div className="gatewayIcon">✓</div><div><b>{pick("درگاه‌های ارز بومی","Native crypto gateways")}</b><small>{pick("USDT-TRC20 حذف شده است؛ فقط USDT-BEP20، TRX و BNB قابل ارائه‌اند.","USDT-TRC20 is removed; only USDT-BEP20, TRX and BNB are offered.")}</small></div></div>
      {error&&<div className="runtime-error">{error}</div>}
      {ok&&<div className="runtime-success">{ok}</div>}
      <button type="button" className="primary" disabled={busy} onClick={()=>void save()}>{busy?"…":pick("ذخیره TRX و BNB","Save TRX & BNB")}</button>
    </section>
  </>,host);
}
