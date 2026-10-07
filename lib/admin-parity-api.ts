"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type AnyRow=Record<string,unknown>;

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  if(!response.ok){
    let detail=`API error ${response.status}`;
    try{
      const payload=await response.json() as {detail?:unknown;message?:unknown};
      if(typeof payload.detail==="string")detail=payload.detail;
      else if(typeof payload.message==="string")detail=payload.message;
      else if(Array.isArray(payload.detail))detail=payload.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
    }catch{}
    throw new Error(detail);
  }
  if(response.status===204)return undefined as T;
  const type=response.headers.get("content-type")||"";
  if(!type.includes("application/json"))return await response.text() as T;
  return response.json() as Promise<T>;
}

export type TelegramBotStatus={
  token_configured:boolean;
  installed:boolean;
  runtime_ready:boolean;
  service_state:string;
  bot?:{id:number|null;username:string|null;first_name:string|null};
  [key:string]:unknown;
};

export type BackupSettings={
  enabled:boolean;
  frequency:"hourly"|"daily"|"weekly";
  hour:number;
  minute:number;
  weekday:number;
  timezone:string;
  send_telegram:boolean;
  telegram_chat_id:string;
  retention:number;
};
export type BackupHome={
  ok:boolean;
  backups:AnyRow[];
  settings:BackupSettings;
  key_fingerprint?:string|null;
  included_tables?:string[];
  excluded_runtime_tables?:string[];
};

export type DiscountDraft={
  code:string;
  title?:string|null;
  discount_type:"percent"|"fixed"|string;
  discount_value:number;
  max_discount_toman?:number|null;
  min_order_toman:number;
  applies_to:string;
  plan_ids:number[];
  usage_limit_total?:number|null;
  usage_limit_per_user?:number|null;
  starts_at?:string|null;
  ends_at?:string|null;
  is_active:boolean;
};

export type ProvisionProtocolSettings={
  install_cisco:boolean;
  cisco_port:number;
  install_openvpn:boolean;
  openvpn_port:number;
  openvpn_transport:"udp"|"tcp";
  install_wireguard:boolean;
  wireguard_port:number;
  install_l2tp:boolean;
  install_v2ray:boolean;
  xray_port:number;
};

export type ProvisionInstallPayload=ProvisionProtocolSettings&{
  host:string;
  port:number;
  username:string;
  password:string;
  name:string;
  node_type:"iran"|"exit";
  country_code:string;
  capacity_users:number;
};

export type MotherAccessSettings={
  admin_enabled:boolean;
  reseller_enabled:boolean;
  reseller_overrides:Record<string,boolean>;
};

