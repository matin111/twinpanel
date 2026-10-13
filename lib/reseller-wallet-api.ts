"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type ResellerWalletSummary={
  id:number;
  wallet_balance:number;
  credit_limit:number;
  available_credit:number;
  [key:string]:unknown;
};

export type ResellerWalletTransaction={
  id:number;
  amount:number;
  balance_after:number;
  type:string;
  description?:string|null;
  reference_type?:string|null;
  reference_id?:number|null;
  created_at:string;
  [key:string]:unknown;
};

export type WalletPaymentMethod={
  id:string;
  title?:string;
  card_number?:string;
  card_holder?:string;
  asset?:string;
  network?:string;
  address?:string;
  auto_verify?:boolean;
  [key:string]:unknown;
};

export type ResellerWalletTopup={
  id:number;
  amount_toman:number;
  payable_amount_toman?:number;
  method:string;
  status:string;
  crypto_asset?:string|null;
  crypto_amount?:string|null;
  crypto_rate_toman?:number|null;
  tracking_code?:string|null;
  txid?:string|null;
  sender_card_last4?:string|null;
  transfer_date?:string|null;
  transfer_time?:string|null;
  receipt_uploaded?:boolean;
  review_note?:string|null;
  created_at:string;
  submitted_at?:string|null;
  approved_at?:string|null;
  rejected_at?:string|null;
  payment_method?:WalletPaymentMethod;
  [key:string]:unknown;
};

export type WalletTopupSubmit={
  tracking_code?:string|null;
  txid?:string|null;
  sender_card_last4?:string|null;
  transfer_date?:string|null;
  transfer_time?:string|null;
};

export type WalletReceiptStatus={
  ok:boolean;
  topup_id:number;
  receipt_uploaded:boolean;
  status:string;
};

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
    if(Array.isArray(row.detail))return row.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
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
    let payload:unknown=null;
    try{payload=await response.json();}catch{}
    throw new Error(errorText(payload,response.status));
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

export const resellerWalletApi={
  summary:()=>request<ResellerWalletSummary>("/v1/reseller/me"),
  transactions:()=>request<ResellerWalletTransaction[]>("/v1/reseller/wallet/transactions"),
  methods:async()=>{
    const result=await request<{methods?:WalletPaymentMethod[]}|WalletPaymentMethod[]>("/v1/wallet/methods");
    return Array.isArray(result)?result:Array.isArray(result.methods)?result.methods:[];
  },
  topups:()=>request<ResellerWalletTopup[]>("/v1/wallet/topups/me"),
  createTopup:(amountToman:number,method:string)=>request<ResellerWalletTopup>("/v1/wallet/topups",{
    method:"POST",
    body:JSON.stringify({amount_toman:amountToman,method}),
  }),
  receiptStatus:(topupId:number)=>request<WalletReceiptStatus>(`/v1/wallet/topups/${topupId}/receipt-status`),
  uploadReceipt:(topupId:number,file:File)=>{
    const form=new FormData();
    form.append("receipt",file);
    return request<WalletReceiptStatus>(`/v1/wallet/topups/${topupId}/receipt-upload`,{
      method:"POST",
      body:form,
    });
  },
  submitTopup:(topupId:number,payload:WalletTopupSubmit)=>request<ResellerWalletTopup>(`/v1/wallet/topups/${topupId}/submit`,{
    method:"POST",
    body:JSON.stringify(payload),
  }),
};
