"use client";

export const CUSTOMER_TOKEN_KEY="twinpanel_customer_token";
export const CUSTOMER_REMEMBER_KEY="twinpanel_customer_remember_token";

export type CustomerUser={
  id:number;
  email:string|null;
  phone?:string|null;
  full_name:string|null;
  role:"user"|"admin"|string;
  is_active:boolean;
  created_at:string;
};

export type LoginResult={
  access_token:string|null;
  token_type:string;
  requires_2fa?:boolean;
  two_factor_token?:string|null;
};

export type MySubscription={
  id:number;
  user_id:number;
  plan_id:number;
  status:string;
  traffic_limit_bytes:number;
  traffic_used_bytes:number;
  traffic_limit_gb:number;
  traffic_used_gb:number;
  traffic_remaining_gb:number;
  iran_node_id:number|null;
  exit_node_id:number|null;
  starts_at:string|null;
  expires_at:string|null;
  node_ids:number[];
  protocols:string[];
  plan_name:string|null;
  days_remaining:number;
  device_limit:number;
  activation_duration_days?:number;
};

export type CustomerConnectionInfo={
  subscription_id:number;
  credentials:Array<{protocol:string;username:string|null;items:unknown}>;
  downloads:Record<string,unknown>;
  subscription_link:string;
  account:{username:string|null;password:string|null};
};

export type StoreOrder={
  id:number;
  user_id:number;
  plan_id:number;
  amount_toman:number;
  protocols:string[];
  status:string;
  payment_method:string|null;
  payment_reference:string|null;
  subscription_id:number|null;
  error:string|null;
  created_at:string;
  paid_at:string|null;
  fulfilled_at:string|null;
  delivery_ready?:boolean;
};

export type PaymentIntent={
  id:number;
  order_id?:number|null;
  user_id?:number;
  amount_toman?:number;
  status:string;
  method?:string|null;
  payment_method?:string|null;
  crypto_amount_usdt?:string|null;
  tracking_code?:string|null;
  txid?:string|null;
  created_at:string;
  submitted_at?:string|null;
  verified_at?:string|null;
  rejected_at?:string|null;
};

export type Wallet={balance_toman:number;updated_at?:string;[key:string]:unknown};
export type WalletTransaction={id:number;amount_toman?:number;amount?:number;kind?:string;type?:string;description?:string|null;reference?:string|null;created_at:string;[key:string]:unknown};
export type WalletPaymentMethod={id:string;title?:string;card_number?:string;card_holder?:string;address?:string;rate_toman?:number;[key:string]:unknown};
export type WalletTopup={
  id:number;
  amount_toman:number;
  payable_amount_toman?:number;
  status:string;
  method?:string|null;
  crypto_amount_usdt?:string|null;
  tracking_code?:string|null;
  txid?:string|null;
  sender_card_last4?:string|null;
  transfer_date?:string|null;
  transfer_time?:string|null;
  review_note?:string|null;
  created_at:string;
  submitted_at?:string|null;
  approved_at?:string|null;
  rejected_at?:string|null;
  payment_method?:WalletPaymentMethod;
  [key:string]:unknown;
};
export type WalletTopupSubmit={tracking_code?:string|null;txid?:string|null;sender_card_last4?:string|null;transfer_date?:string|null;transfer_time?:string|null};
export type UserNotification={id:number;title?:string|null;message?:string|null;body?:string|null;kind?:string|null;is_read?:boolean;read_at?:string|null;created_at:string;[key:string]:unknown};
export type SupportTicket={id:number;subject?:string|null;category?:string|null;status:string;created_at:string;updated_at?:string|null;messages?:Array<unknown>;[key:string]:unknown};

type NotificationListResponse={
  unread_count?:number;
  items?:UserNotification[];
};

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const value=payload as {detail?:unknown;message?:unknown};
    if(typeof value.detail==="string")return value.detail;
    if(typeof value.message==="string")return value.message;
    if(Array.isArray(value.detail))return value.detail.map(x=>typeof x==="object"&&x&&"msg" in x?String((x as {msg:unknown}).msg):String(x)).join("، ");
  }
  return `API error ${status}`;
}

