"use client";

import {getCustomerToken} from "./customer-api";
import {API_BASE} from "./api";

export type AppAppearance={
  primary_color:string;
  secondary_color:string;
  button_color:string;
  background_color:string;
  surface_color:string;
  background_style:"solid"|"gradient"|"image";
  background_image_url:string|null;
  theme_mode:"light"|"dark"|"system";
};
export type AppearanceReseller={id:number;name:string};
export type AppContact={
  logo_url:string|null;
  primary_color:string|null;
  secondary_color:string|null;
  telegram_url:string|null;
  renewal_url:string|null;
  support_phone:string|null;
  website_url:string|null;
};

const root="/v1/central-app";
async function request<T>(path:string,method="GET",body?:AppAppearance|AppContact):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}${path}`,{
    method,
    headers:{"Authorization":`Bearer ${token}`,...(body?{"Content-Type":"application/json"}:{})},
    ...(body?{body:JSON.stringify(body)}:{}),
    cache:"no-store",
  });
  if(!response.ok){
    let reason="API error "+response.status;
    try{const json=await response.json();reason=String(json.detail||reason);}catch{}
    throw new Error(reason);
  }
  return response.json() as Promise<T>;
}

export const appearanceApi={
  loadContact:(role:"admin"|"reseller",resellerId=0)=>{
    const path=role==="reseller"?"reseller/profile":resellerId>0
      ?`admin/resellers/${resellerId}/profile`:"admin/profile";
    return request<AppContact>(`${root}/${path}`);
  },
  saveContact:(role:"admin"|"reseller",value:AppContact,resellerId=0)=>{
    const path=role==="reseller"?"reseller/profile":resellerId>0
      ?`admin/resellers/${resellerId}/profile`:"admin/profile";
    return request<AppContact>(`${root}/${path}`,"PUT",value);
  },
  listResellers:()=>request<AppearanceReseller[]>(root+"/admin/appearance-resellers"),
  load:(role:"admin"|"reseller",resellerId=0)=>{
    const path=role==="reseller"?"reseller/appearance":resellerId>0?`admin/resellers/${resellerId}/appearance`:"admin/appearance";
    return request<AppAppearance>(`${root}/${path}`);
  },
  save:(role:"admin"|"reseller",value:AppAppearance,resellerId=0)=>{
    const path=role==="reseller"?"reseller/appearance":resellerId>0?`admin/resellers/${resellerId}/appearance`:"admin/appearance";
    return request<AppAppearance>(`${root}/${path}`,"PUT",value);
  },
  reset:(role:"admin"|"reseller",resellerId=0)=>{
    const path=role==="reseller"?"reseller/appearance":resellerId>0?`admin/resellers/${resellerId}/appearance`:"admin/appearance";
    return request<AppAppearance>(`${root}/${path}`,"DELETE");
  },
};
