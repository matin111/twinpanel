"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useEffect,useRef,useState} from "react";
import {opsApi} from "../lib/admin-ops-api";
import {useI18n} from "../lib/i18n";
import {playNotificationSound,primeNotificationSound} from "../lib/notification-sound";

type AdminPanelNotification={id:number;event_key?:string|null;category?:string|null;source?:string|null;title?:string|null;message?:string|null;kind?:string|null;route?:string|null;created_at?:string|null;read_at?:string|null;is_read?:boolean};
type AdminNotificationPayload={unread_count?:number;items?:unknown};

function normalize(payload:unknown):{items:AdminPanelNotification[];unread:number}{
  if(!payload||typeof payload!=="object")return {items:[],unread:0};
  const root=payload as AdminNotificationPayload;
  const items=Array.isArray(root.items)?root.items.filter((item):item is AdminPanelNotification=>Boolean(item&&typeof item==="object"&&"id" in item)):[];
  const unread=Number.isFinite(Number(root.unread_count))?Math.max(0,Number(root.unread_count)||0):items.filter(item=>!item.is_read&&!item.read_at).length;
  return {items,unread};
}
function routeFor(item:AdminPanelNotification):string|null{const route=String(item.route||"").trim();if(!route)return null;if(route.startsWith("/"))return route;return `/admin/${route.replace(/^admin\//,"")}`;}
function notificationTitle(item:AdminPanelNotification,lang:"fa"|"en"):string{
  const raw=String(item.title||"").trim();if(lang==="fa")return raw||"اعلان";const source=String(item.source||"").toLowerCase();const category=String(item.category||"").toLowerCase();
  if(source==="tunnel")return "Tunnel status changed";if(source==="node")return "Node status changed";if(source==="payment"||category==="payment")return "Payment awaiting review";if(source==="security"||category==="security")return "Security notification";
  const known:Record<string,string>={"تغییر وضعیت تونل":"Tunnel status changed","تغییر وضعیت نود":"Node status changed","پرداخت در انتظار بررسی":"Payment awaiting review","هشدار امنیتی":"Security alert","اعلان امنیتی":"Security notification"};
  return known[raw]||raw||"Notification";
}
function notificationMessage(item:AdminPanelNotification,lang:"fa"|"en"):string{
  const raw=String(item.message||"").trim();if(!raw)return "—";if(lang==="fa")return raw;
  return raw.replace(/🌐\s*تغییر وضعیت شبکه/g,"🌐 Network status changed").replace(/🔀\s*تغییر وضعیت تونل/g,"🔀 Tunnel status changed").replace(/💳\s*پرداخت در انتظار بررسی/g,"💳 Payment awaiting review").replace(/🔐\s*(هشدار|اعلان) امنیتی/g,"🔐 Security notification").replace(/شناسه پرداخت:/g,"Payment ID:").replace(/شناسه سفارش:/g,"Order ID:").replace(/شناسه کاربر:/g,"User ID:").replace(/کاربر:/g,"User:").replace(/مبلغ:/g,"Amount:").replace(/روش:/g,"Method:").replace(/تومان/g,"Toman");
}

