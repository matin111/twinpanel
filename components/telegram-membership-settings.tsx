"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card} from "./ui";


type MembershipSettings={
  enabled:boolean;
  chat:string|null;
  join_url:string|null;
};

type Scope="admin"|"reseller";

async function request(scope:Scope,init:RequestInit={}):Promise<MembershipSettings>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body)headers.set("Content-Type","application/json");
  const path=scope==="admin"
    ?"/v1/admin/telegram-bot/membership"
    :"/v1/reseller/bot/membership";
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  let payload:unknown=null;
  try{payload=await response.json();}catch{}
  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload
      ?String((payload as {detail:unknown}).detail)
      :`API error ${response.status}`;
    throw new Error(detail);
  }
  return payload as MembershipSettings;
}

function MembershipCard({scope}:{scope:Scope}){
  const {pick}=useI18n();
  const [enabled,setEnabled]=useState(false);
  const [chat,setChat]=useState("");
  const [joinUrl,setJoinUrl]=useState("");
  const [busy,setBusy]=useState(false);
  const [loaded,setLoaded]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    try{
      const row=await request(scope);
      setEnabled(Boolean(row.enabled));
      setChat(String(row.chat||""));
      setJoinUrl(String(row.join_url||""));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoaded(true);}
  };

  useEffect(()=>{void load();},[scope]);

  const save=async()=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      const row=await request(scope,{
        method:"PATCH",
        body:JSON.stringify({enabled,chat:chat.trim()||null,join_url:joinUrl.trim()||null}),
      });
      setEnabled(Boolean(row.enabled));
      setChat(String(row.chat||""));
      setJoinUrl(String(row.join_url||""));
      setOk(pick("تنظیمات عضویت اجباری ذخیره شد","Mandatory membership settings saved"));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  return <Card>
    <div className="card-head">
      <div>
        <b>{scope==="admin"?pick("عضویت اجباری ربات اصلی","Main bot mandatory membership"):pick("عضویت اجباری ربات نمایندگی","Reseller bot mandatory membership")}</b>
        <small>{pick("کاربر قبل از استفاده از ربات باید عضو کانال تعیین‌شده باشد.","Users must join the configured channel before using the bot.")}</small>
      </div>
      <Badge tone={enabled?"ok":"warn"}>{enabled?pick("فعال","Active"):pick("خاموش","Off")}</Badge>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="setting-grid">
      <label className="toggle module-toggle">
        <span>{pick("فعال‌سازی عضویت اجباری","Enable mandatory membership")}</span>
        <input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)} disabled={!loaded||busy}/><i/>
      </label>
      <label className="field">
        <span>{pick("شناسه کانال","Channel ID / username")}</span>
        <input dir="ltr" value={chat} onChange={e=>setChat(e.target.value)} placeholder="@channel or -1001234567890" disabled={busy}/>
      </label>
      <label className="field">
        <span>{pick("لینک عضویت","Join link")}</span>
        <input dir="ltr" value={joinUrl} onChange={e=>setJoinUrl(e.target.value)} placeholder="https://t.me/channel" disabled={busy}/>
      </label>
    </div>

    <p className="muted">{pick("ربات باید بتواند وضعیت عضویت کاربران این کانال را از Telegram بررسی کند.","The bot must be able to read membership status for this Telegram channel.")}</p>
    <div className="action-row">
      <button className="primary" disabled={busy||!loaded} onClick={()=>void save()}>{busy?pick("در حال ذخیره...","Saving..."):pick("ذخیره تنظیمات","Save settings")}</button>
      <button className="ghost" disabled={busy} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
    </div>
  </Card>;
}

function PortalMembershipSettings({scope,selector}:{scope:Scope;selector:string}){
  const [host,setHost]=useState<HTMLElement|null>(null);
  useEffect(()=>{
    const find=()=>setHost(document.querySelector<HTMLElement>(selector));
    find();
    const timer=window.setTimeout(find,50);
    return()=>window.clearTimeout(timer);
  },[selector]);
  return host?createPortal(<MembershipCard scope={scope}/>,host):null;
}

export function AdminTelegramMembershipSettings(){
  return <PortalMembershipSettings scope="admin" selector=".telegram-legacy"/>;
}

export function ResellerTelegramMembershipSettings(){
  return <PortalMembershipSettings scope="reseller" selector=".reseller-parity-page"/>;
}
