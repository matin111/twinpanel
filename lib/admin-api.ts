"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type AdminUser={id:number;email:string|null;phone?:string|null;full_name:string|null;role:string;is_active:boolean;created_at:string};
export type AdminStats={users:number;active_subscriptions:number;online_nodes:number;active_plans:number};
export type DashboardSummary={online_users:number;total_users:number;total_accounts:number;sales_today:number;sales_week:number;sales_month:number;online_nodes:number;total_nodes:number;protocols:Record<string,{online:boolean;online_nodes:number}>;generated_at:string};
export type AdminNode={id:number;name:string;node_type?:string;country_code?:string;public_ip?:string;status?:string;current_users?:number;capacity_users?:number;last_seen_at?:string|null;enable_cisco?:boolean;enable_openvpn?:boolean;enable_wireguard?:boolean;enable_l2tp?:boolean;enable_v2ray?:boolean};
export type AdminTunnel={id:number;iran_node_id:number;exit_node_id:number;transport?:string;active_transport?:string|null;preferred_transport?:string|null;mode?:string|null;status?:string;latency_ms?:number|null;priority?:number;is_active?:boolean};
export type RuntimeRow=Record<string,unknown>;
export type PaymentReviewSummary={needs_review:number;purchase_review:number;receipt_review:number;wallet_review:number;generated_at?:string};
export type XrayDomainState={
  ok?:boolean;
  node_id?:number;
  xray_domain?:string|null;
  effective_xray_domain?:string|null;
  legacy_public_domain_fallback?:boolean;
  public_domain?:string|null;
  tls_enabled?:boolean;
  available_profiles?:string[];
  message?:string;
};

const READ_CACHE_TTL_MS=4000;
const readCache=new Map<string,{expires:number;promise:Promise<unknown>}>();
const TRANSIENT_GET_STATUSES=new Set([502,503,504]);
const TRANSIENT_GET_RETRY_MS=[350,900,1800] as const;

function isHtmlErrorBody(value:string){
  const sample=value.trim().slice(0,1024);
  return /<(?:!doctype|html|head|body|title|center)\b|nginx\//i.test(sample);
}

function isTransientNetworkError(reason:unknown){
  const text=reason instanceof Error?reason.message:String(reason||"");
  return /failed to fetch|networkerror|network request failed|load failed|fetch failed|connection/i.test(text);
}

function transientStatusText(status:number){
  return `سرویس پنل موقتاً در دسترس نیست. چند لحظه بعد دوباره تلاش کنید. (${status})`;
}

function networkErrorText(){
  return "ارتباط با سرویس پنل موقتاً قطع شد. چند لحظه بعد دوباره تلاش کنید.";
}

function errorText(payload:unknown,status:number){
  if(TRANSIENT_GET_STATUSES.has(status))return transientStatusText(status);
  if(typeof payload==="string"&&payload.trim()){
    const text=payload.trim();
    if(isHtmlErrorBody(text))return `خطای ارتباط با سرویس پنل (${status})`;
    return text;
  }
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
    if(Array.isArray(item.detail))return item.detail.map(x=>typeof x==="object"&&x&&"msg" in x?String((x as {msg:unknown}).msg):String(x)).join("، ");
  }
  return `API error ${status}`;
}

function wait(ms:number){
  return new Promise<void>(resolve=>globalThis.setTimeout(resolve,ms));
}

async function performRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");

  const method=String(init.method||"GET").toUpperCase();
  const maxAttempts=method==="GET"?TRANSIENT_GET_RETRY_MS.length+1:1;

  for(let attempt=0;attempt<maxAttempts;attempt+=1){
    let response:Response;
    try{
      response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
    }catch(reason){
      const canRetry=method==="GET"&&isTransientNetworkError(reason)&&attempt<TRANSIENT_GET_RETRY_MS.length;
      if(canRetry){
        await wait(TRANSIENT_GET_RETRY_MS[attempt]);
        continue;
      }
      if(isTransientNetworkError(reason))throw new Error(networkErrorText());
      throw reason;
    }

    if(method==="GET"&&TRANSIENT_GET_STATUSES.has(response.status)&&attempt<TRANSIENT_GET_RETRY_MS.length){
      try{await response.body?.cancel();}catch{}
      await wait(TRANSIENT_GET_RETRY_MS[attempt]);
      continue;
    }

    if(response.status===204)return undefined as T;

    const raw=await response.text();
    let payload:unknown=null;
    if(raw){
      try{payload=JSON.parse(raw);}catch{payload=raw;}
    }

    if(!response.ok)throw new Error(errorText(payload,response.status));
    return payload as T;
  }

  throw new Error(networkErrorText());
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const method=String(init.method||"GET").toUpperCase();

  if(method!=="GET"){
    readCache.clear();
    return performRequest<T>(path,init);
  }

  const now=Date.now();
  const cached=readCache.get(path);
  if(cached&&cached.expires>now)return cached.promise as Promise<T>;

  const promise=performRequest<T>(path,init);
  readCache.set(path,{expires:now+READ_CACHE_TTL_MS,promise:promise as Promise<unknown>});

  try{
    return await promise;
  }catch(error){
    if(readCache.get(path)?.promise===promise)readCache.delete(path);
    throw error;
  }
}

