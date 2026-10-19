"use client";

import {useEffect} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

type LiveItem={subscription_id:number;online:boolean;protocols?:string[];last_seen_at?:string|null};
type LivePayload={items?:LiveItem[]};

const protocolLabel=(value:string)=>({
  cisco:"Cisco",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP",
  xray:"Xray",
  v2ray:"Xray",
} as Record<string,string>)[String(value||"").toLowerCase()]||value;

export function AdminSubscriptionLiveTable(){
  useEffect(()=>{
    if(typeof window==="undefined"||window.location.pathname!=="/admin/subscriptions")return;

    let disposed=false;
    let timer:number|undefined;
    let observer:MutationObserver|undefined;
    const states=new Map<number,LiveItem>();

    const decorate=()=>{
      const table=document.querySelector<HTMLTableElement>(".admin-runtime-list .table table");
      if(!table)return;

      const headRow=table.tHead?.rows?.[0];
      if(headRow&&!headRow.querySelector("[data-live-sub-head]")){
        const th=document.createElement("th");
        th.dataset.liveSubHead="1";
        th.textContent=document.documentElement.lang==="en"?"Connection":"اتصال";
        headRow.insertBefore(th,headRow.lastElementChild);
      }

      for(const row of Array.from(table.tBodies?.[0]?.rows||[])){
        const idText=row.cells?.[0]?.textContent?.trim()||"";
        const id=Number(idText.replace(/[^0-9]/g,""));
        if(!Number.isFinite(id)||id<=0)continue;

        let cell=row.querySelector<HTMLTableCellElement>("td[data-live-sub-cell]");
        if(!cell){
          cell=document.createElement("td");
          cell.dataset.liveSubCell="1";
          row.insertBefore(cell,row.lastElementChild);
        }

        const state=states.get(id);
        const online=Boolean(state?.online);
        const protocols=(state?.protocols||[]).map(protocolLabel).filter(Boolean);
        cell.innerHTML=`<span class="badge ${online?"ok":"bad"}">${online?"آنلاین":"آفلاین"}</span>${online&&protocols.length?`<small style="display:block;margin-top:5px;opacity:.72" dir="ltr">${protocols.join(" · ")}</small>`:""}`;
      }
    };

    const refresh=async()=>{
      const token=getCustomerToken();
      if(!token||disposed)return;
      try{
        const response=await fetch(`${API_BASE}/v1/admin/subscriptions/live-status?ts=${Date.now()}`,{
          cache:"no-store",
          headers:{Authorization:`Bearer ${token}`,Accept:"application/json"},
        });
        if(!response.ok)return;
        const payload=await response.json() as LivePayload;
        states.clear();
        for(const item of payload.items||[])states.set(Number(item.subscription_id),item);
        decorate();
      }catch{}
    };

    observer=new MutationObserver(decorate);
    observer.observe(document.body,{childList:true,subtree:true});
    void refresh();
    timer=window.setInterval(refresh,3000);
    document.addEventListener("visibilitychange",refresh);

    return()=>{
      disposed=true;
      if(timer)window.clearInterval(timer);
      observer?.disconnect();
      document.removeEventListener("visibilitychange",refresh);
    };
  },[]);

  return null;
}
