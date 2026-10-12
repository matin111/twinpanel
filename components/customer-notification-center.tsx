"use client";

import {useEffect,useRef,useState} from "react";
import Link from "next/link";
import {customerApi,UserNotification} from "../lib/customer-api";
import {useCustomerSession} from "../lib/customer-session";
import {useI18n} from "../lib/i18n";

export function CustomerNotificationCenter(){
  const {token}=useCustomerSession();
  const {pick}=useI18n();
  const [open,setOpen]=useState(false);
  const [items,setItems]=useState<UserNotification[]>([]);
  const [loading,setLoading]=useState(false);
  const root=useRef<HTMLDivElement|null>(null);

  const load=async()=>{
    if(!token)return;
    setLoading(true);
    try{setItems(await customerApi.notifications(token,20));}catch{}
    finally{setLoading(false);}
  };

  useEffect(()=>{void load();},[token]);
  useEffect(()=>{
    const timer=window.setInterval(()=>void load(),30000);
    return()=>window.clearInterval(timer);
  },[token]);
  useEffect(()=>{
    if(!open)return;
    const close=(event:MouseEvent)=>{if(root.current&&!root.current.contains(event.target as Node))setOpen(false);};
    document.addEventListener("mousedown",close);
    return()=>document.removeEventListener("mousedown",close);
  },[open]);

  const unread=items.filter(x=>!x.is_read&&!x.read_at).length;
  const markOne=async(item:UserNotification)=>{
    if(!token||item.is_read||item.read_at)return;
    try{await customerApi.readNotification(token,item.id);setItems(rows=>rows.map(x=>x.id===item.id?{...x,is_read:true,read_at:new Date().toISOString()}:x));}catch{}
  };
  const markAll=async()=>{
    if(!token||unread===0)return;
    try{await customerApi.readAllNotifications(token);setItems(rows=>rows.map(x=>({...x,is_read:true,read_at:x.read_at||new Date().toISOString()})));}catch{}
  };

  return <div className="customerNotificationCenter" ref={root}>
    <button type="button" className={`customerNotificationBell ${unread?"hasUnread":""}`} onClick={()=>setOpen(v=>!v)} aria-label={pick("اعلان‌ها","Notifications")}>
      <span>◎</span>{unread>0&&<b>{unread>99?"99+":unread.toLocaleString("fa-IR")}</b>}
    </button>
    {open&&<div className="customerNotificationPopover">
      <header><div><b>{pick("اعلان‌ها","Notifications")}</b><small>{unread?`${unread.toLocaleString("fa-IR")} ${pick("خوانده‌نشده","unread")}`:pick("همه خوانده شده‌اند","All caught up")}</small></div>{unread>0&&<button type="button" onClick={()=>void markAll()}>{pick("خواندن همه","Mark all read")}</button>}</header>
      <div className="customerNotificationList">
        {loading&&items.length===0?<div className="customerNotificationEmpty">{pick("در حال دریافت...","Loading...")}</div>:items.length===0?<div className="customerNotificationEmpty">{pick("اعلانی وجود ندارد","No notifications")}</div>:items.slice(0,8).map(item=><button type="button" key={item.id} className={!item.is_read&&!item.read_at?"unread":""} onClick={()=>void markOne(item)}><i/><div><b>{item.title||pick("اعلان","Notification")}</b><p>{item.message||item.body||"—"}</p><small>{item.created_at?new Date(item.created_at).toLocaleString("fa-IR"):""}</small></div></button>)}
      </div>
      <footer><Link href="/panel/notifications" onClick={()=>setOpen(false)}>{pick("مشاهده همه اعلان‌ها","View all notifications")}</Link></footer>
    </div>}
  </div>;
}