export function AdminNotificationCenter(){
  const {pick,lang}=useI18n();const router=useRouter();
  const [open,setOpen]=useState(false);const [items,setItems]=useState<AdminPanelNotification[]>([]);const [unread,setUnread]=useState(0);const [loading,setLoading]=useState(false);const [error,setError]=useState("");
  const root=useRef<HTMLDivElement|null>(null);const pulseSeeded=useRef(false);const latestSupportId=useRef(0);const latestReceiptId=useRef(0);const pulseBusy=useRef(false);const locale=lang==="fa"?"fa-IR":"en-US";

  const load=async()=>{setLoading(true);try{const next=normalize(await opsApi.panelNotifications());setItems(next.items);setUnread(next.unread);setError("");}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setLoading(false);}};
  const pulse=async()=>{
    if(pulseBusy.current)return;pulseBusy.current=true;
    try{
      const next=await opsApi.adminRealtimePulse();const supportId=Number(next.latest_support_message_id||0);const receiptId=Number(next.latest_receipt_id||0);
      if(!pulseSeeded.current){latestSupportId.current=supportId;latestReceiptId.current=receiptId;pulseSeeded.current=true;return;}
      if(receiptId>latestReceiptId.current){latestReceiptId.current=receiptId;void playNotificationSound("receipt");void load();}
      if(supportId>latestSupportId.current){latestSupportId.current=supportId;void playNotificationSound("message");}
    }catch{}finally{pulseBusy.current=false;}
  };

  useEffect(()=>{
    const prime=()=>void primeNotificationSound();window.addEventListener("pointerdown",prime,{once:true});window.addEventListener("keydown",prime,{once:true});
    void load();void pulse();
    const refresh=()=>{if(document.visibilityState==="visible"){void load();void pulse();}};
    const notificationTimer=window.setInterval(()=>{if(document.visibilityState==="visible")void load();},10000);
    const pulseTimer=window.setInterval(()=>{if(document.visibilityState==="visible")void pulse();},700);
    window.addEventListener("focus",refresh);document.addEventListener("visibilitychange",refresh);
    return()=>{window.clearInterval(notificationTimer);window.clearInterval(pulseTimer);window.removeEventListener("focus",refresh);document.removeEventListener("visibilitychange",refresh);window.removeEventListener("pointerdown",prime);window.removeEventListener("keydown",prime);};
  },[]);

  useEffect(()=>{if(!open)return;const close=(event:MouseEvent)=>{if(root.current&&!root.current.contains(event.target as Node))setOpen(false);};const escape=(event:KeyboardEvent)=>{if(event.key==="Escape")setOpen(false);};document.addEventListener("mousedown",close);document.addEventListener("keydown",escape);return()=>{document.removeEventListener("mousedown",close);document.removeEventListener("keydown",escape);};},[open]);

  const markOne=async(item:AdminPanelNotification)=>{if(item.is_read||item.read_at)return;try{await opsApi.panelNotificationRead(item.id);setItems(rows=>rows.map(row=>row.id===item.id?{...row,is_read:true,read_at:new Date().toISOString()}:row));setUnread(value=>Math.max(0,value-1));}catch{}};
  const openItem=async(item:AdminPanelNotification)=>{await markOne(item);const target=routeFor(item);if(target){setOpen(false);router.push(target);}};
  const markAll=async()=>{if(!unread)return;try{await opsApi.panelNotificationsReadAll();const now=new Date().toISOString();setItems(rows=>rows.map(row=>({...row,is_read:true,read_at:row.read_at||now})));setUnread(0);}catch{}};
  const toggleOpen=()=>{setOpen(value=>{const next=!value;if(next)void load();return next;});};

  return <div className="customerNotificationCenter adminNotificationCenter" ref={root}>
    <button type="button" className={`customerNotificationBell adminNotificationBell ${unread?"hasUnread":""}`} onClick={toggleOpen} aria-label={pick("اعلان‌های مدیریت","Admin notifications")} aria-expanded={open} title={pick("اعلان‌ها","Notifications")}><span aria-hidden="true">◎</span>{unread>0&&<b>{unread>99?"99+":unread.toLocaleString(locale)}</b>}</button>
    {open&&<div className="customerNotificationPopover adminNotificationPopover" role="dialog" aria-label={pick("اعلان‌های مدیریت","Admin notifications")}><header><div><b>{pick("اعلان‌های مدیریت","Admin notifications")}</b><small>{unread?`${unread.toLocaleString(locale)} ${pick("خوانده‌نشده","unread")}`:pick("همه خوانده شده‌اند","All caught up")}</small></div>{unread>0&&<button type="button" onClick={()=>void markAll()}>{pick("خواندن همه","Mark all read")}</button>}</header><div className="customerNotificationList">
      {loading&&items.length===0?<div className="customerNotificationEmpty">{pick("در حال دریافت...","Loading...")}</div>:error&&items.length===0?<div className="customerNotificationEmpty"><span>{pick("دریافت اعلان‌ها ناموفق بود","Could not load notifications")}</span><button type="button" className="ghost" onClick={()=>void load()}>{pick("تلاش دوباره","Retry")}</button></div>:items.length===0?<div className="customerNotificationEmpty">{pick("اعلانی وجود ندارد","No notifications")}</div>:items.slice(0,10).map(item=><button type="button" key={item.id} className={!item.is_read&&!item.read_at?"unread":""} onClick={()=>void openItem(item)}><i/><div><b>{notificationTitle(item,lang)}</b><p>{notificationMessage(item,lang)}</p><small>{item.created_at?new Date(item.created_at).toLocaleString(locale):""}</small></div></button>)}
    </div><footer><Link href="/admin/notifications" onClick={()=>setOpen(false)}>{pick("مشاهده همه اعلان‌ها","View all notifications")}</Link></footer></div>}
  </div>;
}
