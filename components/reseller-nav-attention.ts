"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

type Row=Record<string,unknown>;
type NotificationPayload={unread_count?:number;items?:unknown};
type AttentionState={
  routeCounts:Record<string,number>;
  unreadCount:number;
};

const ACTIONABLE_ORDER_STATUSES=new Set([
  "awaiting_review",
  "review",
  "submitted",
]);

async function request<T>(path:string):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}${path}`,{
    headers:{Authorization:`Bearer ${token}`},
    cache:"no-store",
    signal:AbortSignal.timeout(5000),
  });
  if(!response.ok)throw new Error(`API ${response.status}`);
  return response.json() as Promise<T>;
}

function normalizeRoute(raw:unknown):string|null{
  const value=String(raw||"").trim();
  if(!value)return null;
  if(value==="/reseller"||value.startsWith("/reseller/"))return value;
  const clean=value.replace(/^\/+/,"").replace(/^reseller\//,"");
  return clean?`/reseller/${clean}`:null;
}

function unreadNotificationRows(payload:NotificationPayload):Row[]{
  if(!Array.isArray(payload.items))return [];
  return payload.items.filter((value):value is Row=>{
    if(!value||typeof value!=="object")return false;
    const row=value as Row;
    return !Boolean(row.is_read)&&!row.read_at;
  });
}

function addCount(target:Record<string,number>,route:string,count=1){
  if(count<=0)return;
  target[route]=(target[route]||0)+count;
}

function ensureCount(target:Record<string,number>,route:string,count=1){
  if(count<=0)return;
  target[route]=Math.max(target[route]||0,count);
}

export function useResellerNavAttention(enabled:boolean){
  const [state,setState]=useState<AttentionState>({routeCounts:{},unreadCount:0});

  useEffect(()=>{
    if(!enabled){
      setState({routeCounts:{},unreadCount:0});
      return;
    }

    let alive=true;

    const refresh=async()=>{
      const results=await Promise.allSettled([
        request<Row[]>("/v1/reseller/bot-commerce/wallet-topups"),
        request<Row[]>("/v1/reseller/bot-commerce/orders"),
        request<NotificationPayload>("/v1/reseller/notifications"),
      ]);
      if(!alive)return;

      const routeCounts:Record<string,number>={};
      let unreadCount=0;

      const topups=results[0].status==="fulfilled"&&Array.isArray(results[0].value)?results[0].value:[];
      addCount(
        routeCounts,
        "/reseller/bot-wallet",
        topups.filter(row=>String(row.status||"").toLowerCase()==="awaiting_review").length,
      );

      const orders=results[1].status==="fulfilled"&&Array.isArray(results[1].value)?results[1].value:[];
      addCount(
        routeCounts,
        "/reseller/orders",
        orders.filter(row=>ACTIONABLE_ORDER_STATUSES.has(String(row.status||"").toLowerCase())).length,
      );

      if(results[2].status==="fulfilled"){
        const payload=results[2].value||{};
        const unreadRows=unreadNotificationRows(payload);
        unreadCount=Number.isFinite(Number(payload.unread_count))
          ?Math.max(0,Number(payload.unread_count)||0)
          :unreadRows.length;
        for(const row of unreadRows){
          const route=normalizeRoute(row.route);
          if(route)ensureCount(routeCounts,route);
        }
        ensureCount(routeCounts,"/reseller/notifications",unreadCount);
      }

      setState({routeCounts,unreadCount});
    };

    const refreshVisible=()=>{
      if(document.visibilityState==="visible")void refresh();
    };

    void refresh();
    const timer=window.setInterval(refreshVisible,4000);
    window.addEventListener("focus",refreshVisible);
    document.addEventListener("visibilitychange",refreshVisible);

    return()=>{
      alive=false;
      window.clearInterval(timer);
      window.removeEventListener("focus",refreshVisible);
      document.removeEventListener("visibilitychange",refreshVisible);
    };
  },[enabled]);

  const countMap=useMemo(()=>new Map(Object.entries(state.routeCounts)),[state.routeCounts]);
  const countForPath=(href:string)=>Math.max(0,Number(countMap.get(href))||0);
  const hasPathAttention=(href:string)=>countForPath(href)>0;
  const groupHasAttention=(paths:readonly string[])=>paths.some(path=>hasPathAttention(path));

  return {...state,countForPath,hasPathAttention,groupHasAttention};
}
