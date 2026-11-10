"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type AppAccessDelivery={
  subscription_id:number;
  app_username:string;
  app_password:string;
  subscription_link:string;
  app_password_revision:number;
  vpn_credentials_unchanged:boolean;
};

export async function getAppAccess(
  owner:"admin"|"reseller",subscriptionId:number,reset=false
):Promise<AppAccessDelivery>{
  if(!Number.isSafeInteger(subscriptionId)||subscriptionId<=0)throw new Error("Invalid subscription ID");
  const token=getCustomerToken();
  if(!token)throw new Error("Login required");
  const action=reset?"app-password-reset":"app-delivery";
  const response=await fetch(
    `${API_BASE}/v1/central-app/${owner}/subscriptions/${subscriptionId}/${action}`,{
      method:"POST",
      headers:{"Authorization":`Bearer ${token}`,"Cache-Control":"no-store"},
      cache:"no-store",
    }
  );
  if(!response.ok){
    let reason=`HTTP ${response.status}`;
    try{const data=await response.json();reason=String(data.detail||reason);}catch{}
    throw new Error(reason);
  }
  return await response.json() as AppAccessDelivery;
}
