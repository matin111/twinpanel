"use client";

import {useEffect,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

const STORAGE_KEY="twinpanel.admin.support.lastSeenInboundMessageId";

type Pulse={latest_support_message_id?:number;support_unread_count?:number};

function readSeen():number|null{
  try{
    const raw=localStorage.getItem(STORAGE_KEY);
    if(raw===null)return null;
    const value=Number(raw);
    return Number.isFinite(value)&&value>=0?value:null;
  }catch{return null;}
}

function writeSeen(value:number){
  try{localStorage.setItem(STORAGE_KEY,String(Math.max(0,Math.floor(value))));}catch{}
}

export function SupportUnreadBadge({active}:{active:boolean}){
  const [count,setCount]=useState(0);
  const busy=useRef(false);

  useEffect(()=>{
    let stopped=false;
    const poll=async()=>{
      if(stopped||busy.current||document.visibilityState==="hidden")return;
      const token=getCustomerToken();
      if(!token){setCount(0);return;}
      busy.current=true;
      try{
        const seen=readSeen();
        const after=Math.max(0,seen??0);
        const response=await fetch(`${API_BASE}/v1/admin/panel-notifications/pulse?support_after_id=${after}`,{
          headers:{Authorization:`Bearer ${token}`},cache:"no-store",signal:AbortSignal.timeout(3000),
        });
        if(!response.ok)return;
        const payload=await response.json() as Pulse;
        if(stopped)return;
        const latest=Math.max(0,Number(payload.latest_support_message_id)||0);
        if(seen===null){writeSeen(latest);setCount(0);return;}
        if(active){if(latest>seen)writeSeen(latest);setCount(0);return;}
        setCount(Math.max(0,Number(payload.support_unread_count)||0));
      }catch{}finally{busy.current=false;}
    };
    void poll();
    const timer=window.setInterval(()=>void poll(),1000);
    const onFocus=()=>void poll();
    const onVisibility=()=>{if(document.visibilityState==="visible")void poll();};
    window.addEventListener("focus",onFocus);
    document.addEventListener("visibilitychange",onVisibility);
    return()=>{stopped=true;clearInterval(timer);window.removeEventListener("focus",onFocus);document.removeEventListener("visibilitychange",onVisibility);};
  },[active]);

  if(count<=0)return null;
  return <span aria-label={`${count} unread support messages`} style={{marginInlineStart:"auto",minWidth:20,height:20,padding:"0 6px",borderRadius:999,display:"inline-flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:900,lineHeight:1,color:"#fff",background:"#ef4444",boxShadow:"0 0 0 2px color-mix(in srgb, var(--surface) 80%, transparent)"}}>{count>99?"99+":count}</span>;
}
