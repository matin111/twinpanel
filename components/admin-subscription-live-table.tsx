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

function rowSubscriptionId(row:HTMLTableRowElement){
  const planText=row.cells?.[1]?.textContent||row.textContent||"";
  const match=planText.match(/\bMV-(\d+)\b/i);
  return match?Number(match[1]):0;
}

export function AdminSubscriptionLiveTable(){
  useEffect(()=>{
    if(typeof window==="undefined"||window.location.pathname!=="/admin/subscriptions")return;

    let disposed=false;
    let timer:number|undefined;
    let observer:MutationObserver|undefined;
    let loaded=false;
    const states=new Map<number,LiveItem>();

    const decorate=()=>{
      const table=document.querySelector<HTMLTableElement>(".legacy-subscriptions-page .table table");
      if(!table)return;

      const headRow=table.tHead?.rows?.[0];
      if(headRow&&!headRow.querySelector("[data-live-sub-head]")){
        const th=document.createElement("th");
        th.dataset.liveSubHead="1";
        th.textContent=document.documentElement.lang==="en"?"Connection":"اتصال";
        headRow.insertBefore(th,headRow.lastElementChild);
      }

      for(const row of Array.from(table.tBodies?.[0]?.rows||[])){
        const id=rowSubscriptionId(row);
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
        const signature=loaded?`${online?"1":"0"}:${protocols.join(",")}`:"loading";
        if(cell.dataset.liveSignature===signature)continue;
        cell.dataset.liveSignature=signature;
        cell.replaceChildren();

        if(!loaded){
          const pending=document.createElement("span");
          pending.className="badge violet";
          pending.textContent=document.documentElement.lang==="en"?"Checking…":"در حال بررسی…";
          cell.appendChild(pending);
          continue;
        }

        const badge=document.createElement("span");
        badge.className=`badge ${online?"ok":"bad"}`;
        badge.textContent=document.documentElement.lang==="en"?(online?"Online":"Offline"):(online?"آنلاین":"آفلاین");
        cell.appendChild(badge);

        if(online&&protocols.length){
          const detail=document.createElement("small");
          detail.style.display="block";
          detail.style.marginTop="5px";
          detail.style.opacity=".72";
          detail.dir="ltr";
          detail.textContent=protocols.join(" · ");
          cell.appendChild(detail);
        }
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
        loaded=true;
        decorate();
      }catch{}
    };

    decorate();
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