async function request<T>(path:string,options:RequestInit={},token?:string|null):Promise<T>{
  const headers=new Headers(options.headers);
  if(options.body&&!headers.has("Content-Type")&&!(options.body instanceof FormData))headers.set("Content-Type","application/json");
  if(token)headers.set("Authorization",`Bearer ${token}`);
  const response=await fetch(path,{...options,headers,cache:"no-store"});
  if(!response.ok){
    let payload:unknown=null;
    try{payload=await response.json();}catch{}
    throw new Error(errorText(payload,response.status));
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

export function getCustomerToken(){
  if(typeof window==="undefined")return null;
  try{return sessionStorage.getItem(CUSTOMER_TOKEN_KEY)||localStorage.getItem(CUSTOMER_REMEMBER_KEY)||null;}catch{return null;}
}

export function saveCustomerToken(token:string,remember=false){
  try{
    sessionStorage.setItem(CUSTOMER_TOKEN_KEY,token);
    if(remember)localStorage.setItem(CUSTOMER_REMEMBER_KEY,token);
    else localStorage.removeItem(CUSTOMER_REMEMBER_KEY);
  }catch{}
}

export function clearCustomerToken(){
  try{sessionStorage.removeItem(CUSTOMER_TOKEN_KEY);localStorage.removeItem(CUSTOMER_REMEMBER_KEY);}catch{}
}

export const customerApi={
  login:(email:string,password:string)=>request<LoginResult>("/v1/auth/login",{method:"POST",body:JSON.stringify({email,password})}),
  verifyTwoFactor:(twoFactorToken:string,code:string)=>request<{access_token:string;token_type:string}>("/v1/auth/2fa/login/verify",{method:"POST",body:JSON.stringify({two_factor_token:twoFactorToken,code})}),
  register:(email:string,password:string,fullName:string)=>request<{access_token:string;token_type:string}>("/v1/auth/register",{method:"POST",body:JSON.stringify({email,password,full_name:fullName||null})}),
  me:(token:string)=>request<CustomerUser>("/v1/auth/me",{},token),
  updateEmail:(token:string,email:string,currentPassword:string)=>request<CustomerUser>("/v1/auth/me/email",{method:"PATCH",body:JSON.stringify({email,current_password:currentPassword})},token),
  changePassword:(token:string,currentPassword:string,newPassword:string)=>request<{ok?:boolean;message?:string}>("/v1/auth/change-password",{method:"POST",body:JSON.stringify({current_password:currentPassword,new_password:newPassword})},token),
  twoFactorStatus:(token:string)=>request<{enabled:boolean}>("/v1/auth/2fa/status",{},token),
  twoFactorSetup:(token:string)=>request<{secret:string;otpauth_uri:string}>("/v1/auth/2fa/setup",{method:"POST"},token),
  twoFactorEnable:(token:string,code:string)=>request<{ok:boolean;enabled:boolean}>("/v1/auth/2fa/enable",{method:"POST",body:JSON.stringify({code})},token),
  twoFactorDisable:(token:string,currentPassword:string,code:string)=>request<{ok:boolean;enabled:boolean}>("/v1/auth/2fa/disable",{method:"POST",body:JSON.stringify({current_password:currentPassword,code})},token),

  subscriptions:(token:string)=>request<MySubscription[]>("/v1/subscriptions/me",{},token),
  manageSubscription:(token:string,id:number)=>request<Record<string,unknown>>(`/v1/customer/subscriptions/${id}/manage`,{},token),
  connectionInfo:(token:string,id:number)=>request<CustomerConnectionInfo>(`/v1/customer/subscriptions/${id}/connection-info`,{},token),
  renewSubscription:(token:string,id:number)=>request<StoreOrder>(`/v1/customer/subscriptions/${id}/renew-order`,{method:"POST"},token),

  orders:(token:string)=>request<StoreOrder[]>("/v1/store/orders/me",{},token),
  payments:(token:string)=>request<PaymentIntent[]>("/v1/payments/intents/me",{},token),
  paymentMethods:()=>request<{methods:Array<Record<string,unknown>>}>("/v1/payments/methods"),

  wallet:(token:string)=>request<Wallet>("/v1/wallet/me",{},token),
  walletTransactions:(token:string)=>request<WalletTransaction[]>("/v1/wallet/transactions",{},token),
  walletTopups:(token:string)=>request<WalletTopup[]>("/v1/wallet/topups/me",{},token),
  walletMethods:(token:string)=>request<{methods?:WalletPaymentMethod[]}|WalletPaymentMethod[]>("/v1/wallet/methods",{},token),
  createWalletTopup:(token:string,amountToman:number,method:string)=>request<WalletTopup>("/v1/wallet/topups",{method:"POST",body:JSON.stringify({amount_toman:amountToman,method})},token),
  submitWalletTopup:(token:string,id:number,payload:WalletTopupSubmit)=>request<WalletTopup>(`/v1/wallet/topups/${id}/submit`,{method:"POST",body:JSON.stringify(payload)},token),

  notifications:async(token:string,limit=50)=>{
    const payload=await request<NotificationListResponse|UserNotification[]>(`/v1/notifications/me?limit=${limit}`,{},token);
    if(Array.isArray(payload))return payload;
    return Array.isArray(payload?.items)?payload.items:[];
  },
  readNotification:(token:string,id:number)=>request<unknown>(`/v1/notifications/${id}/read`,{method:"POST"},token),
  readAllNotifications:(token:string)=>request<unknown>("/v1/notifications/read-all",{method:"POST"},token),

  supportTickets:(token:string)=>request<SupportTicket[]>("/v1/support/tickets/me",{},token),
  supportTicket:(token:string,id:number)=>request<SupportTicket>(`/v1/support/tickets/${id}`,{},token),
  createTicket:(token:string,category:string,subject:string,message:string)=>request<SupportTicket>("/v1/support/tickets",{method:"POST",body:JSON.stringify({category,subject,message})},token),
  closeTicket:(token:string,id:number)=>request<SupportTicket>(`/v1/support/tickets/${id}/close`,{method:"POST"},token)
};
