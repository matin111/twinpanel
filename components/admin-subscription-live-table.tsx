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
  const text=row.textContent||"";
  const match=text.match(/MV-\s*(\d+)/i);
  return match?Number(match[1]):0;
}

function statusCell(row:HTMLTableRowElement){
  // The production table has Status immediately before Actions. We decorate
  // that existing React-owned cell instead of inserting an extra <td>. The old
  // sidecar inserted cells imperatively, which desynchronised React's table DOM
  // after the 15s subscription refresh and caused new rows to lose live state
  // or appear visually misaligned.
  return row.cells.length>=2?row.cells[row.cells.length-2] as HTMLTableCellElement:null;
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

      // Clean up cells/header left behind by pre-v87 builds if a soft navigation
      // kept the old document alive. Fresh v87 renders never create them.
      table.querySelectorAll("[data-live-sub-head]").forEach(node=>node.remove());
      table.querySelectorAll("td[data-live-sub-cell]").forEach(node=>node.remove());

      for(const row of Array.from(table.tBodies?.[0]?.rows||[])){
        const id=rowSubscriptionId(row);
        if(!Number.isFinite(id)||id<=0)continue;
        const cell=statusCell(row);
        if(!cell)continue;

        let host=cell.querySelector<HTMLDivElement>("div[data-live-sub-state]");
        if(!host){
          host=document.createElement("div");
          host.dataset.liveSubState="1";
          host.style.marginTop="6px";
          host.style.display="flex";
          host.style.alignItems="center";
          host.style.gap="5px";
          host.style.flexWrap="wrap";
          cell.appendChild(host);
        }

        const state=states.get(id);
        const online=Boolean(state?.online);
        const protocols=(state?.protocols||[]).map(protocolLabel).filter(Boolean);
        const signature=loaded?`${online?"1":"0"}:${protocols.join(",")}`:"loading";
        if(host.dataset.liveSignature===signature)continue;
        host.dataset.liveSignature=signature;
        host.replaceChildren();

        const badge=document.createElement("span");
        badge.className=`badge ${loaded?(online?"ok":"bad"):"violet"}`;
        badge.textContent=document.documentElement.lang==="en"
          ?loaded?(online?"Online":"Offline"):"Checking…"
          :loaded?(online?"آنلاین":"آفلاین"):"در حال بررسی…";
        badge.title=document.documentElement.lang==="en"?"Connection status":"وضعیت اتصال";
        host.appendChild(badge);

        if(loaded&&online&&protocols.length){
          const detail=document.createElement("small");
          detail.style.opacity=".72";
          detail.dir="ltr";
          detail.textContent=protocols.join(" · ");
          host.appendChild(detail);
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
