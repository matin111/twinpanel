"use client";

import {useEffect,useState} from "react";

const STORAGE_KEY="twinpanel.admin.support.lastSeenInboundMessageId";
const ADMIN_PULSE_EVENT="twinpanel:admin-pulse";

type Pulse={latest_support_message_id?:number;support_unread_count?:number};

function readSeen():number|null{
  try{
    const raw=localStorage.getItem(STORAGE_KEY);
    if(raw===null)return null;
    const value=Number(raw);
    return Number.isFinite(value)&&value>=0?Math.floor(value):null;
  }catch{return null;}
}
function writeSeen(value:number){
  try{localStorage.setItem(STORAGE_KEY,String(Math.max(0,Math.floor(value))));}catch{}
}

export function SupportUnreadBadge({active}:{active:boolean}){
  const [count,setCount]=useState(0);

  useEffect(()=>{
    const onPulse=(event:Event)=>{
      const payload=(event as CustomEvent<Pulse>).detail||{};
      const latest=Math.max(0,Number(payload.latest_support_message_id)||0);
      const seen=readSeen();

      if(seen===null){writeSeen(latest);setCount(0);return;}
      if(active){if(latest>seen)writeSeen(latest);setCount(0);return;}
      setCount(Math.max(0,Number(payload.support_unread_count)||0));
    };

    window.addEventListener(ADMIN_PULSE_EVENT,onPulse as EventListener);
    return()=>window.removeEventListener(ADMIN_PULSE_EVENT,onPulse as EventListener);
  },[active]);

  if(count<=0)return null;
  return <span aria-label={`${count} unread support messages`} style={{marginInlineStart:"auto",minWidth:20,height:20,padding:"0 6px",borderRadius:999,display:"inline-flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:900,lineHeight:1,color:"#fff",background:"#ef4444",boxShadow:"0 0 0 2px color-mix(in srgb, var(--surface) 80%, transparent)"}}>{count>99?"99+":count}</span>;
}
