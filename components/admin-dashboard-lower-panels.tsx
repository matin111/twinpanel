"use client";
import Link from "next/link";
import type {CSSProperties} from "react";
import type {AdminNode,RuntimeRow} from "../lib/admin-api";
import {dashboardPaymentAmount} from "../lib/admin-dashboard-revenue";
import styles from "./admin-dashboard-lower-panels.module.css";

type Pick=(fa:string,en:string)=>string;
export type SubscriptionBreakdown={total:number;active:number;expired:number;suspended:number;other:number};
const num=(n:number)=>Math.max(0,n).toLocaleString("fa-IR");
const percentage=(v:unknown):number|null=>{
 if(v==null||v==="")return null;
 const n=Number(v);return Number.isFinite(n)?Math.max(0,Math.min(100,n)):null;
};
const first=(row:RuntimeRow,...keys:string[])=>{
 for(const key of keys)if(row[key]!==undefined&&row[key]!==null)return row[key];
 return undefined;
};
const txt=(row:RuntimeRow,...keys:string[])=>String(first(row,...keys)??"");
const part=(n:number,total:number)=>total>0?Math.max(0,Math.min(100,n/total*100)):0;
const percentText=(n:number)=>n.toLocaleString("fa-IR",{maximumFractionDigits:1})+"٪";
const types=[
 {key:"active" as const,fa:"فعال",en:"Active",color:"#8f73fb"},
 {key:"expired" as const,fa:"منقضی",en:"Expired",color:"#e0a450"},
 {key:"suspended" as const,fa:"معلق",en:"Suspended",color:"#e4778a"},
 {key:"other" as const,fa:"سایر",en:"Other",color:"#30bfa8"}
];
export function SubscriptionAnalytics({breakdown,loaded,pick}:{
 breakdown:SubscriptionBreakdown|null;loaded:boolean;pick:Pick;
}){
 const total=breakdown?.total??0,missing=!loaded||!breakdown;
 let cursor=0;
 const sections=types.map(type=>{
   const value=breakdown?.[type.key]??0,p=part(value,total),start=cursor;cursor+=p;
   return {type,value,p,sector:type.color+" "+start.toFixed(3)+"% "+cursor.toFixed(3)+"%"};
 });
 const ring=total>0&&!missing?"conic-gradient("+sections.map(s=>s.sector).join(",")+")":"var(--line)";
 return <div className={styles.subscriptions}>
  <div className={styles.top}>
   <div className={styles.heading}><h3>{pick("وضعیت اشتراک‌ها","Subscription overview")}</h3></div>
   <Link href="/admin/subscriptions" className={styles.more}>{pick("مشاهده همه","View all")} ↗</Link>
  </div>
  <div className={styles.subBody}>
   <div className={styles.donut} style={{"--ring":ring} as CSSProperties} aria-label={pick("کل اشتراک‌ها","Subscriptions total")+": "+(missing?"—":num(total))} role="img">
    <div className={styles.donutInner}><span>{pick("کل اشتراک‌ها","All accounts")}</span><strong>{missing?"—":num(total)}</strong><small>{missing?pick("در حال دریافت","Loading"):percentText(part(breakdown!.active,total))+" "+pick("فعال","active")}</small></div>
   </div>
   <div className={styles.subRows}>{sections.map(s=><div key={s.type.key} className={styles.subRow} style={{"--accent":s.type.color} as CSSProperties}>
    <div className={styles.subRowTitle}><span><i/>{pick(s.type.fa,s.type.en)}</span><b>{missing?"—":num(s.value)}</b></div>
    <div className={styles.track}><i style={{width:(missing?0:s.p)+"%"}}/></div>
    <small>{missing?"—":percentText(s.p)}</small>
   </div>)}</div>
  </div>
 </div>;
}
type Tone="good"|"pending"|"bad"|"unknown";
function paymentStatus(row:RuntimeRow):{fa:string;en:string;tone:Tone;icon:string}{
 const status=txt(row,"status","payment_status").toLowerCase();
 if(["approved","verified","auto_verified","completed","paid","success"].includes(status))return {fa:status==="auto_verified"?"تأیید خودکار":"تأیید شده",en:status==="auto_verified"?"Auto verified":"Approved",tone:"good",icon:"✓"};
 if(["pending_payment","pending","review","needs_review","waiting"].includes(status))return {fa:"در انتظار پرداخت",en:"Pending",tone:"pending",icon:"◷"};
 if(["rejected","failed","canceled","cancelled"].includes(status))return {fa:"رد شده",en:"Rejected",tone:"bad",icon:"×"};
 return {fa:"نامشخص",en:"Unknown",tone:"unknown",icon:"·"};
}
function paymentTime(row:RuntimeRow,pick:Pick){
 const raw=txt(row,"verified_at","paid_at","submitted_at","created_at");
 const d=new Date(raw);
 return raw&&!Number.isNaN(d.getTime())?d.toLocaleString(pick("fa-IR","en-US"),{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}):"—";
}
export function RecentPaymentActivity({payments,loaded,pick}:{payments:RuntimeRow[];loaded:boolean;pick:Pick}){
 return <div className={styles.activity}>
  <div className={styles.top}><div className={styles.heading}><h3>{pick("فعالیت اخیر","Recent activity")}</h3></div><Link href="/admin/payments" className={styles.more}>{pick("همه تراکنش‌ها","All payments")} ↗</Link></div>
  <div className={styles.activityList}>{payments.length?payments.map((row,index)=>{
   const status=paymentStatus(row),amount=dashboardPaymentAmount(row),id=txt(row,"id")||String(index+1);
   return <Link key={id+"-"+index} href="/admin/payments" className={styles.event}>
    <span data-tone={status.tone} className={styles.eventIcon} aria-hidden="true">{status.icon}</span>
    <span className={styles.eventTitle}><b>{pick("تراکنش","Transaction")} <span dir="ltr">#{id}</span></b><small>{paymentTime(row,pick)}</small></span>
    <span className={styles.eventSummary}><b>{amount>0?num(amount)+" "+pick("تومان","toman"):pick("مبلغ نامشخص","Amount unavailable")}</b><span data-tone={status.tone} className={styles.eventBadge}>{pick(status.fa,status.en)}</span></span>
    <span className={styles.eventArrow} aria-hidden="true">↗</span>
   </Link>;
  }):<div className={styles.empty}>{loaded?pick("تراکنشی ثبت نشده","No payments returned"):pick("در حال دریافت تراکنش‌ها","Loading payments")}</div>}</div>
 </div>;
}
const flag=(code:string|undefined)=>{
 const v=(code||"").toUpperCase();
 return /^[A-Z]{2}$/.test(v)?String.fromCodePoint(...[...v].map(c=>127397+c.charCodeAt(0))):"🌐";
};
function ResourceMeter({name,value}:{name:string;value:number|null}){
 return <div className={styles.resource} data-level={value!=null&&value>=90?"danger":value!=null&&value>=75?"warning":"normal"}>
  <div><span>{name}</span><b>{value==null?"—":num(Math.round(value))+"%"}</b></div>
  <div className={styles.track} role="meter" aria-label={name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value==null?undefined:Math.round(value)} aria-valuetext={value==null?"No telemetry":num(Math.round(value))+"%"}><i style={{width:(value??0)+"%"}}/></div>
 </div>;
}
export function ServerFleetVisual({nodes,health,loaded,pick}:{
 nodes:AdminNode[];health:Record<number,RuntimeRow>;loaded:boolean;pick:Pick;
}){
 const onlineCount=nodes.filter(node=>String(node.status||"").toLowerCase()==="online").length;
 return <section className={styles.fleet}>
  <div className={styles.top}><div className={styles.heading}><h3>{pick("وضعیت سرورها","Server fleet")}</h3></div><div className={styles.fleetActions}><span className={styles.fleetSummary}><i/>{loaded?num(onlineCount)+" / "+num(nodes.length):"—"} {pick("نود آنلاین","nodes online")}</span><Link href="/admin/nodes" className={styles.more}>{pick("مدیریت سرورها","Manage servers")} ↗</Link></div></div>
  <div className={styles.nodeGrid}>{nodes.slice(0,6).map(n=>{
   const row=n as unknown as RuntimeRow,h=health[n.id]||{};
   const status=String(n.status||"").toLowerCase(),state=status==="online"?"online":status==="offline"?"offline":"unknown";
   const used=n.current_users,capacity=n.capacity_users;
   const cap=capacity!=null&&Number.isFinite(capacity)&&capacity>0;
   const use=used!=null&&Number.isFinite(used)&&used>=0;
   const fullness=cap&&use?part(used!,capacity!):null;
   const measured=(...keys:string[])=>percentage(first(h,...keys)??first(row,...keys));
   const cpu=measured("cpu_percent","cpu"),ram=measured("memory_percent","ram_percent","memory"),disk=measured("disk_percent","disk");
   const last=n.last_seen_at?new Date(n.last_seen_at):null;
   return <article key={n.id} className={styles.node} data-state={state}>
    <div className={styles.nodeHead}><span className={styles.country} aria-hidden="true">{flag(n.country_code)}</span><div className={styles.nodeName}><b>{n.name}</b><small dir="ltr">{n.public_ip||n.country_code||"—"}</small></div><span className={styles.nodeStatus}><i/>{state==="online"?pick("آنلاین","Online"):state==="offline"?pick("آفلاین","Offline"):pick("نامشخص","Unknown")}</span></div>
    <div className={styles.capacity}><div><span>{pick("کاربران نود","Node users")}</span><b dir="ltr">{use?num(used!):"—"} / {cap?num(capacity!):pick("نامحدود","Unlimited")}</b></div><div className={styles.track}><i style={{width:(fullness??0)+"%"}}/></div><small>{fullness==null?"—":percentText(fullness)}</small></div>
    <div className={styles.resources}><ResourceMeter name="CPU" value={cpu}/><ResourceMeter name="RAM" value={ram}/><ResourceMeter name="Disk" value={disk}/></div>
    <div className={styles.nodeFoot}>
      <span className={styles.nodeRole} data-role={String(n.node_type||"").toLowerCase()==="iran"?"iran":"exit"}>{String(n.node_type||"").toLowerCase()==="iran"?pick("ورودی ایران","Iran ingress"):String(n.node_type||"").toLowerCase()==="exit"?pick("سرور خروجی","Exit server"):pick("نود","Node")}</span>
      <span className={styles.lastSeen}>{last&&!Number.isNaN(last.getTime())?pick("آخرین گزارش","Last seen")+": "+last.toLocaleString(pick("fa-IR","en-US"),{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}):""}</span>
      <Link href="/admin/nodes" aria-label={pick("مدیریت نود","Manage node")+" "+n.name}>↗</Link>
    </div>
   </article>;
  })}{!nodes.length&&<div className={styles.empty}>{loaded?pick("نودی دریافت نشد","No nodes returned"):pick("در حال دریافت سرورها","Loading servers")}</div>}</div>
 </section>;
}
