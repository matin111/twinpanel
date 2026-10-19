"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,AdminStats,AdminTunnel,DashboardSummary,RuntimeRow} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const protocolLabel=(key:string)=>({cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray",xray:"V2Ray / Xray"} as Record<string,string>)[key.toLowerCase()]||key;
const valueOf=(row:RuntimeRow,...keys:string[])=>{for(const key of keys){const value=row[key];if(value!==undefined&&value!==null)return value;}return undefined;};
const numberOf=(row:RuntimeRow,...keys:string[])=>{const raw=valueOf(row,...keys);const parsed=Number(String(raw??0).replace(/[,٬]/g,""));return Number.isFinite(parsed)?parsed:0;};
const stringOf=(row:RuntimeRow,...keys:string[])=>String(valueOf(row,...keys)??"");
const successfulPayment=(row:RuntimeRow)=>["paid","approved","verified","completed","fulfilled","success","successful"].includes(stringOf(row,"status","payment_status").toLowerCase());

function revenueSeries(payments:RuntimeRow[]){
  const now=new Date();
  const rows=Array.from({length:30},(_,index)=>{
    const date=new Date(now);date.setHours(0,0,0,0);date.setDate(date.getDate()-(29-index));
    return {key:date.toISOString().slice(0,10),date,value:0};
  });
  const map=new Map(rows.map(item=>[item.key,item]));
  for(const payment of payments){
    if(!successfulPayment(payment))continue;
    const raw=stringOf(payment,"verified_at","paid_at","submitted_at","created_at");
    if(!raw)continue;
    const date=new Date(raw);if(Number.isNaN(date.getTime()))continue;
    const key=new Date(date.getFullYear(),date.getMonth(),date.getDate()).toISOString().slice(0,10);
    const item=map.get(key);if(!item)continue;
    item.value+=numberOf(payment,"amount_toman","amount","final_amount_toman","total_toman");
  }
  return rows;
}

