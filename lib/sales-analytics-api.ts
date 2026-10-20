"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type SalesRange="daily"|"weekly"|"monthly"|"yearly";

export type SalesMetric={
  revenue_toman:number;
  sales_count:number;
  average_sale_toman:number;
};

export type SalesSeriesPoint={
  key:string;
  start_at:string;
  end_at:string;
  revenue_toman:number;
  sales_count:number;
};

export type SalesBreakdownItem={
  key:string;
  revenue_toman:number;
  sales_count:number;
};

export type SalesAnalyticsResponse={
  scope:"admin"|"reseller";
  timezone:string;
  range:SalesRange;
  summary:{
    today:SalesMetric;
    week:SalesMetric;
    month:SalesMetric;
    year:SalesMetric;
  };
  selected:SalesMetric;
  series:SalesSeriesPoint[];
  breakdown:SalesBreakdownItem[];
  generated_at:string;
};

function errorMessage(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const row=payload as {detail?:unknown;message?:unknown};
    if(typeof row.detail==="string")return row.detail;
    if(typeof row.message==="string")return row.message;
  }
  return `API error ${status}`;
}

async function request(path:string):Promise<SalesAnalyticsResponse>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}${path}`,{
    headers:{Authorization:`Bearer ${token}`},
    cache:"no-store",
  });
  if(!response.ok){
    let payload:unknown=null;
    try{payload=await response.json();}catch{}
    throw new Error(errorMessage(payload,response.status));
  }
  return response.json() as Promise<SalesAnalyticsResponse>;
}

export const salesAnalyticsApi={
  admin:(range:SalesRange)=>request(`/v1/admin/sales-analytics?range=${encodeURIComponent(range)}`),
  reseller:(range:SalesRange)=>request(`/v1/reseller/sales-analytics?range=${encodeURIComponent(range)}`),
};
