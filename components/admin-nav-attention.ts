"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

type NotificationItem={
  route?:string|null;
  read_at?:string|null;
  is_read?:boolean;
};

type NotificationPayload={
  unread_count?:number;
  items?:unknown;
};

type SupportTicket={
  id?:number;
  status?:string|null;
};

type PaymentReviewSummary={needs_review?:number};
type ReleaseStatus={update_available?:boolean};

type AttentionState={
  paymentReviewCount:number;
  supportNeedsReplyCount:number;
  notificationUnreadCount:number;
  unreadRoutes:string[];
  updateAvailable:boolean;
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers,
    cache:"no-store",
    signal:init.signal??AbortSignal.timeout(5000),
  });
  if(!response.ok)throw new Error(`API ${response.status}`);
  return response.json() as Promise<T>;
}

function normalizeRoute(raw:unknown):string|null{
  const value=String(raw||"").trim();
  if(!value)return null;
  if(value.startsWith("/"))return value;
  return `/admin/${value.replace(/^admin\//,"")}`;
}

export function useAdminNavAttention(_active:string){
  const [state,setState]=useState<AttentionState>({
    paymentReviewCount:0,
    supportNeedsReplyCount:0,
    notificationUnreadCount:0,
    unreadRoutes:[],
    updateAvailable:false,
  });

  useEffect(()=>{
    let alive=true;

    const refreshSupport=async()=>{
      try{
        const rows=await request<SupportTicket[]>("/v1/admin/support/tickets?status=open");
        if(!alive)return;
        const count=Array.isArray(rows)
          ?rows.filter(row=>String(row?.status||"").toLowerCase()==="open").length
          :0;
        setState(current=>({...current,supportNeedsReplyCount:count}));
      }catch{}
    };

    const refreshPayments=async()=>{
      try{
        const summary=await request<PaymentReviewSummary>("/v1/admin/wallet/payment-review-summary");
        if(!alive)return;
        setState(current=>({...current,paymentReviewCount:Math.max(0,Number(summary.needs_review)||0)}));
      }catch{}
    };

    const refreshNotifications=async()=>{
      try{
        const payload=await request<NotificationPayload>("/v1/admin/panel-notifications");
        if(!alive)return;
        const rows=Array.isArray(payload.items)
          ?payload.items.filter((row):row is NotificationItem=>Boolean(row&&typeof row==="object"))
          :[];
        const unreadRows=rows.filter(row=>!row.is_read&&!row.read_at);
        const routes=Array.from(new Set(
          unreadRows
            .map(row=>normalizeRoute(row.route))
            .filter((route):route is string=>Boolean(route))
        ));
        const unread=Number.isFinite(Number(payload.unread_count))
          ?Math.max(0,Number(payload.unread_count)||0)
          :unreadRows.length;
        setState(current=>({...current,notificationUnreadCount:unread,unreadRoutes:routes}));
      }catch{}
    };

    const applyRelease=async(path:string,init:RequestInit={})=>{
      try{
        const release=await request<ReleaseStatus>(path,init);
        if(!alive)return;
        setState(current=>({...current,updateAvailable:Boolean(release.update_available)}));
      }catch{}
    };

    const refreshRelease=()=>applyRelease("/v1/admin/system/release/status");
    const checkRelease=()=>applyRelease("/v1/admin/system/release/check",{method:"POST"});

    const refreshVisible=()=>{
      if(document.visibilityState!=="visible")return;
      void refreshSupport();
      void refreshPayments();
      void refreshNotifications();
      void refreshRelease();
    };

    refreshVisible();
    void checkRelease();

    const fastTimer=window.setInterval(()=>{
      if(document.visibilityState!=="visible")return;
      void refreshSupport();
    },2500);

    const workTimer=window.setInterval(()=>{
      if(document.visibilityState!=="visible")return;
      void refreshPayments();
      void refreshNotifications();
    },10000);

    const releaseStatusTimer=window.setInterval(()=>{
      if(document.visibilityState==="visible")void refreshRelease();
    },5000);

    const releaseCheckTimer=window.setInterval(()=>{
      if(document.visibilityState==="visible")void checkRelease();
    },300000);

    window.addEventListener("focus",refreshVisible);
    document.addEventListener("visibilitychange",refreshVisible);

    return()=>{
      alive=false;
      window.clearInterval(fastTimer);
      window.clearInterval(workTimer);
      window.clearInterval(releaseStatusTimer);
      window.clearInterval(releaseCheckTimer);
      window.removeEventListener("focus",refreshVisible);
      document.removeEventListener("visibilitychange",refreshVisible);
    };
  },[]);

  const routeSet=useMemo(()=>new Set(state.unreadRoutes),[state.unreadRoutes]);

  const hasPathAttention=(href:string)=>{
    if(routeSet.has(href))return true;
    if(href==="/admin/payments"&&state.paymentReviewCount>0)return true;
    if(href==="/admin/support"&&state.supportNeedsReplyCount>0)return true;
    if(href==="/admin/notifications"&&state.notificationUnreadCount>0)return true;
    return false;
  };

  const countForPath=(href:string)=>{
    if(href==="/admin/payments")return state.paymentReviewCount;
    if(href==="/admin/support")return state.supportNeedsReplyCount;
    if(href==="/admin/notifications")return state.notificationUnreadCount;
    return 0;
  };

  const groupHasAttention=(groupName:string,paths:readonly string[])=>{
    if(groupName==="System & Maintenance"&&state.updateAvailable)return true;
    return paths.some(path=>hasPathAttention(path));
  };

  return {...state,hasPathAttention,countForPath,groupHasAttention};
}
