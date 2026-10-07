"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,AdminStats,AdminTunnel,DashboardSummary} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} ${"تومان"}`;
const protocolLabel=(key:string)=>({cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray",xray:"V2Ray / Xray"} as Record<string,string>)[key.toLowerCase()]||key;

export function AdminDashboardRuntime(){
  const {pick}=useI18n();
  const [stats,setStats]=useState<AdminStats|null>(null);
  const [summary,setSummary]=useState<DashboardSummary|null>(null);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const result=await Promise.allSettled([adminApi.stats(),adminApi.dashboard(),adminApi.nodes(),adminApi.tunnels()]);
    if(result[0].status==="fulfilled")setStats(result[0].value);
    if(result[1].status==="fulfilled")setSummary(result[1].value);
    if(result[2].status==="fulfilled")setNodes(result[2].value);
    if(result[3].status==="fulfilled")setTunnels(result[3].value);
    const failed=result.find(x=>x.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };
  useEffect(()=>{void load();},[]);

  const protocols=useMemo(()=>Object.entries(summary?.protocols||{}),[summary]);
  const onlineTunnels=tunnels.filter(t=>String(t.status).toLowerCase()==="online").length;

  return <Shell active="/admin"><div className="page admin-dashboard-runtime">
    <div className="page-head"><div><h1>{pick("داشبورد مدیریت","Admin Dashboard")}</h1></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}
    {loading&&<div className="runtime-loading">{pick("در حال دریافت وضعیت زنده...","Loading live status...")}</div>}
    <div className="stats dashboard-stats">
      <Stat label={pick("کل کاربران","Total users")} value={String(summary?.total_users??stats?.users??"—")} icon="♙"/>
      <Stat label={pick("اشتراک فعال","Active subscriptions")} value={String(stats?.active_subscriptions??"—")} icon="▱"/>
      <Stat label={pick("کاربر آنلاین","Online users")} value={String(summary?.online_users??"—")} icon="◉"/>
      <Stat label={pick("فروش امروز","Sales today")} value={summary?money(summary.sales_today):"—"} icon="◫"/>
      <Stat label={pick("نود آنلاین","Online nodes")} value={summary?`${summary.online_nodes} / ${summary.total_nodes}`:stats?String(stats.online_nodes):"—"} icon="▦"/>
    </div>

    <div className="module-grid two admin-live-grid">
      <Card><div className="card-head"><div><b>{pick("فروش","Sales")}</b></div></div><div className="admin-sales-grid"><div><small>{pick("امروز","Today")}</small><b>{summary?money(summary.sales_today):"—"}</b></div><div><small>{pick("این هفته","This week")}</small><b>{summary?money(summary.sales_week):"—"}</b></div><div><small>{pick("این ماه","This month")}</small><b>{summary?money(summary.sales_month):"—"}</b></div></div></Card>
      <Card><div className="card-head"><div><b>{pick("پروتکل‌ها","Protocols")}</b></div></div><div className="admin-protocol-grid">{protocols.length?protocols.map(([key,p])=><div key={key}><span className={`status-dot ${p.online?"online":"offline"}`}/><b>{protocolLabel(key)}</b><small>{p.online_nodes} {pick("نود آنلاین","online nodes")}</small><Badge tone={p.online?"ok":"bad"}>{p.online?pick("آنلاین","Online"):pick("آفلاین","Offline")}</Badge></div>):<span className="muted">{pick("داده پروتکل دریافت نشد","No protocol data")}</span>}</div></Card>
    </div>

    <div className="module-grid two admin-live-grid">
      <Card><div className="card-head"><b>{pick("نودها","Nodes")}</b><Link href="/admin/nodes">{pick("همه","All")}</Link></div>{nodes.slice(0,6).map(n=><div className="row" key={n.id}><span className={`status-dot ${String(n.status).toLowerCase()==="online"?"online":"offline"}`}/><div className="grow"><b>{n.name}</b><small dir="ltr">{n.public_ip||n.country_code||""}</small></div><Badge tone={String(n.status).toLowerCase()==="online"?"ok":"warn"}>{n.status||"—"}</Badge></div>)}{!nodes.length&&!loading&&<p className="muted">{pick("نودی دریافت نشد","No nodes returned")}</p>}</Card>
      <Card><div className="card-head"><b>{pick("تانل‌ها","Tunnels")}</b><Link href="/admin/tunnels">{pick("مدیریت","Manage")}</Link></div><div className="admin-tunnel-summary"><div><small>{pick("کل","Total")}</small><b>{tunnels.length}</b></div><div><small>{pick("آنلاین","Online")}</small><b>{onlineTunnels}</b></div></div>{tunnels.slice(0,5).map(t=><div className="row" key={t.id}><span className={`status-dot ${String(t.status).toLowerCase()==="online"?"online":"offline"}`}/><div className="grow"><b>#{t.id} · {t.transport||"Transport"}</b><small>{t.latency_ms==null?"—":`${t.latency_ms}ms`}</small></div><Badge tone={String(t.status).toLowerCase()==="online"?"ok":"warn"}>{t.status||"—"}</Badge></div>)}</Card>
    </div>
  </div></Shell>;
}
