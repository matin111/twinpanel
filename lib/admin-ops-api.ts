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
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData)&&!(init.body instanceof Blob))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store",signal:init.signal??AbortSignal.timeout(8000)});
  if(!response.ok){
    let payload:unknown=null;try{payload=await response.json();}catch{}
    throw new Error(errorMessage(payload,response.status));
  }
  if(response.status===204)return undefined as T;
  const type=response.headers.get("content-type")||"";
  if(!type.includes("application/json"))return await response.text() as T;
  return response.json() as Promise<T>;
}

async function uploadSupportImage(id:string|number,file:File):Promise<unknown>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers();
  headers.set("Authorization",`Bearer ${token}`);
  headers.set("Content-Type",file.type||"application/octet-stream");
  const response=await fetch(`${API_BASE}/v1/admin/support/tickets/${encodeURIComponent(String(id))}/upload-image`,{method:"POST",headers,body:file,cache:"no-store",signal:AbortSignal.timeout(15000)});
  if(!response.ok){
    let payload:unknown=null;try{payload=await response.json();}catch{}
    throw new Error(errorMessage(payload,response.status));
  }
  return response.json() as Promise<unknown>;
}

export type NotificationSettings={telegram_enabled:boolean;telegram_chat_id:string;payment_enabled:boolean;network_enabled:boolean;security_enabled:boolean};
export type NotificationSendPayload={title:string;message:string;kind:"info"|"success"|"warning"|"error";user_email:string|null;send_telegram:boolean};
export type SupportReplyPayload={message:string|null;attachment_type?:string|null;attachment_ref?:string|null;source?:string|null};
export type AdminRealtimePulse={latest_support_message_id:number;support_unread_count?:number;open_support_count:number;latest_receipt_id:number;pending_receipt_count:number;latest_notification_id:number;server_time:string};

export const opsApi={
  supportTickets:()=>request<unknown>("/v1/admin/support/tickets"),
  supportTicket:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}`),
  supportReply:(id:string|number,message:string)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}/reply`,{method:"POST",body:JSON.stringify({message})}),
  supportReplyFull:(id:string|number,payload:SupportReplyPayload)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}/reply`,{method:"POST",body:JSON.stringify(payload)}),
  supportUploadImage:(id:string|number,file:File)=>uploadSupportImage(id,file),
  supportClose:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}/close`,{method:"POST"}),
  supportReopen:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}/reopen`,{method:"POST"}),
  supportDelete:(id:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(id))}`,{method:"DELETE"}),
  supportDeleteMessage:(ticketId:string|number,messageId:string|number)=>request<unknown>(`/v1/admin/support/tickets/${encodeURIComponent(String(ticketId))}/messages/${encodeURIComponent(String(messageId))}`,{method:"DELETE"}),

  notificationSettings:()=>request<NotificationSettings>("/v1/settings/notifications"),
  saveNotificationSettings:(payload:NotificationSettings)=>request<NotificationSettings>("/v1/settings/notifications",{method:"PUT",body:JSON.stringify(payload)}),
  testNotification:()=>request<unknown>("/v1/settings/notifications/test",{method:"POST"}),
  sendNotification:(payload:NotificationSendPayload)=>request<unknown>("/v1/admin/notifications/send",{method:"POST",body:JSON.stringify(payload)}),
  notificationHistory:(limit=30)=>request<unknown>(`/v1/admin/notifications/history?limit=${limit}`),
  panelNotifications:()=>request<unknown>("/v1/admin/panel-notifications"),
  adminRealtimePulse:(supportAfterId=0)=>request<AdminRealtimePulse>(`/v1/admin/panel-notifications/pulse?support_after_id=${Math.max(0,Math.floor(Number(supportAfterId)||0))}`),
  panelNotificationRead:(id:string|number)=>request<unknown>(`/v1/admin/panel-notifications/${encodeURIComponent(String(id))}/read`,{method:"POST"}),
  panelNotificationsReadAll:()=>request<unknown>("/v1/admin/panel-notifications/read-all",{method:"POST"}),

  storeOrders:()=>request<unknown>("/v1/store/orders/admin"),

  subscriptionUsernameSettings:()=>request<OpsRow>("/v1/settings/general/subscription-username"),
  saveSubscriptionUsernameSettings:(payload:OpsRow)=>request<OpsRow>("/v1/settings/general/subscription-username",{method:"PUT",body:JSON.stringify(payload)})
};
