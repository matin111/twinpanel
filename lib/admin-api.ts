"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type AdminUser={id:number;email:string|null;phone?:string|null;full_name:string|null;role:string;is_active:boolean;created_at:string};
export type AdminStats={users:number;active_subscriptions:number;online_nodes:number;active_plans:number};
export type DashboardSummary={online_users:number;total_users:number;total_accounts:number;sales_today:number;sales_week:number;sales_month:number;online_nodes:number;total_nodes:number;protocols:Record<string,{online:boolean;online_nodes:number}>;generated_at:string};
export type AdminNode={id:number;name:string;node_type?:string;country_code?:string;public_ip?:string;status?:string;current_users?:number;capacity_users?:number;last_seen_at?:string|null;enable_cisco?:boolean;enable_openvpn?:boolean;enable_wireguard?:boolean;enable_l2tp?:boolean;enable_v2ray?:boolean};
export type AdminTunnel={id:number;iran_node_id:number;exit_node_id:number;transport?:string;status?:string;latency_ms?:number|null;priority?:number;is_active?:boolean};
export type RuntimeRow=Record<string,unknown>;

function errorText(payload:unknown,status:number){
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
    throw new Error(errorText(payload,response.status));
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
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
  deleteNode:(id:number)=>request<RuntimeRow>(`/v1/nodes/${id}`,{method:"DELETE"}),

  tunnels:()=>request<AdminTunnel[]>("/v1/tunnels"),
  createTunnel:(payload:{iran_node_id:number;exit_node_id:number;transport:string;priority:number;is_active:boolean})=>request<AdminTunnel>("/v1/tunnels",{method:"POST",body:JSON.stringify(payload)}),
  updateTunnel:(id:number,payload:RuntimeRow)=>request<AdminTunnel>(`/v1/tunnels/${id}`,{method:"PATCH",body:JSON.stringify(payload)}),
  toggleTunnel:(id:number)=>request<AdminTunnel>(`/v1/tunnels/${id}/toggle`,{method:"POST"}),
  prepareTunnel:(id:number)=>request<AdminTunnel>(`/v1/tunnels/${id}/prepare`,{method:"POST"}),
  tunnelHealth:(id:number)=>request<RuntimeRow>(`/v1/tunnels/${id}/health`),
  deleteTunnel:(id:number)=>request<{ok:boolean}>(`/v1/tunnels/${id}`,{method:"DELETE"}),

  subscriptions:()=>request<RuntimeRow[]>("/v1/subscriptions"),
  createSubscription:(payload:{user_id:number;plan_id:number;node_ids:number[];protocols:string[];traffic_gb?:number;duration_days?:number;username?:string;password?:string})=>request<RuntimeRow>("/v1/subscriptions",{method:"POST",body:JSON.stringify(payload)}),
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
  approvePayment:(id:number)=>request<RuntimeRow>(`/v1/payments/admin/intents/${id}/approve`,{method:"POST"}),
  rejectPayment:(id:number,reason:string)=>request<RuntimeRow>(`/v1/payments/admin/intents/${id}/reject`,{method:"POST",body:JSON.stringify({reason})})
};
