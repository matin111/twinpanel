"use client";

import {FormEvent,useCallback,useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";


type WalletRow={
  user_id:number;
  balance_toman:number;
};

type HostRow={
  userId:number;
  host:HTMLElement;
};

async function adminRequest<T>(path:string,init:RequestInit={}):Promise<T>{
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

const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;

export function AdminUsersWalletInline(){
  const {pick}=useI18n();
  const [hosts,setHosts]=useState<HostRow[]>([]);
  const [balances,setBalances]=useState<Record<number,number>>({});
  const [userId,setUserId]=useState<number|null>(null);
  const [amount,setAmount]=useState("");
  const [note,setNote]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const loadBalances=useCallback(async()=>{
    try{
      const rows=await adminRequest<WalletRow[]>("/v1/admin/wallet/wallets");
      const map:Record<number,number>={};
      for(const row of Array.isArray(rows)?rows:[])map[Number(row.user_id)]=Number(row.balance_toman||0);
      setBalances(map);
    }catch{/* users page must remain usable even if wallet endpoint is unavailable */}
  },[]);

  const scan=useCallback(()=>{
    const found:HostRow[]=[];
    const rows=document.querySelectorAll<HTMLElement>(".legacy-users-page tbody tr");

    rows.forEach(row=>{
      const first=row.querySelector<HTMLElement>("td:first-child");
      const actions=row.querySelector<HTMLElement>(".row-actions");
      if(!first||!actions)return;

      const match=(first.textContent||"").match(/#\s*(\d+)/);
      if(!match)return;

      const id=Number(match[1]);
      if(!Number.isFinite(id)||id<=0)return;

      let host=actions.querySelector<HTMLElement>(`.admin-user-wallet-slot[data-user-id="${id}"]`);
      if(!host){
        host=document.createElement("span");
        host.className="admin-user-wallet-slot";
        host.dataset.userId=String(id);
        actions.prepend(host);
      }

      found.push({userId:id,host});
    });

    setHosts(previous=>{
      if(previous.length===found.length&&previous.every((item,index)=>item.userId===found[index]?.userId&&item.host===found[index]?.host))return previous;
      return found;
    });
  },[]);

  useEffect(()=>{
    void loadBalances();
    scan();
    const observer=new MutationObserver(scan);
    observer.observe(document.body,{childList:true,subtree:true});
    return()=>observer.disconnect();
  },[loadBalances,scan]);

  const currentBalance=useMemo(()=>userId?Number(balances[userId]||0):0,[balances,userId]);

  const open=(id:number)=>{
    setUserId(id);
    setAmount("");
    setNote("");
    setError("");
    setOk("");
  };

  const close=()=>{
    if(busy)return;
    setUserId(null);
    setAmount("");
    setNote("");
    setError("");
    setOk("");
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(!userId||busy)return;

    const value=Number(amount.replace(/[^0-9-]/g,""));
    if(!Number.isFinite(value)||value===0){
      setError(pick("مبلغ تغییر نمی‌تواند صفر باشد.","Adjustment amount cannot be zero."));
      return;
    }

    setBusy(true);setError("");setOk("");
    try{
      const result=await adminRequest<{balance_toman:number}>(`/v1/admin/wallet/wallets/${userId}/adjust`,{
        method:"POST",
        body:JSON.stringify({
          amount_toman:value,
          note:note.trim()||"اصلاح دستی موجودی"
        })
      });
      setBalances(current=>({...current,[userId]:Number(result.balance_toman||0)}));
      setOk(pick("موجودی کاربر بروزرسانی شد.","User balance updated."));
      setAmount("");setNote("");
      await loadBalances();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  return <>
    {hosts.map(({userId:id,host})=>createPortal(
      <button
        type="button"
        className="ghost"
        onClick={()=>open(id)}
        title={pick("افزایش یا کاهش دستی موجودی","Manually adjust wallet balance")}
      >
        {pick("موجودی","Balance")}: {money(Number(balances[id]||0))}
      </button>,
      host,
      `wallet-${id}`
    ))}

    {userId&&createPortal(
      <div className="runtime-modal" role="dialog" aria-modal="true">
        <button type="button" className="runtime-modal-bg" onClick={close}/>
        <form className="runtime-modal-card" onSubmit={submit}>
          <div className="card-head">
            <div>
              <b>{pick("اصلاح موجودی کاربر","Adjust user balance")} #{userId}</b>
              <small>{pick("موجودی فعلی","Current balance")}: {money(currentBalance)}</small>
            </div>
            <button type="button" className="icon-button" onClick={close}>×</button>
          </div>

          {error&&<div className="runtime-error">{error}</div>}
          {ok&&<div className="runtime-success">{ok}</div>}

          <label className="payField">
            <span>{pick("مبلغ تغییر","Adjustment amount")}</span>
            <div className="inputSuffix">
              <input
                dir="ltr"
                inputMode="numeric"
                value={amount}
                onChange={e=>setAmount(e.target.value.replace(/[^0-9-]/g,""))}
                placeholder="100000 یا -50000"
                required
              />
              <em>{pick("تومان","toman")}</em>
            </div>
          </label>

          <label className="payField">
            <span>{pick("توضیح (اختیاری)","Note (optional)")}</span>
            <textarea
              rows={3}
              value={note}
              onChange={e=>setNote(e.target.value)}
              placeholder={pick("مثلاً شارژ هدیه یا اصلاح حساب؛ اختیاری","e.g. bonus credit or balance correction; optional")}
            />
          </label>

          <div className="runtime-modal-actions">
            <button type="button" className="ghost" onClick={close}>{pick("بستن","Close")}</button>
            <button className="primary" disabled={busy}>{busy?"…":pick("ثبت تغییر موجودی","Apply balance change")}</button>
          </div>
        </form>
      </div>,
      document.body
    )}
  </>;
}
