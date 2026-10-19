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

function unreadNotificationCount(payload:NotificationPayload):number{
  if(Number.isFinite(Number(payload.unread_count))){
    return Math.max(0,Number(payload.unread_count)||0);
  }
  if(!Array.isArray(payload.items))return 0;
  return payload.items.filter(value=>{
    if(!value||typeof value!=="object")return false;
    const row=value as Row;
    return !Boolean(row.is_read)&&!row.read_at;
  }).length;
}

function setCount(target:Record<string,number>,route:string,count:number){
  if(count>0)target[route]=count;
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

      const topups=results[0].status==="fulfilled"&&Array.isArray(results[0].value)?results[0].value:[];
      setCount(
        routeCounts,
        "/reseller/bot-wallet",
        topups.filter(row=>String(row.status||"").toLowerCase()==="awaiting_review").length,
      );

      const orders=results[1].status==="fulfilled"&&Array.isArray(results[1].value)?results[1].value:[];
      setCount(
        routeCounts,
        "/reseller/orders",
        orders.filter(row=>ACTIONABLE_ORDER_STATUSES.has(String(row.status||"").toLowerCase())).length,
      );

      const unreadCount=results[2].status==="fulfilled"
        ?unreadNotificationCount(results[2].value||{})
        :0;
      setCount(routeCounts,"/reseller/notifications",unreadCount);

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
