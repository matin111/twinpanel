"use client";

import {useCallback,useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";


type RateRow={
  symbol:string;
  rate_toman:number;
  provider?:string|null;
  updated_at?:string|null;
  error?:string|null;
};

type AutomationState={
  auto_rate_enabled:boolean;
  crypto_auto_verify:boolean;
  sms_reader_enabled:boolean;
  sms_auto_verify:boolean;
  sms_allowed_senders?:string|null;
  active_reader_count:number;
  card_auto_verify_operational:boolean;
  usdt_bep20_ready:boolean;
  trx_tron_ready:boolean;
  bnb_bsc_ready:boolean;
};

type MarketPayload={
  ok:boolean;
  updated?:boolean;
  updated_at?:string|null;
  rates:Record<string,RateRow>;
  automation:AutomationState;
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);

  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers,
    cache:"no-store"
  });

  const raw=await response.text();
  let payload:unknown=null;

  if(raw){
    try{payload=JSON.parse(raw);}catch{payload=raw;}
  }

  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload
      ?String((payload as {detail:unknown}).detail)
      :`API error ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

const toman=(value:number)=>value>0?`${value.toLocaleString("fa-IR")} تومان`:"—";
const when=(value?:string|null)=>value?new Date(value).toLocaleString("fa-IR"):"—";

export function AdminPaymentMarketRates(){
  const {pick}=useI18n();
  const [host,setHost]=useState<Element|null>(null);
  const [data,setData]=useState<MarketPayload|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);

  const findHost=useCallback(()=>{
    setHost(document.querySelector(".gatewayAutomation"));
  },[]);

  const load=useCallback(async()=>{
    try{
      const payload=await request<MarketPayload>("/v1/payments/admin/market-rates");
      setData(payload);
      setError("");
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }
  },[]);

  const refresh=async()=>{
    if(busy)return;
    setBusy(true);
    try{
      const payload=await request<MarketPayload>(
        "/v1/payments/admin/market-rates/refresh",
        {method:"POST"}
      );
      setData(payload);
      setError("");
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      setBusy(false);
    }
  };

  const activate=async()=>{
    if(busy)return;
    setBusy(true);
    try{
      await request(
        "/v1/payments/admin/automation/activate",
        {method:"POST"}
      );
      await load();
      setError("");
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

    return()=>observer.disconnect();
  },[findHost]);

  useEffect(()=>{
    void load();
    const timer=window.setInterval(()=>void load(),10000);
    return()=>window.clearInterval(timer);
  },[load]);

  if(!host)return null;

  const automation=data?.automation;
  const rates=["USDT","TRX","BNB"].map(symbol=>data?.rates?.[symbol]??{
    symbol,rate_toman:0,provider:null,updated_at:null,error:null
  });

  const cryptoReady=Boolean(
    automation?.usdt_bep20_ready||automation?.trx_tron_ready||automation?.bnb_bsc_ready
  );

  return createPortal(
    <div className="paymentMarketV2">
      <div className="paymentMarketHead">
        <div>
          <b>{pick("قیمت لحظه‌ای ارزها","Live market rates")}</b>
          <small>{pick("نرخ‌های USDT، TRX و BNB برای تبدیل دقیق مبلغ پلن","USDT, TRX and BNB rates for exact plan conversion")}</small>
        </div>
        <button type="button" className="ghost" disabled={busy} onClick={()=>void refresh()}>
          {busy?"…":pick("بروزرسانی نرخ‌ها","Refresh rates")}
        </button>
      </div>

      <div className="paymentMarketGrid">
        {rates.map(row=><div className={`paymentMarketRate ${row.rate_toman>0?"live":"failed"}`} key={row.symbol}>
          <div><strong>{row.symbol}</strong><span>{row.rate_toman>0?pick("زنده","Live"):pick("ناموجود","Unavailable")}</span></div>
          <b>{toman(Number(row.rate_toman||0))}</b>
          <small title={row.error||undefined}>{row.provider||row.error||pick("در انتظار دریافت نرخ","Waiting for rate")}</small>
          <em>{when(row.updated_at)}</em>
        </div>)}
      </div>

      {error&&<div className="paymentMarketError">{error}</div>}

      <div className="paymentAutomationState">
        <div className={automation?.crypto_auto_verify&&cryptoReady?"ready":"waiting"}>
          <span>{pick("تأیید خودکار ارز دیجیتال","Crypto auto verification")}</span>
          <b>{automation?.crypto_auto_verify?pick("فعال","Active"):pick("غیرفعال","Inactive")}</b>
          <small>
            USDT-BEP20: {automation?.usdt_bep20_ready?pick("آماده","Ready"):pick("نیاز به درگاه و کیف پول","Needs gateway + wallet")}
            {" · "}
            TRX-TRON: {automation?.trx_tron_ready?pick("آماده","Ready"):pick("نیاز به درگاه و کیف پول","Needs gateway + wallet")}
            {" · "}
            BNB-BSC: {automation?.bnb_bsc_ready?pick("آماده","Ready"):pick("نیاز به درگاه و کیف پول","Needs gateway + wallet")}
          </small>
        </div>

        <div className={automation?.card_auto_verify_operational?"ready":"waiting"}>
          <span>{pick("تأیید خودکار کارت‌به‌کارت","Card auto verification")}</span>
          <b>{automation?.card_auto_verify_operational?pick("عملیاتی","Operational"):pick("منتظر اتصال Reader","Waiting for Reader")}</b>
          <small>
            {pick("دستگاه متصل","Connected reader")}: {Number(automation?.active_reader_count||0).toLocaleString("fa-IR")}
            {automation?.sms_allowed_senders?` · ${automation.sms_allowed_senders}`:""}
          </small>
        </div>
      </div>

      {automation&&(!automation.auto_rate_enabled||!automation.crypto_auto_verify||!automation.sms_reader_enabled||!automation.sms_auto_verify)&&
        <button type="button" className="primary paymentAutomationActivate" disabled={busy} onClick={()=>void activate()}>
          {pick("فعال‌سازی کامل تأیید و نرخ خودکار","Enable all payment automation")}
        </button>
      }
    </div>,
    host
  );
}
