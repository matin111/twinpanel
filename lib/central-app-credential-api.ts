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


export type AppDirectoryRegistration={
  ok:boolean;namespace:string;short_namespace:string;api_origin:string;
};

/** Only a panel administrator may register the public panel HTTPS origin.
 * Vendor receives a signed installation entitlement and namespace only;
 * never app usernames or passwords.
 */
export async function registerAppDirectory(apiOrigin:string):Promise<AppDirectoryRegistration>{
  const origin=new URL(apiOrigin);
  if(origin.protocol!=="https:"||origin.username||origin.password||
     origin.search||origin.hash||origin.pathname!=="/"||
     (origin.port&&origin.port!=="443")){
    throw new Error("PUBLIC_HTTPS_ORIGIN_REQUIRED");
  }
  const token=getCustomerToken();
  if(!token)throw new Error("Login required");
  const response=await fetch(`${API_BASE}/v1/central-app/admin/register`,{
    method:"POST",
    headers:{"Authorization":`Bearer ${token}`,"Content-Type":"application/json",
             "Cache-Control":"no-store"},
    cache:"no-store",
    body:JSON.stringify({api_origin:origin.origin}),
  });
  if(!response.ok){
    let reason=`HTTP ${response.status}`;
    try{const data=await response.json();reason=String(data.detail||reason);}catch{}
    throw new Error(reason);
  }
  return await response.json() as AppDirectoryRegistration;
}
