"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type OpsRow=Record<string,unknown>;

function errorMessage(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
    if(Array.isArray(item.detail))return item.detail.map(x=>typeof x==="object"&&x&&"msg" in x?String((x as {msg:unknown}).msg):String(x)).join("، ");
  }
  return `API error ${status}`;
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let payload:unknown=null;try{payload=await response.json();}catch{}
    throw new Error(errorMessage(payload,response.status));
  }
  if(response.status===204)return undefined as T;
  const type=response.headers.get("content-type")||"";
  if(!type.includes("application/json"))return await response.text() as T;
  return response.json() as Promise<T>;
}

export type NotificationSettings={
  telegram_enabled:boolean;
  telegram_chat_id:string;
  payment_enabled:boolean;
  network_enabled:boolean;
  security_enabled:boolean;
};

export type NotificationSendPayload={
  title:string;
  message:string;
  kind:"info"|"success"|"warning"|"error";
  user_email:string|null;
  send_telegram:boolean;
};

export const opsApi={
  supportTickets:()=>request<unknown>("/v1/admin/support/tickets"),
  supportTicket:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}`),
  supportReply:(id:string|number,message:string)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}/reply`,{method:"POST",body:JSON.stringify({message})}),
  supportClose:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}/close`,{method:"POST"}),
  supportReopen:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}/reopen`,{method:"POST"}),
  supportDelete:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}`,{method:"DELETE"}),

  notificationSettings:()=>request<NotificationSettings>("/v1/settings/notifications"),
  saveNotificationSettings:(payload:NotificationSettings)=>request<NotificationSettings>("/v1/settings/notifications",{method:"PUT",body:JSON.stringify(payload)}),
  testNotification:()=>request<unknown>("/v1/settings/notifications/test",{method:"POST"}),
  sendNotification:(payload:NotificationSendPayload)=>request<unknown>("/v1/admin/notifications/send",{method:"POST",body:JSON.stringify(payload)}),
  notificationHistory:(limit=30)=>request<unknown>(`/v1/admin/notifications/history?limit=${limit}`),
  panelNotifications:()=>request<unknown>("/v1/admin/panel-notifications"),
  panelNotificationsReadAll:()=>request<unknown>("/v1/admin/panel-notifications/read-all",{method:"POST"}),

  storeOrders:()=>request<unknown>("/v1/store/orders/admin"),

  subscriptionUsernameSettings:()=>request<OpsRow>("/v1/settings/general/subscription-username"),
  saveSubscriptionUsernameSettings:(payload:OpsRow)=>request<OpsRow>("/v1/settings/general/subscription-username",{method:"PUT",body:JSON.stringify(payload)})
};
