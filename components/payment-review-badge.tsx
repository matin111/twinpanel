"use client";

import {useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

type ReviewSummary={
  needs_review:number;
  purchase_review:number;
  receipt_review:number;
  wallet_review:number;
};

const badgeStyle:React.CSSProperties={
  marginInlineStart:"auto",
  minWidth:22,
  height:22,
  padding:"0 6px",
  borderRadius:999,
  display:"inline-flex",
  alignItems:"center",
  justifyContent:"center",
  flex:"0 0 auto",
  fontSize:11,
  fontWeight:800,
  lineHeight:1,
  color:"#fff",
  background:"#dc2626",
  boxShadow:"0 0 0 2px rgba(220,38,38,.16)",
};

async function fetchSummary():Promise<ReviewSummary>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(
    `${API_BASE}/v1/payments/admin/review-summary`,
    {
      headers:{Authorization:`Bearer ${token}`},
      cache:"no-store",
    },
  );
  if(!response.ok)throw new Error(`API ${response.status}`);
  return response.json() as Promise<ReviewSummary>;
}

export function PaymentReviewBadge(){
  const [count,setCount]=useState(0);

  useEffect(()=>{
    let alive=true;

    const refresh=async()=>{
      try{
        const summary=await fetchSummary();
        if(alive)setCount(Math.max(0,Number(summary.needs_review||0)));
      }catch{
        // Keep the last known count on transient errors so navigation never
        // waits on the badge and a short API outage does not make it flicker.
      }
    };

    const onVisible=()=>{
      if(document.visibilityState==="visible")void refresh();
    };

    void refresh();
    const timer=window.setInterval(()=>void refresh(),10000);
    window.addEventListener("focus",refresh);
    document.addEventListener("visibilitychange",onVisible);

    return()=>{
      alive=false;
      window.clearInterval(timer);
      window.removeEventListener("focus",refresh);
      document.removeEventListener("visibilitychange",onVisible);
    };
  },[]);

  if(count<=0)return null;

  return <span
    className="nav-review-count"
    style={badgeStyle}
    title={`${count} پرداخت نیازمند بررسی`}
    aria-label={`${count} پرداخت نیازمند بررسی`}
  >{count>99?"99+":count}</span>;
}