export const parityApi={
  telegramStatus:()=>request<TelegramBotStatus>("/v1/admin/telegram-bot"),
  telegramSaveToken:(token:string)=>request<AnyRow>("/v1/admin/telegram-bot/token",{method:"PUT",body:JSON.stringify({token})}),
  telegramTest:()=>request<AnyRow>("/v1/admin/telegram-bot/test",{method:"POST"}),
  telegramInstall:()=>request<AnyRow>("/v1/admin/telegram-bot/install",{method:"POST"}),
  telegramStart:()=>request<AnyRow>("/v1/admin/telegram-bot/start",{method:"POST"}),
  telegramStop:()=>request<AnyRow>("/v1/admin/telegram-bot/stop",{method:"POST"}),
  telegramRestart:()=>request<AnyRow>("/v1/admin/telegram-bot/restart",{method:"POST"}),
  telegramLogs:()=>request<{logs:string}>("/v1/admin/telegram-bot/logs"),

  backups:()=>request<BackupHome>("/v1/admin/backups"),
  backupCreate:(sendTelegram:boolean)=>request<AnyRow>("/v1/admin/backups/create",{method:"POST",body:JSON.stringify({send_telegram:sendTelegram})}),
  backupSettings:(settings:BackupSettings)=>request<AnyRow>("/v1/admin/backups/settings",{method:"PUT",body:JSON.stringify(settings)}),
  backupTestTelegram:()=>request<AnyRow>("/v1/admin/backups/test-telegram",{method:"POST"}),
  backupRestore:(filename:string)=>request<AnyRow>(`/v1/admin/backups/${encodeURIComponent(filename)}/restore`,{method:"POST",body:JSON.stringify({confirm:"RESTORE"})}),
  backupDelete:(filename:string)=>request<AnyRow>(`/v1/admin/backups/${encodeURIComponent(filename)}`,{method:"DELETE"}),
  backupTelegram:(filename:string)=>request<AnyRow>(`/v1/admin/backups/${encodeURIComponent(filename)}/telegram`,{method:"POST"}),
  backupInfo:(filename:string)=>request<AnyRow>(`/v1/admin/backups/${encodeURIComponent(filename)}/info`),

  wallets:()=>request<AnyRow[]>("/v1/admin/wallet/wallets"),
  walletTopups:()=>request<AnyRow[]>("/v1/admin/wallet/topups"),
  walletApprove:(id:number)=>request<AnyRow>(`/v1/admin/wallet/topups/${id}/approve`,{method:"POST"}),
  walletReject:(id:number,reason:string)=>request<AnyRow>(`/v1/admin/wallet/topups/${id}/reject`,{method:"POST",body:JSON.stringify({reason})}),
  walletAdjust:(userId:number,amountToman:number,note:string)=>request<AnyRow>(`/v1/admin/wallet/wallets/${userId}/adjust`,{method:"POST",body:JSON.stringify({amount_toman:amountToman,note})}),

  discounts:()=>request<AnyRow[]>("/v1/discounts/admin"),
  discountCreate:(payload:DiscountDraft)=>request<AnyRow>("/v1/discounts/admin",{method:"POST",body:JSON.stringify(payload)}),
  discountUpdate:(id:number,payload:DiscountDraft)=>request<AnyRow>(`/v1/discounts/admin/${id}`,{method:"PUT",body:JSON.stringify(payload)}),
  discountDelete:(id:number)=>request<AnyRow>(`/v1/discounts/admin/${id}`,{method:"DELETE"}),

  resellerStats:()=>request<AnyRow>("/v1/admin/resellers/stats"),
  resellers:()=>request<AnyRow[]>("/v1/admin/resellers"),
  resellerCreate:(payload:AnyRow)=>request<AnyRow>("/v1/admin/resellers",{method:"POST",body:JSON.stringify(payload)}),
  resellerUpdate:(id:number,payload:AnyRow)=>request<AnyRow>(`/v1/admin/resellers/${id}`,{method:"PATCH",body:JSON.stringify(payload)}),
  resellerToggle:(id:number)=>request<AnyRow>(`/v1/admin/resellers/${id}/toggle-active`,{method:"POST"}),
  resellerDelete:(id:number)=>request<AnyRow>(`/v1/admin/resellers/${id}`,{method:"DELETE"}),
  resellerWalletAdjust:(id:number,amount_toman:number,note:string)=>request<AnyRow>(`/v1/admin/resellers/${id}/wallet/adjust`,{method:"POST",body:JSON.stringify({amount_toman,note})}),
  resellerPlans:(id:number)=>request<AnyRow[]>(`/v1/admin/resellers/${id}/plans`),
  resellerSetPlan:(resellerId:number,planId:number,payload:AnyRow)=>request<AnyRow>(`/v1/admin/resellers/${resellerId}/plans/${planId}`,{method:"PUT",body:JSON.stringify(payload)}),
  resellerTrafficBalance:(id:number)=>request<AnyRow>(`/v1/admin/resellers/${id}/traffic/balance`),
  resellerTrafficTransactions:(id:number)=>request<AnyRow[]>(`/v1/admin/resellers/${id}/traffic/transactions`),
  resellerTrafficAdjust:(id:number,payload:AnyRow)=>request<AnyRow>(`/v1/admin/resellers/${id}/traffic/adjust`,{method:"POST",body:JSON.stringify(payload)}),

  storefrontSettings:()=>request<AnyRow>("/v1/storefront/settings"),
  saveStorefrontSettings:(payload:AnyRow)=>request<AnyRow>("/v1/storefront/settings",{method:"PUT",body:JSON.stringify(payload)}),

  systemHealth:()=>request<AnyRow>("/v1/admin/system-health"),
  securityOverview:()=>request<AnyRow>("/v1/admin/security/overview"),
  coreProtocols:()=>request<AnyRow>("/v1/admin/core-protocols"),
  restartCoreProtocol:(protocol:string)=>request<AnyRow>(`/v1/admin/core-protocols/${encodeURIComponent(protocol)}/restart`,{method:"POST"}),
  restartAllCoreProtocols:()=>request<AnyRow>("/v1/admin/core-protocols/restart-all",{method:"POST"}),

  provisionTest:(payload:{host:string;port:number;username:string;password:string})=>request<AnyRow>("/v1/provision/test",{method:"POST",body:JSON.stringify(payload)}),
  provisionInstall:(payload:ProvisionInstallPayload)=>request<AnyRow>("/v1/provision/install",{method:"POST",body:JSON.stringify(payload)}),
  provisionNodeAccess:(nodeId:number)=>request<AnyRow>(`/v1/provision/node-access/${nodeId}`),
  provisionSaveNodeAccess:(payload:{node_id:number;host:string;port:number;username:string;password:string})=>request<AnyRow>("/v1/provision/save-node-access",{method:"POST",body:JSON.stringify(payload)}),
  provisionProtocolHealth:(nodeId:number,protocol?:string)=>request<AnyRow>("/v1/provision/protocol-health",{method:"POST",body:JSON.stringify({node_id:nodeId,...(protocol?{protocol}:{})})}),
  provisionRestartProtocol:(nodeId:number,protocol?:string)=>request<AnyRow>("/v1/provision/restart-protocol",{method:"POST",body:JSON.stringify({node_id:nodeId,...(protocol?{protocol}:{})})}),
  provisionRepairSaved:(payload:ProvisionProtocolSettings&{node_id:number})=>request<AnyRow>("/v1/provision/repair-protocols-saved",{method:"POST",body:JSON.stringify(payload)}),
  provisionUpgradeAgent:(nodeId:number)=>request<AnyRow>("/v1/provision/upgrade-agent",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  provisionInstallFabric:(nodeId:number)=>request<AnyRow>("/v1/provision/install-fabric",{method:"POST",body:JSON.stringify({node_id:nodeId})}),
  provisionFabricStatus:(nodeId:number)=>request<AnyRow>(`/v1/provision/fabric-status/${nodeId}`),

  paymentSettings:()=>request<AnyRow>("/v1/payments/admin/settings"),
  savePaymentSettings:(payload:AnyRow)=>request<AnyRow>("/v1/payments/admin/settings",{method:"PUT",body:JSON.stringify(payload)}),
  smsReader:()=>request<AnyRow>("/v1/payments/admin/sms-reader"),
  smsPairCode:()=>request<AnyRow>("/v1/payments/admin/sms-reader/pair-code",{method:"POST"}),
  smsAutomagenDevice:(name:string)=>request<AnyRow>("/v1/payments/admin/sms-reader/automagen-device",{method:"POST",body:JSON.stringify({name})}),
  smsRevokeDevice:(id:number)=>request<AnyRow>(`/v1/payments/admin/sms-reader/devices/${id}/revoke`,{method:"POST"}),

  motherAccess:()=>request<MotherAccessSettings>("/v1/mother-access/admin"),
  saveMotherAccess:(payload:{admin_enabled:boolean;reseller_enabled:boolean})=>request<AnyRow>("/v1/mother-access/admin",{method:"PUT",body:JSON.stringify(payload)}),
  setResellerMotherAccess:(resellerId:number,enabled:boolean)=>request<AnyRow>(`/v1/mother-access/admin/resellers/${resellerId}`,{method:"PUT",body:JSON.stringify({enabled})})
};
