"use client";

import Link from "next/link";
import {useEffect,useRef,useState} from "react";
import {resellerApi} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";
import {resellerDate,resellerNotificationDisplay,resellerNumber} from "../lib/reseller-i18n";

type ResellerNotification={
  id:number;
  title?:string|null;
  message?:string|null;
  kind?:string|null;
  source?:string|null;
  route?:string|null;
  created_at?:string|null;
  read_at?:string|null;
  is_read?:boolean;
};

function normalize(payload:unknown):ResellerNotification[]{
  if(!payload||typeof payload!=="object")return [];
  const items=(payload as {items?:unknown}).items;
  if(!Array.isArray(items))return [];
  return items.filter((item):item is ResellerNotification=>Boolean(item&&typeof item==="object"&&"id" in item));
}

export function ResellerNotificationCenter(){
  const {lang,pick}=useI18n();
  const [open,setOpen]=useState(false);
  const [items,setItems]=useState<ResellerNotification[]>([]);
  const [loading,setLoading]=useState(false);
  const root=useRef<HTMLDivElement|null>(null);

  const load=async()=>{
    setLoading(true);
    try{setItems(normalize(await resellerApi.notifications()));}
    catch{}
    finally{setLoading(false);}
  };

  useEffect(()=>{
    void load();
    const refresh=()=>{if(document.visibilityState==="visible")void load();};
    const timer=window.setInterval(refresh,5000);
    window.addEventListener("focus",refresh);
    document.addEventListener("visibilitychange",refresh);
    return()=>{
      window.clearInterval(timer);
      window.removeEventListener("focus",refresh);
      document.removeEventListener("visibilitychange",refresh);
    };
  },[]);
  useEffect(()=>{
    if(!open)return;
    const close=(event:MouseEvent)=>{
      if(root.current&&!root.current.contains(event.target as Node))setOpen(false);
    };
    const escape=(event:KeyboardEvent)=>{if(event.key==="Escape")setOpen(false);};
    document.addEventListener("mousedown",close);
    document.addEventListener("keydown",escape);
    return()=>{
      document.removeEventListener("mousedown",close);
      document.removeEventListener("keydown",escape);
    };
  },[open]);

  const unread=items.filter(item=>!item.is_read&&!item.read_at).length;

  const markOne=async(item:ResellerNotification)=>{
    if(item.is_read||item.read_at)return;
    try{
      await resellerApi.notificationMarkRead(item.id);
      setItems(rows=>rows.map(row=>row.id===item.id?{...row,is_read:true,read_at:new Date().toISOString()}:row));
    }catch{}
  };

  const markAll=async()=>{
    if(!unread)return;
    try{
      await resellerApi.notificationReadAll();
      setItems(rows=>rows.map(row=>({...row,is_read:true,read_at:row.read_at||new Date().toISOString()})));
    }catch{}
  };

  const toggleOpen=()=>{
    setOpen(value=>{
      const next=!value;
      if(next)void load();
      return next;
    });
  };

  return <div className="customerNotificationCenter resellerNotificationCenter" ref={root}>
    <button
      type="button"
      className={`customerNotificationBell ${unread?"hasUnread":""}`}
      onClick={toggleOpen}
      aria-label={pick("اعلان‌ها","Notifications")}
      aria-expanded={open}
    >
      <span>◎</span>
      {unread>0&&<b>{unread>99?"99+":resellerNumber(lang,unread)}</b>}
    </button>

    {open&&<div className="customerNotificationPopover">
      <header>
        <div>
          <b>{pick("اعلان‌های نمایندگی","Reseller notifications")}</b>
          <small>{unread?`${resellerNumber(lang,unread)} ${pick("خوانده‌نشده","unread")}`:pick("همه خوانده شده‌اند","All caught up")}</small>
        </div>
        {unread>0&&<button type="button" onClick={()=>void markAll()}>{pick("خواندن همه","Mark all read")}</button>}
      </header>

      <div className="customerNotificationList">
        {loading&&items.length===0
          ?<div className="customerNotificationEmpty">{pick("در حال دریافت...","Loading...")}</div>
          :items.length===0
            ?<div className="customerNotificationEmpty">{pick("اعلانی وجود ندارد","No notifications")}</div>
            :items.slice(0,8).map(item=>{
              const display=resellerNotificationDisplay(lang,item);
              return <button
                type="button"
                key={item.id}
                className={!item.is_read&&!item.read_at?"unread":""}
                onClick={()=>void markOne(item)}
              >
                <i/>
                <div>
                  <b>{display.title}</b>
                  <p>{display.message}</p>
                  <small>{item.created_at?resellerDate(lang,item.created_at):""}</small>
                </div>
              </button>;
            })}
      </div>

      <footer><Link href="/reseller/notifications" onClick={()=>setOpen(false)}>{pick("مشاهده همه اعلان‌ها","View all notifications")}</Link></footer>
    </div>}
  </div>;
}
