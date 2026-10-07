"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,AdminUser,RuntimeRow} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const id=(row:RuntimeRow)=>Number(row.id||0);
const n=(value:unknown)=>{const x=Number(value||0);return Number.isFinite(x)?x:0;};
const s=(value:unknown)=>String(value??"");
const arrayNumber=(value:unknown)=>Array.isArray(value)?value.map(Number).filter(Number.isFinite):[];
const arrayString=(value:unknown)=>Array.isArray(value)?value.map(String).filter(Boolean):[];
const durationDays=(row:RuntimeRow)=>{
  const start=row.starts_at?new Date(String(row.starts_at)):null;
  const end=row.expires_at?new Date(String(row.expires_at)):null;
  if(start&&end&&!Number.isNaN(start.getTime())&&!Number.isNaN(end.getTime()))return Math.max(1,Math.round((end.getTime()-start.getTime())/86400000));
  return 30;
};
const statusTone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const x=s(value).toLowerCase();
  return x==="active"?"ok":["expired","canceled"].includes(x)?"bad":"warn";
};

const protocolOptions=[
  ["cisco","Cisco / OpenConnect"],
  ["openvpn","OpenVPN"],
  ["wireguard","WireGuard"],
  ["l2tp","L2TP / IPsec"],
  ["v2ray","V2Ray / Xray"]
] as const;