export const adminApi={
  stats:()=>request<AdminStats>("/v1/admin/stats"),
  dashboard:()=>request<DashboardSummary>("/v1/admin/dashboard-summary"),
  users:()=>request<AdminUser[]>("/v1/admin/users"),
  createUser:(payload:{email:string;phone?:string;password:string;full_name:string})=>request<AdminUser>("/v1/admin/users",{method:"POST",body:JSON.stringify(payload)}),
  updateUser:(id:number,payload:{email?:string;phone?:string;full_name?:string})=>request<AdminUser>(`/v1/admin/users/${id}`,{method:"PATCH",body:JSON.stringify(payload)}),
  deleteUser:(id:number)=>request<{ok:boolean;user_id:number;email:string}>(`/v1/admin/users/${id}`,{method:"DELETE"}),
  toggleUser:(id:number)=>request<{ok:boolean;is_active:boolean}>(`/v1/admin/users/${id}/toggle-active`,{method:"POST"}),
  resetUserPassword:(id:number,newPassword:string)=>request<{ok:boolean}>(`/v1/admin/users/${id}/reset-password`,{method:"POST",body:JSON.stringify({new_password:newPassword})}),

  nodes:()=>request<AdminNode[]>("/v1/nodes"),
  toggleNodeMaintenance:(id:number)=>request<AdminNode>(`/v1/nodes/${id}/maintenance`,{method:"POST"}),
  nodeHealth:(id:number)=>request<RuntimeRow>(`/v1/nodes/${id}/health`),
  nodeProtocols:(id:number)=>request<RuntimeRow>(`/v1/nodes/${id}/protocols`),
  xrayDomain:(id:number)=>request<XrayDomainState>(`/v1/xray-modern-admin/nodes/${id}/xray-domain`),
  saveXrayDomain:(id:number,domain:string)=>request<XrayDomainState>(`/v1/xray-modern-admin/nodes/${id}/xray-domain`,{method:"PUT",body:JSON.stringify({domain})}),
  prepareXrayDomain:(id:number,issueCertificate=true)=>request<XrayDomainState>(`/v1/xray-modern-admin/nodes/${id}/xray-domain/prepare`,{method:"POST",body:JSON.stringify({issue_certificate:issueCertificate})}),
  deleteNode:async(id:number)=>{
    try{
      return await request<RuntimeRow>(`/v1/nodes/${id}`,{method:"DELETE"});
    }catch(error){
      const message=error instanceof Error?error.message:String(error);

      // TWINPANEL_OFFLINE_NODE_FORCE_RETIRE_CONFIRM_V1
      const unreachablePreflight=/(حذف شروع نشد|دسترسی SSH یکی از نودهای لازم|api error 424)/i.test(message);
      if(unreachablePreflight){
        const confirmed=globalThis.confirm(
          "دسترسی SSH نود برقرار نیست و پاک‌سازی Runtime روی سرور انجام نمی‌شود. نود فقط از پنل حذف شود؟"
        );
        if(!confirmed)throw error;
        return request<RuntimeRow>(`/v1/nodes/${id}/force-retire`,{method:"POST"});
      }

      if(!/(پاک.?سازی|runtime|حذف را دوباره|api error 409|api error 500)/i.test(message))throw error;
      return request<RuntimeRow>(`/v1/nodes/${id}/force-retire`,{method:"POST"});
    }
  },

  tunnels:()=>request<AdminTunnel[]>("/v1/tunnels"),
  createTunnel:(payload:{iran_node_id:number;exit_node_id:number;transport:string;priority:number;is_active:boolean})=>request<AdminTunnel>("/v1/tunnels",{method:"POST",body:JSON.stringify(payload)}),
  updateTunnel:(id:number,payload:RuntimeRow)=>request<AdminTunnel>(`/v1/tunnels/${id}`,{method:"PATCH",body:JSON.stringify(payload)}),
  toggleTunnel:(id:number)=>request<AdminTunnel>(`/v1/tunnels/${id}/toggle`,{method:"POST"}),
  prepareTunnel:(id:number)=>request<AdminTunnel>(`/v1/tunnels/${id}/prepare`,{method:"POST"}),
  tunnelHealth:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/health`),
  deleteTunnel:async(id:number)=>{
    try{
      return await request<RuntimeRow>(`/v1/tunnels/${id}`,{method:"DELETE"});
    }catch(error){
      const message=error instanceof Error?error.message:String(error);

      // TWINPANEL_UNREACHABLE_TUNNEL_FORCE_DELETE_CONFIRM_V1
      // Normal deletion keeps strict SSH cleanup. If a node is dead, let the
      // admin explicitly remove only the controller desired-state so broken
      // infrastructure can never trap an undeletable tunnel in the panel.
      const canForce=/(حذف شروع نشد|دسترسی SSH یکی از نودهای لازم|پاک.?سازی کامل تونل|تونل از دیتابیس حذف نشد|api error 424|api error 409)/i.test(message);
      if(!canForce)throw error;

      const confirmed=globalThis.confirm(
        "یکی از نودهای تانل در دسترس نیست. پاک‌سازی Runtime روی نود خراب ممکن نیست. تانل فقط از پنل و کنترل‌پلین حذف شود؟"
      );
      if(!confirmed)throw error;

      return request<RuntimeRow>(`/v1/tunnels/${id}/force-delete`,{method:"POST"});
    }
  },

  subscriptions:()=>request<RuntimeRow[]>("/v1/subscriptions"),
  subscriptionsV2:()=>request<RuntimeRow[]>("/v1/subscriptions/admin-list-v2"),
  createSubscription:(payload:{user_id:number;plan_id:number;node_ids:number[];protocols:string[];traffic_gb?:number;duration_days?:number;username?:string;password?:string})=>request<RuntimeRow>("/v1/subscriptions",{method:"POST",body:JSON.stringify(payload)}),
  createSubscriptionV2:async(payload:{user_id:number;plan_id?:number|null;node_ids:number[];protocols:string[];traffic_gb?:number;duration_days?:number;device_limit?:number;username?:string;password?:string})=>{
    try{
      return await request<RuntimeRow>("/v1/subscriptions/admin-create-v2",{method:"POST",body:JSON.stringify(payload)});
    }catch(error){
      const message=error instanceof Error?error.message:String(error);
      if(!/(not found|method not allowed|api error 404|api error 405)/i.test(message))throw error;
      if(payload.plan_id==null){
        throw new Error("ساخت اشتراک دستی به API جدید نیاز دارد؛ پنل را بروزرسانی کنید");
      }
      const {device_limit:_deviceLimit,...legacyPayload}=payload;
      return request<RuntimeRow>("/v1/subscriptions",{method:"POST",body:JSON.stringify(legacyPayload)});
    }
  },
  setSubscriptionActive:(id:number,active:boolean)=>request<RuntimeRow>(`/v1/subscriptions/${id}/${active?"activate":"suspend"}`,{method:"POST"}),
  deleteSubscription:(id:number)=>request<RuntimeRow>(`/v1/subscriptions/${id}`,{method:"DELETE"}),
  editSubscription:(id:number,payload:{plan_id:number;traffic_gb:number;node_ids:number[];protocols:string[];account_username?:string;account_password?:string})=>request<RuntimeRow>(`/v1/subscriptions/${id}/admin-edit`,{method:"PATCH",body:JSON.stringify(payload)}),
  extendSubscription:(id:number,payload:{duration_days?:number;traffic_gb?:number;add_days?:number;add_traffic_gb?:number})=>request<RuntimeRow>(`/v1/subscriptions/${id}/extend`,{method:"PATCH",body:JSON.stringify({...(payload.add_days!=null?{add_days:payload.add_days}:{}),...(payload.add_traffic_gb!=null?{add_traffic_gb:payload.add_traffic_gb}:payload.traffic_gb!=null?{add_traffic_gb:payload.traffic_gb}:{}),...(payload.duration_days!=null?{add_days:payload.duration_days}:{})})}),
  setSubscriptionManualLimits:(id:number,payload:{traffic_gb:number;duration_days:number})=>request<RuntimeRow>(`/v1/subscriptions/${id}/manual-limits`,{method:"PATCH",body:JSON.stringify(payload)}),
  provisionSubscription:(id:number)=>request<RuntimeRow>(`/v1/subscriptions/${id}/provision-account`,{method:"POST"}),
  refreshSubscriptionPasswords:(id:number)=>request<RuntimeRow>(`/v1/subscriptions/${id}/refresh-simple-passwords`,{method:"POST"}),
  subscriptionConnectionInfo:(id:number)=>request<RuntimeRow>(`/v1/subscriptions/${id}/connection-info`),

  plans:()=>request<RuntimeRow[]>("/v1/plans/admin/all"),
  createPlan:(payload:RuntimeRow)=>request<RuntimeRow>("/v1/plans",{method:"POST",body:JSON.stringify(payload)}),
  updatePlan:(id:number,payload:RuntimeRow)=>request<RuntimeRow>(`/v1/plans/${id}`,{method:"PATCH",body:JSON.stringify(payload)}),
  deletePlan:(id:number)=>request<RuntimeRow>(`/v1/plans/${id}`,{method:"DELETE"}),

  payments:()=>request<RuntimeRow[]>("/v1/payments/admin/intents"),
  paymentReviewSummary:()=>request<PaymentReviewSummary>("/v1/admin/wallet/payment-review-summary"),
  approvePayment:(id:number)=>request<RuntimeRow>(`/v1/admin/wallet/payment-intents/${id}/approve-safe`,{method:"POST"}),
  rejectPayment:(id:number,reason:string)=>request<RuntimeRow>(`/v1/payments/admin/intents/${id}/reject`,{method:"POST",body:JSON.stringify({reason})})
};