"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type AuditEvent={
  id:number;actor:string;actor_id:string;action:string;
  subject_type:string;subject_id:string;created_at:string|null;
  success:boolean;details:Record<string,unknown>;
};
type ActivityPage={items:AuditEvent[];total:number;limit:number;offset:number};
type Stats={recorded_total:number;wallet_adjustments:number;subscription_changes:number};
const titles:Record<string,string>={
  wallet_credit:"افزایش کیف پول",wallet_debit:"کاهش کیف پول",
  subscription_renew_or_reset:"تمدید / تغییر سهمیه اشتراک",
  subscription_usage_period_reset:"ریست حجم مصرفی",
};
const pretty=(value:unknown)=>value==null?"—":typeof value==="boolean"?(value?"بله":"خیر"):String(value);
const fmt=(value:string|null)=>value?new Date(value).toLocaleString("fa-IR"):"—";
const money=(value:unknown)=>Number(value||0).toLocaleString("fa-IR")+" تومان";
const bytes=(value:unknown)=>value==null?"—":(Number(value)/1073741824).toLocaleString("fa-IR",{maximumFractionDigits:2})+" GB";

export function AdminActivityPopup(){
  const {pick}=useI18n();
  const [open,setOpen]=useState(false);
  const [filter,setFilter]=useState("all");
  const [page,setPage]=useState(0);
  const [data,setData]=useState<ActivityPage|null>(null);
  const [stats,setStats]=useState<Stats|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{
    if(!open)return;
    let cancelled=false;
    const token=getCustomerToken();
    if(!token){setError("AUTH_REQUIRED");return;}
    setLoading(true);setError("");
    const headers={Authorization:`Bearer ${token}`};
    Promise.all([
      fetch(`${API_BASE}/v1/admin/activity?category=${filter}&limit=30&offset=${page*30}`,{headers,cache:"no-store"}),
      fetch(`${API_BASE}/v1/admin/activity/stats`,{headers,cache:"no-store"}),
    ]).then(async([a,b])=>{
      if(!a.ok||!b.ok)throw new Error("دریافت تاریخچه ممکن نشد");
      const [history,summary]=await Promise.all([a.json(),b.json()]);
      if(!cancelled){setData(history);setStats(summary);}
    }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:String(e));})
      .finally(()=>{if(!cancelled)setLoading(false);});
    return()=>{cancelled=true;};
  },[open,filter,page]);
  const close=()=>setOpen(false);
  return <>
    <button type="button" className="ghost" onClick={()=>setOpen(true)}
      style={{whiteSpace:"nowrap",padding:"7px 11px",fontSize:12}}
      title={pick("آمار و تاریخچه عملیات دستی ادمین","Admin activity and stats")}>
      ◷ {pick("آمار و تاریخچه","Activity")}
    </button>
    {open&&createPortal(
      <div className="runtime-modal tp-admin-audit-popup" role="dialog" aria-modal="true"
        aria-label={pick("آمار و تاریخچه ادمین","Admin activity and statistics")} dir="rtl"
        style={{position:"fixed",inset:0,zIndex:100000,display:"grid",placeItems:"center",padding:14}}>
        <button type="button" className="runtime-modal-bg" onClick={close} aria-label={pick("بستن","Close")}/>
        <div className="runtime-modal-card" style={{position:"relative",width:"min(790px,96vw)",maxWidth:"100%",maxHeight:"88vh",overflowY:"auto",padding:18}}>
          <div className="card-head"><div><b>{pick("آمار و تاریخچه عملیات ادمین","Admin activity and history")}</b>
            <small>{pick("آمار عملیات ثبت‌شده؛ نه مجموع کارهای گذشته که ثبت نشده‌اند","Recorded actions only; historical unlogged actions are excluded")}</small></div>
            <button className="icon-button" type="button" onClick={close}>×</button></div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:8,margin:"12px 0"}}>
            {[
              [pick("کل رویدادها","Recorded actions"),stats?.recorded_total],
              [pick("تغییر کیف پول","Wallet changes"),stats?.wallet_adjustments],
              [pick("تغییر اشتراک","Subscription changes"),stats?.subscription_changes],
            ].map(([label,value],i)=><div key={i} style={{padding:10,border:"1px solid var(--line)",borderRadius:12,display:"grid",gap:5}}>
              <small>{label}</small><strong>{value==null?"—":Number(value).toLocaleString("fa-IR")}</strong>
            </div>)}
          </div>
          <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap",marginBottom:12}}>
            <label>{pick("فیلتر","Filter")}: <select value={filter} onChange={e=>{setFilter(e.target.value);setPage(0);}}>
              <option value="all">{pick("همه","All")}</option>
              <option value="wallet">{pick("کیف پول","Wallet")}</option>
              <option value="subscription">{pick("اشتراک‌ها","Subscriptions")}</option>
              <option value="other">{pick("سایر","Other")}</option>
            </select></label>
            <button className="ghost" type="button" disabled={loading} onClick={()=>{setOpen(false);setTimeout(()=>setOpen(true),0);}}>{pick("بروزرسانی","Refresh")}</button>
          </div>
          {error&&<div className="runtime-error">{error}</div>}
          {loading&&<small>{pick("در حال دریافت…","Loading…")}</small>}
          {!loading&&!error&&data?.items.length===0&&<div className="runtime-empty">{pick("هنوز عملیاتی برای این فیلتر ثبت نشده است","No recorded activity for this filter")}</div>}
          <div style={{display:"grid",gap:9}}>
            {(data?.items||[]).map(item=><article key={item.id} style={{border:"1px solid var(--line)",borderRadius:12,padding:12,display:"grid",gap:5}}>
              <div style={{display:"flex",justifyContent:"space-between",gap:8,flexWrap:"wrap"}}>
                <strong>{titles[item.action]||item.action}</strong><small>{fmt(item.created_at)}</small>
              </div>
              <small>{pick("ادمین","Admin")}: {item.actor} · {item.subject_type} #{item.subject_id}</small>
              {item.action.startsWith("wallet_")&&<small>
                {pick("تغییر","Change")}: {money(item.details.amount_toman)} · {money(item.details.previous_balance_toman)} ← {money(item.details.new_balance_toman)}
              </small>}
              {item.action.startsWith("subscription_")&&<small>
                {pick("مصرف قبلی","Previous usage")}: {bytes(item.details.previous_usage_bytes)}
                {item.details.new_traffic_limit_bytes!=null?" · "+pick("حجم جدید","New quota")+": "+bytes(item.details.new_traffic_limit_bytes):""}
              </small>}
              {item.details.note&&<small>{pick("توضیح","Note")}: {pretty(item.details.note)}</small>}
            </article>)}
          </div>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:8,marginTop:12}}>
            <small>{pick("تعداد","Total")}: {(data?.total||0).toLocaleString("fa-IR")}</small>
            <div className="row-actions">
              <button type="button" className="ghost" disabled={page===0||loading} onClick={()=>setPage(v=>Math.max(0,v-1))}>{pick("قبلی","Previous")}</button>
              <button type="button" className="ghost" disabled={loading||!data||(page+1)*30>=data.total} onClick={()=>setPage(v=>v+1)}>{pick("بعدی","Next")}</button>
            </div>
          </div>
        </div>
      </div>,document.body)}
  </>;
}
