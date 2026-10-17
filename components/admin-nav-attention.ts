"use client";

import {useEffect,useMemo,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

const SUPPORT_SEEN_KEY="twinpanel.admin.support.lastSeenInboundMessageId";

type NotificationItem={
  route?:string|null;
  read_at?:string|null;
  is_read?:boolean;
};

type NotificationPayload={
  unread_count?:number;
  items?:unknown;
};

type PulsePayload={
  latest_support_message_id?:number;
  support_unread_count?:number;
};

type PaymentReviewSummary={needs_review?:number};
type ReleaseStatus={update_available?:boolean};

type AttentionState={
  paymentReviewCount:number;
  supportUnreadCount:number;
  notificationUnreadCount:number;
  unreadRoutes:string[];
  updateAvailable:boolean;
};

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
  if(value.startsWith("/"))return value;
  return `/admin/${value.replace(/^admin\//,"")}`;
}

function readSupportSeen():number|null{
  try{
    const raw=localStorage.getItem(SUPPORT_SEEN_KEY);
    if(raw===null)return null;
    const value=Number(raw);
    return Number.isFinite(value)&&value>=0?value:null;
  }catch{return null;}
}

function writeSupportSeen(value:number){
  try{localStorage.setItem(SUPPORT_SEEN_KEY,String(Math.max(0,Math.floor(value))));}catch{}
}

export function useAdminNavAttention(active:string){
  const [state,setState]=useState<AttentionState>({
    paymentReviewCount:0,
    supportUnreadCount:0,
    notificationUnreadCount:0,
    unreadRoutes:[],
    updateAvailable:false,
  });

  useEffect(()=>{
    let alive=true;

    const refreshPulse=async()=>{
      try{
        const seen=readSupportSeen();
        const after=Math.max(0,seen??0);
        const pulse=await request<PulsePayload>(`/v1/admin/panel-notifications/pulse?support_after_id=${after}`);
        if(!alive)return;
        const latest=Math.max(0,Number(pulse.latest_support_message_id)||0);
        if(seen===null){
          writeSupportSeen(latest);
          setState(current=>({...current,supportUnreadCount:0}));
          return;
        }
        if(active==="/admin/support"){
          if(latest>seen)writeSupportSeen(latest);
          setState(current=>({...current,supportUnreadCount:0}));
          return;
        }
        const count=Math.max(0,Number(pulse.support_unread_count)||0);
        setState(current=>({...current,supportUnreadCount:count||(latest>seen?1:0)}));
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
        const rows=Array.isArray(payload.items)?payload.items.filter((row):row is NotificationItem=>Boolean(row&&typeof row==="object")):[];
        const unreadRows=rows.filter(row=>!row.is_read&&!row.read_at);
        const routes=Array.from(new Set(unreadRows.map(row=>normalizeRoute(row.route)).filter((route):route is string=>Boolean(route))));
        const unread=Number.isFinite(Number(payload.unread_count))?Math.max(0,Number(payload.unread_count)||0):unreadRows.length;
        setState(current=>({...current,notificationUnreadCount:unread,unreadRoutes:routes}));
      }catch{}
    };

    const refreshRelease=async()=>{
      try{
        const release=await request<ReleaseStatus>("/v1/admin/system/release/status");
        if(!alive)return;
        setState(current=>({...current,updateAvailable:Boolean(release.update_available)}));
      }catch{}
    };

    const refreshVisible=()=>{
      if(document.visibilityState!=="visible")return;
      void refreshPulse();
      void refreshPayments();
      void refreshNotifications();
      void refreshRelease();
    };

    refreshVisible();
    const pulseTimer=window.setInterval(()=>{if(document.visibilityState==="visible")void refreshPulse();},2000);
    const workTimer=window.setInterval(()=>{
      if(document.visibilityState!=="visible")return;
      void refreshPayments();
      void refreshNotifications();
    },10000);
    const releaseTimer=window.setInterval(()=>{if(document.visibilityState==="visible")void refreshRelease();},60000);
    window.addEventListener("focus",refreshVisible);
    document.addEventListener("visibilitychange",refreshVisible);

    return()=>{
      alive=false;
      window.clearInterval(pulseTimer);
      window.clearInterval(workTimer);
      window.clearInterval(releaseTimer);
      window.removeEventListener("focus",refreshVisible);
      document.removeEventListener("visibilitychange",refreshVisible);
    };
  },[active]);

  const routeSet=useMemo(()=>new Set(state.unreadRoutes),[state.unreadRoutes]);

  const hasPathAttention=(href:string)=>{
    if(routeSet.has(href))return true;
    if(href==="/admin/payments"&&state.paymentReviewCount>0)return true;
    if(href==="/admin/support"&&state.supportUnreadCount>0)return true;
    if(href==="/admin/notifications"&&state.notificationUnreadCount>0)return true;
    return false;
  };

  const countForPath=(href:string)=>{
    if(href==="/admin/payments")return state.paymentReviewCount;
    if(href==="/admin/support")return state.supportUnreadCount;
    if(href==="/admin/notifications")return state.notificationUnreadCount;
    return 0;
  };

  const groupHasAttention=(groupName:string,paths:readonly string[])=>{
    if(groupName==="System & Maintenance"&&state.updateAvailable)return true;
    return paths.some(path=>hasPathAttention(path));
  };

  return {...state,hasPathAttention,countForPath,groupHasAttention};
}
