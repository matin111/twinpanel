"use client";

import Link from "next/link";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {resellerApi} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";


type NotificationRow={
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

type NotificationPayload={
  unread_count?:number;
  items?:NotificationRow[];
};

function asPayload(value:unknown):NotificationPayload{
  if(!value||typeof value!=="object")return {};
  return value as NotificationPayload;
}

function dateText(value?:string|null){
  if(!value)return "—";
  const date=new Date(value);
  return Number.isNaN(date.getTime())?value:date.toLocaleString("fa-IR");
}

function tone(kind?:string|null):"ok"|"warn"|"bad"|"violet"{
  const value=String(kind||"").toLowerCase();
  if(["success","ok","approved"].includes(value))return "ok";
  if(["error","danger","failed","rejected"].includes(value))return "bad";
  if(["warning","warn"].includes(value))return "warn";
  return "violet";
}

function sourceTitle(source:string,pick:(fa:string,en:string)=>string){
  if(source==="bot_wallet")return pick("کیف پول ربات","Bot wallet");
  if(source==="bot_order")return pick("سفارش ربات","Bot order");
  if(source==="subscription")return pick("اشتراک","Subscription");
  return pick("سیستم","System");
}

function routeHref(value?:string|null){
  const raw=String(value||"").trim();
  if(!raw)return "";
  if(raw.startsWith("/"))return raw;
  return `/reseller/${raw.replace(/^reseller\//,"")}`;
}

export function ResellerNotificationsLive(){
  const {pick}=useI18n();
  const [items,setItems]=useState<NotificationRow[]>([]);
  const [unread,setUnread]=useState(0);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [lastUpdate,setLastUpdate]=useState<Date|null>(null);
  const firstLoad=useRef(true);
  const knownIds=useRef<Set<number>>(new Set());

  const load=useCallback(async(silent=false)=>{
    if(!silent)setLoading(true);
    try{
      const payload=asPayload(await resellerApi.notifications());
      const rows=Array.isArray(payload.items)?payload.items:[];

      if(!firstLoad.current){
        const incoming=rows.filter(row=>!knownIds.current.has(Number(row.id)));
        if(incoming.length>0&&typeof window!=="undefined"&&"Notification" in window&&Notification.permission==="granted"){
          const newest=incoming[0];
          try{
            new Notification(newest.title||pick("اعلان جدید نمایندگی","New reseller notification"),{
              body:newest.message||"",
              tag:`reseller-notification-${newest.id}`,
            });
          }catch{}
        }
      }

      knownIds.current=new Set(rows.map(row=>Number(row.id)).filter(Boolean));
      firstLoad.current=false;
      setItems(rows);
      setUnread(Number(payload.unread_count||0));
      setLastUpdate(new Date());
      setError("");
    }catch(reason){
      if(!silent)setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      if(!silent)setLoading(false);
    }
  },[pick]);

  useEffect(()=>{
    void load(false);

    const refresh=()=>{
      if(document.visibilityState==="visible")void load(true);
    };

    const timer=window.setInterval(refresh,4000);
    window.addEventListener("focus",refresh);
    document.addEventListener("visibilitychange",refresh);

    return()=>{
      window.clearInterval(timer);
      window.removeEventListener("focus",refresh);
      document.removeEventListener("visibilitychange",refresh);
    };
  },[load]);

  const readOne=async(id:number)=>{
    if(busy)return;
    setBusy(true);setError("");
    try{
      await resellerApi.notificationMarkRead(id);
      await load(true);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy(false);
    }
  };

  const readAll=async()=>{
    if(busy||unread===0)return;
    setBusy(true);setError("");
    try{
      await resellerApi.notificationReadAll();
      await load(true);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy(false);
    }
  };

  const reviewReceipts=useMemo(
    ()=>items.filter(row=>!row.is_read&&["bot_wallet","bot_order"].includes(String(row.source||""))).length,
    [items]
  );

  return <PortalShell type="reseller" active="/reseller/notifications">
    <div className="page reseller-parity-page reseller-notifications-live">
      <div className="page-head">
        <div>
          <h1>{pick("اعلان‌ها","Notifications")}</h1>
          <small>
            {pick(
              "رسیدهای خرید، تمدید و شارژ کیف پول ربات به‌صورت خودکار اینجا نمایش داده می‌شوند.",
              "Bot purchase, renewal and wallet top-up receipts appear here automatically."
            )}
          </small>
        </div>
        <div className="action-row">
          <Badge tone="ok">{pick("زنده · هر ۴ ثانیه","Live · 4s")}</Badge>
          <button className="ghost" disabled={loading||busy} onClick={()=>void load(false)}>
            {pick("بروزرسانی","Refresh")}
          </button>
          <button className="primary" disabled={busy||unread===0} onClick={()=>void readAll()}>
            {pick("خواندن همه","Mark all read")}
          </button>
        </div>
      </div>

      {error&&<div className="runtime-error">{error}</div>}
      {loading&&items.length===0&&<div className="runtime-loading">{pick("در حال دریافت اعلان‌ها...","Loading notifications...")}</div>}

      <div className="stats">
        <Stat label={pick("خوانده‌نشده","Unread")} value={String(unread)}/>
        <Stat label={pick("رسید نیازمند توجه","Receipts needing attention")} value={String(reviewReceipts)}/>
        <Stat label={pick("کل نمایش‌داده‌شده","Shown")} value={String(items.length)}/>
      </div>

      <Card>
        <div className="card-head">
          <div>
            <b>{pick("مرکز اعلان نمایندگی","Reseller notification center")}</b>
            <small>
              {lastUpdate
                ?`${pick("آخرین بروزرسانی","Last update")}: ${lastUpdate.toLocaleTimeString("fa-IR")}`
                :pick("در انتظار اولین بروزرسانی","Waiting for first refresh")}
            </small>
          </div>
        </div>

        <div className="module-list">
          {items.map(row=>{
            const href=routeHref(row.route);
            const isRead=Boolean(row.is_read||row.read_at);
            const source=String(row.source||"");

            return <div className={`module-row reseller-notification-row ${isRead?"is-read":""}`} key={row.id}>
              <div className="grow">
                <div className="action-row">
                  <b>{row.title||pick("اعلان","Notification")}</b>
                  <Badge tone={tone(row.kind)}>{sourceTitle(source,pick)}</Badge>
                  {!isRead&&<Badge tone="violet">{pick("جدید","New")}</Badge>}
                </div>
                <p>{row.message||"—"}</p>
                <small>{dateText(row.created_at)}</small>
              </div>

              <div className="action-row">
                {!isRead&&<button className="mini-btn" disabled={busy} onClick={()=>void readOne(row.id)}>
                  {pick("خواندم","Mark read")}
                </button>}
                {href&&<Link className="mini-btn" href={href}>
                  {source==="bot_wallet"
                    ?pick("بررسی شارژ","Review top-up")
                    :source==="bot_order"
                      ?pick("بررسی سفارش","Review order")
                      :pick("باز کردن","Open")}
                </Link>}
              </div>
            </div>;
          })}

          {!items.length&&!loading&&<div className="runtime-empty">
            {pick("در حال حاضر اعلانی وجود ندارد.","There are no notifications right now.")}
          </div>}
        </div>
      </Card>
    </div>
  </PortalShell>;
}