export function SubscriptionToolsRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);
  const [plans,setPlans]=useState<RuntimeRow[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [selectedId,setSelectedId]=useState(0);
  const [planId,setPlanId]=useState(0);
  const [trafficGb,setTrafficGb]=useState(0);
  const [nodeIds,setNodeIds]=useState<number[]>([]);
  const [protocols,setProtocols]=useState<string[]>([]);
  const [manualTrafficGb,setManualTrafficGb]=useState(0);
  const [manualDurationDays,setManualDurationDays]=useState(30);
  const [detail,setDetail]=useState("");
  const [q,setQ]=useState("");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [subs,p,nodesResult,usersResult]=await Promise.all([adminApi.subscriptions(),adminApi.plans(),adminApi.nodes(),adminApi.users()]);
      setRows(subs);setPlans(p);setNodes(nodesResult);setUsers(usersResult);
      setSelectedId(current=>current&&subs.some(row=>id(row)===current)?current:(subs[0]?id(subs[0]):0));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const selected=useMemo(()=>rows.find(row=>id(row)===selectedId)||null,[rows,selectedId]);
  const userMap=useMemo(()=>new Map(users.map(user=>[user.id,user])),[users]);
  const planMap=useMemo(()=>new Map(plans.map(plan=>[Number(plan.id),plan])),[plans]);

  useEffect(()=>{
    if(!selected)return;
    const currentTraffic=Math.round((n(selected.traffic_limit_bytes)/GB)*100)/100;
    setPlanId(n(selected.plan_id));
    setTrafficGb(currentTraffic);
    setManualTrafficGb(currentTraffic);
    setManualDurationDays(durationDays(selected));
    setNodeIds(arrayNumber(selected.node_ids));
    setProtocols(arrayString(selected.protocols));
    setDetail("");
  },[selectedId,selected]);

  const filtered=useMemo(()=>{
    const query=q.trim().toLowerCase();
    if(!query)return rows;
    return rows.filter(row=>{
      const user=userMap.get(n(row.user_id));
      const plan=planMap.get(n(row.plan_id));
      return `${row.id??""} ${row.user_id??""} ${user?.full_name??""} ${user?.email??""} ${plan?.name??""} ${row.status??""}`.toLowerCase().includes(query);
    });
  },[rows,q,userMap,planMap]);

  const run=async(key:string,label:string,fn:()=>Promise<unknown>,reload=true)=>{
    if(busy||!selectedId)return;
    setBusy(key);setError("");setOk("");
    try{
      const result=await fn();
      setOk(label);
      if(key==="connection")setDetail(JSON.stringify(result,null,2));
      if(reload)await load();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const toggleNode=(nodeId:number,checked:boolean)=>setNodeIds(current=>checked?[...new Set([...current,nodeId])]:current.filter(x=>x!==nodeId));
  const toggleProtocol=(protocol:string,checked:boolean)=>setProtocols(current=>checked?[...new Set([...current,protocol])]:current.filter(x=>x!==protocol));

  const activeCount=rows.filter(row=>s(row.status).toLowerCase()==="active").length;
  const totalTraffic=rows.reduce((sum,row)=>sum+n(row.traffic_limit_bytes),0);

  return <Shell active="/admin/subscription-tools"><div className="page">
    <div className="page-head"><div><h1>{pick("ابزار پیشرفته اشتراک","Advanced Subscription Tools")}</h1><small>{pick("ویرایش پلن، حجم، نودها، پروتکل‌ها و محدودیت‌های دستی","Edit plan, traffic, nodes, protocols and manual limits")}</small></div><button className="ghost" disabled={loading||Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats"><Stat label={pick("کل اشتراک‌ها","Total subscriptions")} value={String(rows.length)} icon="▱"/><Stat label={pick("فعال","Active")} value={String(activeCount)} icon="✓"/><Stat label={pick("حجم تخصیص‌یافته","Allocated traffic")} value={`${(totalTraffic/GB).toLocaleString("fa-IR",{maximumFractionDigits:1})} GB`} icon="◉"/></div>

    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("انتخاب اشتراک","Select subscription")}</b><small>{pick("جستجو با نام، ایمیل، شناسه یا پلن","Search by name, email, ID or plan")}</small></div></div><label className="field"><span>{pick("جستجو","Search")}</span><input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("مثلاً ایمیل یا ID","Email or ID")}/></label><div className="subscription-tool-list">{filtered.slice(0,80).map(row=>{const rid=id(row),user=userMap.get(n(row.user_id)),plan=planMap.get(n(row.plan_id));return <button type="button" key={rid} className={`module-row ${rid===selectedId?"active":""}`} onClick={()=>setSelectedId(rid)}><div className="grow"><b>#{rid} · {user?.full_name||user?.email||`User #${row.user_id}`}</b><small>{String(plan?.name||`Plan #${row.plan_id}`)} · {row.expires_at?new Date(String(row.expires_at)).toLocaleDateString("fa-IR"):"—"}</small></div><Badge tone={statusTone(row.status)}>{s(row.status)||"—"}</Badge></button>})}{!filtered.length&&!loading&&<div className="runtime-empty">{pick("اشتراکی پیدا نشد.","No subscriptions found.")}</div>}</div></Card>

      <Card><div className="card-head"><div><b>{pick("اطلاعات فعلی","Current subscription")}</b><small>#{selectedId||"—"}</small></div>{selected&&<Badge tone={statusTone(selected.status)}>{s(selected.status)||"—"}</Badge>}</div>{selected?<div className="runtime-info-list"><div><span>{pick("کاربر","User")}</span><b>{userMap.get(n(selected.user_id))?.full_name||userMap.get(n(selected.user_id))?.email||`#${selected.user_id}`}</b></div><div><span>{pick("پلن","Plan")}</span><b>{String(planMap.get(n(selected.plan_id))?.name||`#${selected.plan_id}`)}</b></div><div><span>{pick("حجم فعلی","Current traffic")}</span><b>{(n(selected.traffic_limit_bytes)/GB).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB</b></div><div><span>{pick("مصرف","Used")}</span><b>{(n(selected.traffic_used_bytes)/GB).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB</b></div><div><span>{pick("شروع","Starts")}</span><b>{selected.starts_at?new Date(String(selected.starts_at)).toLocaleString("fa-IR"):"—"}</b></div><div><span>{pick("انقضا","Expires")}</span><b>{selected.expires_at?new Date(String(selected.expires_at)).toLocaleString("fa-IR"):"—"}</b></div></div>:<div className="runtime-empty">{pick("یک اشتراک انتخاب کنید.","Select a subscription.")}</div>}</Card>
    </div>

    {selected&&<>
      <Card className="runtime-editor"><div className="card-head"><div><b>{pick("Admin Edit","Admin Edit")}</b><small>{pick("ویرایش ساختاری اشتراک با API رسمی admin-edit","Structural edit using the official admin-edit API")}</small></div></div><div className="setting-grid"><label className="field"><span>{pick("پلن","Plan")}</span><select value={planId} onChange={e=>setPlanId(Number(e.target.value))}>{plans.map(plan=><option key={String(plan.id)} value={Number(plan.id)}>{String(plan.name||`#${plan.id}`)}</option>)}</select></label><label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={0} step="0.01" value={trafficGb} onChange={e=>setTrafficGb(Number(e.target.value))}/></label></div><div className="runtime-choice-section"><b>{pick("نودها","Nodes")}</b><div className="protocol-toggle-grid">{nodes.map(node=><label className="toggle module-toggle" key={node.id}><span>{node.name} · {node.node_type}</span><input type="checkbox" checked={nodeIds.includes(node.id)} onChange={e=>toggleNode(node.id,e.target.checked)}/><i/></label>)}</div></div><div className="runtime-choice-section"><b>{pick("پروتکل‌ها","Protocols")}</b><div className="protocol-toggle-grid">{protocolOptions.map(([key,label])=><label className="toggle module-toggle" key={key}><span>{label}</span><input type="checkbox" checked={protocols.includes(key)} onChange={e=>toggleProtocol(key,e.target.checked)}/><i/></label>)}</div></div><div className="action-row"><button className="primary" disabled={Boolean(busy)||!planId||protocols.length===0} onClick={()=>void run("edit",pick("اشتراک ویرایش شد","Subscription updated"),()=>adminApi.editSubscription(selectedId,{plan_id:planId,traffic_gb:trafficGb,node_ids:nodeIds,protocols}))}>{busy==="edit"?"…":pick("ذخیره Admin Edit","Save Admin Edit")}</button></div></Card>

      <Card className="runtime-editor"><div className="card-head"><div><b>{pick("Manual Limits","Manual Limits")}</b><small>{pick("مقدار نهایی حجم و مدت را مستقیماً تنظیم می‌کند؛ این بخش افزایش تجمعی نیست","Sets final traffic and duration directly; this is not additive extension")}</small></div></div><div className="setting-grid"><label className="field"><span>{pick("حجم نهایی GB","Final traffic GB")}</span><input type="number" min={0} step="0.01" value={manualTrafficGb} onChange={e=>setManualTrafficGb(Number(e.target.value))}/></label><label className="field"><span>{pick("مدت نهایی روز","Final duration days")}</span><input type="number" min={1} value={manualDurationDays} onChange={e=>setManualDurationDays(Number(e.target.value))}/></label></div><div className="action-row"><button className="primary" disabled={Boolean(busy)||manualDurationDays<1} onClick={()=>{if(window.confirm(pick("محدودیت‌های دستی جایگزین مقادیر فعلی شوند؟","Replace current limits with these manual values?")))void run("limits",pick("محدودیت‌های دستی اعمال شد","Manual limits applied"),()=>adminApi.setSubscriptionManualLimits(selectedId,{traffic_gb:manualTrafficGb,duration_days:manualDurationDays}));}}>{busy==="limits"?"…":pick("اعمال محدودیت دستی","Apply manual limits")}</button></div></Card>

      <Card><div className="card-head"><div><b>{pick("عملیات سرویس","Service actions")}</b><small>{pick("همان عملیات سالم Backend، بدون دستکاری دستی سرور","Existing backend operations without manual server changes")}</small></div></div><div className="action-grid"><button className="ghost" disabled={Boolean(busy)} onClick={()=>void run("toggle",s(selected.status).toLowerCase()==="active"?pick("اشتراک تعلیق شد","Subscription suspended"):pick("اشتراک فعال شد","Subscription activated"),()=>adminApi.setSubscriptionActive(selectedId,s(selected.status).toLowerCase()!=="active"))}>{s(selected.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button className="ghost" disabled={Boolean(busy)} onClick={()=>void run("provision",pick("Provision انجام شد","Provision completed"),()=>adminApi.provisionSubscription(selectedId))}>Provision</button><button className="ghost" disabled={Boolean(busy)} onClick={()=>void run("refresh-pass",pick("رمزها تازه شدند","Passwords refreshed"),()=>adminApi.refreshSubscriptionPasswords(selectedId))}>{pick("Refresh Passwords","Refresh Passwords")}</button><button className="ghost" disabled={Boolean(busy)} onClick={()=>void run("connection",pick("اطلاعات اتصال دریافت شد","Connection info loaded"),()=>adminApi.subscriptionConnectionInfo(selectedId),false)}>{pick("Connection Info","Connection Info")}</button></div></Card>
    </>}

    {detail&&<Card><div className="card-head"><b>{pick("اطلاعات اتصال","Connection Info")}</b><button className="mini-btn" onClick={()=>setDetail("")}>×</button></div><pre className="runtime-log" dir="ltr">{detail}</pre></Card>}
  </div></Shell>;
}
