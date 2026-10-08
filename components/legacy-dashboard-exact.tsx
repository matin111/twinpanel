"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,AdminTunnel,RuntimeRow} from "../lib/admin-api";
import {legacyControlApi,SystemHealth} from "../lib/legacy-control-api";
import {useI18n} from "../lib/i18n";

const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const s=(value:unknown)=>String(value??"");
const money=(value:unknown)=>`${n(value).toLocaleString("fa-IR")} تومان`;
const bytes=(value:unknown)=>{const size=n(value);if(size<=0)return "0 B";const units=["B","KB","MB","GB","TB"];const i=Math.min(units.length-1,Math.floor(Math.log(size)/Math.log(1024)));return `${(size/1024**i).toLocaleString("fa-IR",{maximumFractionDigits:1})} ${units[i]}`;};
const percent=(value:unknown)=>`${n(value).toLocaleString("fa-IR",{maximumFractionDigits:1})}٪`;
const statusTone=(value:unknown):"ok"|"warn"|"bad"=>["healthy","active","online","ok"].includes(s(value).toLowerCase())?"ok":["critical","down","offline","failed"].includes(s(value).toLowerCase())?"bad":"warn";
const protocolName=(key:string)=>({cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray"} as Record<string,string>)[key]||key;

export function LegacyDashboardExactPage(){
  const {pick}=useI18n();
  const [summary,setSummary]=useState<RuntimeRow|null>(null);
  const [health,setHealth]=useState<SystemHealth|null>(null);
  const [protocols,setProtocols]=useState<Record<string,RuntimeRow>>({});
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [subscriptions,setSubscriptions]=useState<RuntimeRow[]>([]);
  const [payments,setPayments]=useState<RuntimeRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const result=await Promise.allSettled([
      legacyControlApi.dashboard(),legacyControlApi.systemHealth(),legacyControlApi.coreProtocols(),legacyControlApi.nodes(),legacyControlApi.tunnels(),adminApi.subscriptions(),adminApi.payments()
    ]);
    if(result[0].status==="fulfilled")setSummary(result[0].value);
    if(result[1].status==="fulfilled")setHealth(result[1].value);
    if(result[2].status==="fulfilled")setProtocols(result[2].value.protocols||{});
    if(result[3].status==="fulfilled")setNodes(result[3].value);
    if(result[4].status==="fulfilled")setTunnels(result[4].value);
    if(result[5].status==="fulfilled")setSubscriptions(result[5].value);
    if(result[6].status==="fulfilled")setPayments(result[6].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),30000);return()=>window.clearInterval(timer);},[]);

  const activeSubs=subscriptions.filter(item=>s(item.status).toLowerCase()==="active").length;
  const onlineTunnels=tunnels.filter(item=>s(item.status).toLowerCase()==="online").length;
  const pendingPayments=useMemo(()=>payments.filter(item=>["pending","submitted","waiting","review"].includes(s(item.status).toLowerCase())).slice(0,5),[payments]);
  const cpu=health?.cpu as RuntimeRow|undefined;
  const memory=health?.memory as RuntimeRow|undefined;
  const disk=health?.disk as RuntimeRow|undefined;
  const network=health?.network as RuntimeRow|undefined;
  const services=health?.services||{};

  const restartOne=async(key:string)=>{
    if(busy)return;
    if(!window.confirm(pick(`${protocolName(key)} ری‌استارت شود؟`,`Restart ${protocolName(key)}?`)))return;
    setBusy(`protocol-${key}`);setError("");setOk("");
    try{await legacyControlApi.restartCoreProtocol(key);setOk(pick(`${protocolName(key)} با موفقیت ری‌استارت شد.`,`${protocolName(key)} restarted successfully.`));const fresh=await legacyControlApi.coreProtocols();setProtocols(fresh.protocols||{});}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  const restartAll=async()=>{
    if(busy)return;
    if(!window.confirm(pick("همه پروتکل‌های Core ری‌استارت شوند؟","Restart all core protocols?")))return;
    setBusy("all-protocols");setError("");setOk("");
    try{await legacyControlApi.restartAllCoreProtocols();setOk(pick("عملیات ری‌استارت همه پروتکل‌ها انجام شد.","All core protocol restart operations finished."));const fresh=await legacyControlApi.coreProtocols();setProtocols(fresh.protocols||{});}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  return <Shell active="/admin"><div className="page legacy-control-page">
    <div className="page-head"><div><h1>{pick("داشبورد","Dashboard")}</h1><small>{pick("وضعیت واقعی کسب‌وکار، سیستم، پروتکل‌ها و شبکه","Live business, system, protocol and network status")}</small></div><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("کاربر آنلاین","Online users")} value={n(summary?.online_users).toLocaleString("fa-IR")}/>
      <Stat label={pick("کل کاربران","Total users")} value={n(summary?.total_users).toLocaleString("fa-IR")}/>
      <Stat label={pick("اکانت‌ها","Accounts")} value={n(summary?.total_accounts).toLocaleString("fa-IR")}/>
      <Stat label={pick("اشتراک فعال","Active subscriptions")} value={activeSubs.toLocaleString("fa-IR")}/>
      <Stat label={pick("نود آنلاین","Online nodes")} value={`${n(summary?.online_nodes).toLocaleString("fa-IR")} / ${n(summary?.total_nodes).toLocaleString("fa-IR")}`}/>
    </div>

    <div className="legacy-dashboard-grid">
      <Card>
        <div className="card-head"><div><b>{pick("فروش","Sales")}</b><small>{pick("مقادیر واقعی ثبت‌شده در Backend","Backend recorded totals")}</small></div><Link href="/admin/payments">{pick("پرداخت‌ها","Payments")}</Link></div>
        <div className="legacy-kpi-list"><div><small>{pick("امروز","Today")}</small><b>{money(summary?.sales_today)}</b></div><div><small>{pick("این هفته","This week")}</small><b>{money(summary?.sales_week)}</b></div><div><small>{pick("این ماه","This month")}</small><b>{money(summary?.sales_month)}</b></div><div><small>{pick("مصرف ماهانه","Monthly usage")}</small><b>{bytes(summary?.monthly_usage_bytes)}</b></div></div>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("سلامت سیستم","System health")}</b><small dir="ltr">{health?.hostname||"—"}</small></div><Badge tone={statusTone(health?.state)}>{s(health?.state)||pick("نامشخص","Unknown")}</Badge></div>
        <div className="legacy-kpi-list"><div><small>CPU</small><b>{percent(cpu?.percent)}</b></div><div><small>RAM</small><b>{percent(memory?.percent)}</b></div><div><small>{pick("دیسک","Disk")}</small><b>{percent(disk?.percent)}</b></div><div><small>{pick("اتصال فعال","Active connections")}</small><b>{n(health?.active_connections).toLocaleString("fa-IR")}</b></div><div><small>RX</small><b>{n(network?.rx_mbps).toLocaleString("fa-IR",{maximumFractionDigits:2})} Mbps</b></div><div><small>TX</small><b>{n(network?.tx_mbps).toLocaleString("fa-IR",{maximumFractionDigits:2})} Mbps</b></div></div>
        <div className="legacy-service-row">{Object.entries(services).map(([key,item])=><span key={key}><i className={`status-dot ${s(item.state)==="active"?"online":"offline"}`}/>{key}<Badge tone={statusTone(item.state)}>{s(item.state)||"—"}</Badge></span>)}</div>
      </Card>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("پروتکل‌های Core","Core protocols")}</b><small>{pick("وضعیت سرویس‌های اصلی روی کنترلر","Controller service status")}</small></div><button className="ghost" disabled={!!busy} onClick={()=>void restartAll()}>{busy==="all-protocols"?"…":pick("ری‌استارت همه","Restart all")}</button></div>
      <div className="legacy-protocol-cards">{Object.entries(protocols).map(([key,item])=><div className="setting-box" key={key}><div className="card-head"><div><b>{s(item.name)||protocolName(key)}</b><small dir="ltr">{s(item.port_text)||"—"} · {s(item.transport)||"—"}</small></div><Badge tone={Boolean(item.ok)?"ok":"bad"}>{Boolean(item.ok)?pick("آنلاین","Online"):pick("نیاز به بررسی","Needs attention")}</Badge></div><div className="row-actions"><button className="ghost" disabled={!!busy||item.installed===false} onClick={()=>void restartOne(key)}>{busy===`protocol-${key}`?"…":pick("ری‌استارت","Restart")}</button></div></div>)}</div>
    </Card>

    <div className="legacy-dashboard-grid three">
      <Card><div className="card-head"><b>{pick("نودها","Nodes")}</b><Link href="/admin/nodes">{pick("مدیریت","Manage")}</Link></div>{nodes.slice(0,6).map(item=><div className="row" key={item.id}><span className={`status-dot ${s(item.status)==="online"?"online":"offline"}`}/><div className="grow"><b>{item.name}</b><small dir="ltr">{item.public_ip||"—"}</small></div><Badge tone={s(item.status)==="online"?"ok":"warn"}>{s(item.status)||"—"}</Badge></div>)}</Card>
      <Card><div className="card-head"><b>{pick("تانل‌ها","Tunnels")}</b><Link href="/admin/tunnels">{pick("مدیریت","Manage")}</Link></div><div className="legacy-kpi-list"><div><small>{pick("کل","Total")}</small><b>{tunnels.length.toLocaleString("fa-IR")}</b></div><div><small>{pick("آنلاین","Online")}</small><b>{onlineTunnels.toLocaleString("fa-IR")}</b></div></div>{tunnels.slice(0,4).map(item=><div className="row" key={item.id}><span className={`status-dot ${s(item.status)==="online"?"online":"offline"}`}/><div className="grow"><b>#{item.id} · {item.transport||"—"}</b><small>{item.latency_ms==null?"—":`${item.latency_ms} ms`}</small></div></div>)}</Card>
      <Card><div className="card-head"><b>{pick("پرداخت‌های منتظر بررسی","Payments awaiting review")}</b><Link href="/admin/payments">{pick("مشاهده","View")}</Link></div>{pendingPayments.length?pendingPayments.map(item=><div className="row" key={s(item.id)}><div className="grow"><b>#{s(item.id)} · {money(item.amount_toman)}</b><small>{s(item.method||item.payment_method)||"—"}</small></div><Badge tone="warn">{s(item.status)||"—"}</Badge></div>):<div className="runtime-empty">{pick("پرداخت منتظر بررسی وجود ندارد","No payments awaiting review")}</div>}</Card>
    </div>
  </div></Shell>;
}