function chartGeometry(series:ReturnType<typeof revenueSeries>){
  const max=Math.max(1,...series.map(item=>item.value));
  const points=series.map((item,index)=>{
    const x=(index/(series.length-1))*600;
    const y=180-(item.value/max)*145;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return {points,fill:`0,200 ${points} 600,200`};
}

function paymentTitle(row:RuntimeRow,pick:(fa:string,en:string)=>string){
  const id=stringOf(row,"id")||"—";
  const amount=numberOf(row,"amount_toman","amount","final_amount_toman","total_toman");
  return `${pick("پرداخت","Payment")} #${id}${amount?` · ${money(amount)}`:""}`;
}

export function AdminDashboardRuntime(){
  const {pick}=useI18n();
  const [stats,setStats]=useState<AdminStats|null>(null);
  const [summary,setSummary]=useState<DashboardSummary|null>(null);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [subscriptions,setSubscriptions]=useState<RuntimeRow[]>([]);
  const [payments,setPayments]=useState<RuntimeRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const result=await Promise.allSettled([
      adminApi.stats(),adminApi.dashboard(),adminApi.nodes(),adminApi.tunnels(),adminApi.subscriptions(),adminApi.payments()
    ]);
    if(result[0].status==="fulfilled")setStats(result[0].value);
    if(result[1].status==="fulfilled")setSummary(result[1].value);
    if(result[2].status==="fulfilled")setNodes(result[2].value);
    if(result[3].status==="fulfilled")setTunnels(result[3].value);
    if(result[4].status==="fulfilled")setSubscriptions(result[4].value);
    if(result[5].status==="fulfilled")setPayments(result[5].value);
    const failed=result.find(x=>x.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };
  useEffect(()=>{void load();},[]);

  const protocols=useMemo(()=>Object.entries(summary?.protocols||{}),[summary]);
  const onlineTunnels=tunnels.filter(t=>String(t.status).toLowerCase()==="online").length;
  const subStats=useMemo(()=>{
    const counts={active:0,expired:0,suspended:0,pending:0,other:0};
    for(const row of subscriptions){
      const status=stringOf(row,"status").toLowerCase();
      if(status in counts)(counts as Record<string,number>)[status]++;
      else counts.other++;
    }
    const total=subscriptions.length;
    const activePct=total?Math.round((counts.active/total)*100):0;
    const expiredPct=total?Math.round((counts.expired/total)*100):0;
    return {...counts,total,activePct,expiredPct,otherPct:Math.max(0,100-activePct-expiredPct)};
  },[subscriptions]);
  const sales=useMemo(()=>revenueSeries(payments),[payments]);
  const chart=useMemo(()=>chartGeometry(sales),[sales]);
  const recentPayments=useMemo(()=>[...payments].sort((a,b)=>{
    const ad=Date.parse(stringOf(a,"verified_at","paid_at","submitted_at","created_at"))||0;
    const bd=Date.parse(stringOf(b,"verified_at","paid_at","submitted_at","created_at"))||0;
    return bd-ad;
  }).slice(0,4),[payments]);
  const donutStyle={background:`conic-gradient(#8b5cf6 0 ${subStats.activePct}%,#f59e0b ${subStats.activePct}% ${subStats.activePct+subStats.expiredPct}%,#2dd4bf ${subStats.activePct+subStats.expiredPct}% 100%)`};

  return <Shell active="/admin"><div className="page admin-dashboard-runtime">
    <div className="page-head"><div><h1>{pick("داشبورد مدیریت","Admin Dashboard")}</h1></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}
    {loading&&<div className="runtime-loading">{pick("در حال دریافت وضعیت زنده...","Loading live status...")}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("کل کاربران","Total users")} value={String(summary?.total_users??stats?.users??"—")} icon="♙"/>
      <Stat label={pick("اشتراک فعال","Active subscriptions")} value={String(subStats.total?subStats.active:stats?.active_subscriptions??"—")} icon="▱"/>
      <Stat label={pick("اشتراک آنلاین","Online subscriptions")} value={String(summary?.online_users??"—")} icon="◉"/>
      <Stat label={pick("فروش امروز","Sales today")} value={summary?money(summary.sales_today):"—"} icon="◫"/>
      <Stat label={pick("نود آنلاین","Online nodes")} value={summary?`${summary.online_nodes} / ${summary.total_nodes}`:stats?String(stats.online_nodes):"—"} icon="▦"/>
    </div>

    <div className="dash-grid admin-runtime-charts">
      <Card>
        <div className="card-head"><div><b>{pick("روند درآمد","Revenue trend")}</b><small>{pick("۳۰ روز گذشته · پرداخت‌های تأییدشده","Last 30 days · confirmed payments")}</small></div><Badge tone="violet">{pick("۳۰ روز","30 days")}</Badge></div>
        <div className="chart">
          <svg viewBox="0 0 600 200" preserveAspectRatio="none" aria-label={pick("نمودار درآمد ۳۰ روزه","30-day revenue chart")}>
            <defs><linearGradient id="runtimeRevenue" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#8b5cf6" stopOpacity=".38"/><stop offset="1" stopColor="#8b5cf6" stopOpacity="0"/></linearGradient></defs>
            <polygon points={chart.fill} fill="url(#runtimeRevenue)"/>
            <polyline points={chart.points} fill="none" stroke="#9b7cff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <div className="chart-labels"><span>{sales[0]?.date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"})}</span><span>{sales[14]?.date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"})}</span><span>{sales[29]?.date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"})}</span></div>
        </div>
        <div className="admin-sales-grid"><div><small>{pick("امروز","Today")}</small><b>{summary?money(summary.sales_today):"—"}</b></div><div><small>{pick("این هفته","This week")}</small><b>{summary?money(summary.sales_week):"—"}</b></div><div><small>{pick("این ماه","This month")}</small><b>{summary?money(summary.sales_month):"—"}</b></div></div>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("وضعیت اشتراک‌ها","Subscription status")}</b><small>{pick("بر اساس اشتراک‌های واقعی","Based on live subscriptions")}</small></div></div>
        <div className="donut" style={donutStyle}><div><b>{subStats.total.toLocaleString("fa-IR")}</b><small>{pick("کل اشتراک","Total")}</small></div></div>
        <div className="legend"><span><i className="c1"/>{pick(`فعال ${subStats.activePct}٪`,`Active ${subStats.activePct}%`)}</span><span><i className="c2"/>{pick(`منقضی ${subStats.expiredPct}٪`,`Expired ${subStats.expiredPct}%`)}</span><span><i style={{background:"#2dd4bf"}}/>{pick(`سایر ${subStats.otherPct}٪`,`Other ${subStats.otherPct}%`)}</span></div>
        <div className="online-summary"><span className="dot"/><b>{pick(`${summary?.online_users??0} اشتراک اکنون آنلاین است`,`${summary?.online_users??0} subscriptions are online now`)}</b><small>{pick("وضعیت زنده از Backend خوانده می‌شود","Live status is read from the backend")}</small></div>
      </Card>
    </div>

    <div className="triple admin-runtime-triple">
      <Card><div className="card-head"><b>{pick("نودها","Nodes")}</b><Link href="/admin/nodes">{pick("مشاهده همه","View all")}</Link></div>{nodes.slice(0,5).map(n=><div className="row" key={n.id}><span className={`status-dot ${String(n.status).toLowerCase()==="online"?"online":"offline"}`}/><div className="grow"><b>{n.name}</b><small dir="ltr">{n.public_ip||n.country_code||""}</small></div><Badge tone={String(n.status).toLowerCase()==="online"?"ok":"warn"}>{n.status||"—"}</Badge></div>)}{!nodes.length&&!loading&&<p className="muted">{pick("نودی دریافت نشد","No nodes returned")}</p>}</Card>
      <Card><div className="card-head"><b>{pick("تانل‌ها","Tunnels")}</b><Link href="/admin/tunnels">{pick("مدیریت","Manage")}</Link></div><div className="admin-tunnel-summary"><div><small>{pick("کل","Total")}</small><b>{tunnels.length}</b></div><div><small>{pick("آنلاین","Online")}</small><b>{onlineTunnels}</b></div></div>{tunnels.slice(0,4).map(t=><div className="row" key={t.id}><span className={`status-dot ${String(t.status).toLowerCase()==="online"?"online":"offline"}`}/><div className="grow"><b>#{t.id} · {t.transport||"Transport"}</b><small>{t.latency_ms==null?"—":`${t.latency_ms}ms`}</small></div><Badge tone={String(t.status).toLowerCase()==="online"?"ok":"warn"}>{t.status||"—"}</Badge></div>)}</Card>
      <Card><div className="card-head"><b>{pick("فعالیت اخیر","Recent activity")}</b><Link href="/admin/payments">{pick("همه","All")}</Link></div>{recentPayments.length?recentPayments.map((row,index)=><div className="activity" key={stringOf(row,"id")||index}><span>{index+1}</span><div><b>{paymentTitle(row,pick)}</b><small>{stringOf(row,"status","payment_status")||"—"}</small></div></div>):<p className="muted">{pick("پرداختی دریافت نشد","No payment activity")}</p>}</Card>
    </div>

    <Card className="admin-runtime-protocols-card"><div className="card-head"><div><b>{pick("پروتکل‌ها","Protocols")}</b><small>{pick("سلامت سرویس روی نودها","Service health across nodes")}</small></div></div><div className="admin-protocol-grid">{protocols.length?protocols.map(([key,p])=><div key={key}><span className={`status-dot ${p.online?"online":"offline"}`}/><b>{protocolLabel(key)}</b><small>{p.online_nodes} {pick("نود آنلاین","online nodes")}</small><Badge tone={p.online?"ok":"bad"}>{p.online?pick("آنلاین","Online"):pick("آفلاین","Offline")}</Badge></div>):<span className="muted">{pick("داده پروتکل دریافت نشد","No protocol data")}</span>}</div></Card>
  </div></Shell>;
}
