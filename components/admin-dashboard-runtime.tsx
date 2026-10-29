"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {adminApi,AdminNode,AdminStats,AdminTunnel,DashboardSummary,RuntimeRow} from "../lib/admin-api";
import {dashboardPaymentAmount,revenueSeries} from "../lib/admin-dashboard-revenue";
import {useI18n} from "../lib/i18n";

const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const PROTOCOLS=[
  ["cisco","Cisco / OpenConnect"],["openvpn","OpenVPN"],["wireguard","WireGuard"],["l2tp","L2TP / IPsec"],["v2ray","V2Ray / Xray"],
  ["hysteria2","Hysteria2"],["tuic","TUIC v5"],["anytls","AnyTLS"],["naive","NaiveProxy"],["shadowtls","ShadowTLS v3"],
  ["snell","Snell"],["mieru","Mieru"],["trusttunnel","TrustTunnel"],["amneziawg","AmneziaWG"],["sudoku","Sudoku"]
] as const;
const valueOf=(row:RuntimeRow,...keys:string[])=>{for(const key of keys){const value=row[key];if(value!==undefined&&value!==null)return value;}return undefined;};
const stringOf=(row:RuntimeRow,...keys:string[])=>String(valueOf(row,...keys)??"");
const numOf=(value:unknown)=>{const n=Number(value);return Number.isFinite(n)?n:null;};

function chartGeometry(series:ReturnType<typeof revenueSeries>){
  const max=Math.max(1,...series.map(item=>item.value));
  const points=series.map((item,index)=>{
    const x=(index/Math.max(1,series.length-1))*600;
    const y=180-(item.value/max)*145;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return {points,fill:`0,200 ${points} 600,200`};
}

function paymentTitle(row:RuntimeRow,pick:(fa:string,en:string)=>string){
  const id=stringOf(row,"id")||"—";
  const amount=dashboardPaymentAmount(row);
  return `${pick("پرداخت","Payment")} #${id}${amount?` · ${money(amount)}`:""}`;
}

function MetricBar({label,value}:{label:string;value:number|null}){
  const safe=value==null?0:Math.max(0,Math.min(100,value));
  const tone=value==null?"unknown":safe>=90?"danger":safe>=75?"warning":"healthy";
  return <div className={`dash-resource ${tone}`}>
    <div><span>{label}</span><b>{value==null?"—":`${Math.round(value)}%`}</b></div>
    <i><em style={{width:`${safe}%`}}/></i>
  </div>;
}

function KpiCard({label,value,meta,icon,tone="violet"}:{label:string;value:string;meta:string;icon:string;tone?:string}){
  return <div className={`dash-kpi dash-kpi-${tone}`}>
    <div className="dash-kpi-icon">{icon}</div>
    <div className="dash-kpi-copy"><span>{label}</span><strong>{value}</strong><small>{meta}</small></div>
  </div>;
}

export function AdminDashboardRuntime(){
  const {pick}=useI18n();
  const [stats,setStats]=useState<AdminStats|null>(null);
  const [summary,setSummary]=useState<DashboardSummary|null>(null);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [nodeHealth,setNodeHealth]=useState<Record<number,RuntimeRow>>({});
  const [modernProtocols,setModernProtocols]=useState<Record<string,{online:boolean;online_nodes:number;reported:boolean}>>({});
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [subscriptions,setSubscriptions]=useState<RuntimeRow[]>([]);
  const [payments,setPayments]=useState<RuntimeRow[]>([]);
  const [loading,setLoading]=useState(true);
  const [refreshing,setRefreshing]=useState(false);
  const [error,setError]=useState("");

  const load=async(silent=false)=>{
    if(silent)setRefreshing(true);else setLoading(true);
    setError("");
    const result=await Promise.allSettled([
      adminApi.stats(),adminApi.dashboard(),adminApi.nodes(),adminApi.tunnels(),adminApi.subscriptions(),adminApi.payments()
    ]);
    if(result[0].status==="fulfilled")setStats(result[0].value);
    if(result[1].status==="fulfilled")setSummary(result[1].value);
    const loadedNodes=result[2].status==="fulfilled"?result[2].value:[];
    if(result[2].status==="fulfilled")setNodes(loadedNodes);
    if(result[3].status==="fulfilled")setTunnels(result[3].value);
    if(result[4].status==="fulfilled")setSubscriptions(result[4].value);
    if(result[5].status==="fulfilled")setPayments(result[5].value);
    const failed=result.find(x=>x.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));

    if(loadedNodes.length){
      const healthResults=await Promise.allSettled(loadedNodes.map(node=>adminApi.nodeHealth(node.id)));
      const healthMap:Record<number,RuntimeRow>={};
      healthResults.forEach((item,index)=>{if(item.status==="fulfilled")healthMap[loadedNodes[index].id]=item.value;});
      setNodeHealth(healthMap);

      const protocolResults=await Promise.allSettled(loadedNodes.map(node=>adminApi.nodeProtocols(node.id)));
      const aggregate:Record<string,{online:boolean;online_nodes:number;reported:boolean}>={};
      protocolResults.forEach((item,index)=>{
        if(item.status!=="fulfilled"||!Array.isArray(item.value))return;
        const nodeOnline=String(loadedNodes[index].status||"").toLowerCase()==="online";
        for(const raw of item.value as RuntimeRow[]){
          const key=stringOf(raw,"protocol").toLowerCase();
          if(!key)continue;
          const status=stringOf(raw,"status").toLowerCase();
          const healthy=nodeOnline&&["online","active","ready","healthy","running"].includes(status);
          const current=aggregate[key]||{online:false,online_nodes:0,reported:false};
          current.reported=true;
          if(healthy){current.online=true;current.online_nodes+=1;}
          aggregate[key]=current;
        }
      });
      setModernProtocols(aggregate);
    }
    setLoading(false);setRefreshing(false);
  };
  useEffect(()=>{void load();},[]);

  const protocols=useMemo(()=>PROTOCOLS.map(([key,label])=>{
    const classic=summary?.protocols?.[key];
    const modern=modernProtocols[key];
    return {key,label,online:classic?.online??modern?.online??false,onlineNodes:classic?.online_nodes??modern?.online_nodes??0,reported:Boolean(classic||modern?.reported)};
  }),[summary,modernProtocols]);
  const onlineTunnels=tunnels.filter(t=>String(t.status).toLowerCase()==="online").length;
  const onlineNodes=nodes.filter(n=>String(n.status).toLowerCase()==="online").length;
  const nodeHealthPct=nodes.length?Math.round((onlineNodes/nodes.length)*100):0;
  const tunnelHealthPct=tunnels.length?Math.round((onlineTunnels/tunnels.length)*100):0;
  const protocolOnline=protocols.filter(p=>p.online).length;
  const protocolReported=protocols.filter(p=>p.reported).length;

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
    const suspendedPct=total?Math.round((counts.suspended/total)*100):0;
    const otherPct=Math.max(0,100-activePct-expiredPct-suspendedPct);
    return {...counts,total,activePct,expiredPct,suspendedPct,otherPct};
  },[subscriptions]);
  const sales=useMemo(()=>revenueSeries(payments),[payments]);
  const chart=useMemo(()=>chartGeometry(sales),[sales]);
  const recentPayments=useMemo(()=>[...payments].sort((a,b)=>{
    const ad=Date.parse(stringOf(a,"verified_at","paid_at","submitted_at","created_at"))||0;
    const bd=Date.parse(stringOf(b,"verified_at","paid_at","submitted_at","created_at"))||0;
    return bd-ad;
  }).slice(0,5),[payments]);
  const donutStyle={background:`conic-gradient(#7c5cff 0 ${subStats.activePct}%,#f59e0b ${subStats.activePct}% ${subStats.activePct+subStats.expiredPct}%,#f06a78 ${subStats.activePct+subStats.expiredPct}% ${subStats.activePct+subStats.expiredPct+subStats.suspendedPct}%,#20c997 ${subStats.activePct+subStats.expiredPct+subStats.suspendedPct}% 100%)`};
  const generatedAt=summary?.generated_at?new Date(summary.generated_at):null;

  return <Shell active="/admin"><div className="page dash27">
    <section className="dash27-hero">
      <div className="dash27-title">
        <span className="dash27-eyebrow"><i/>{pick("مرکز فرمان زنده","LIVE COMMAND CENTER")}</span>
        <h1>{pick("داشبورد مدیریت","Admin Dashboard")}</h1>
        <p>{pick("نمای یکپارچه فروش، کاربران، نودها، تانل‌ها و سلامت پروتکل‌های TwinPanel","Unified view of sales, users, nodes, tunnels and TwinPanel protocol health")}</p>
      </div>
      <div className="dash27-actions">
        <div className="dash27-live"><span/><div><b>{pick("سیستم آنلاین","System online")}</b><small>{generatedAt?generatedAt.toLocaleTimeString("fa-IR",{hour:"2-digit",minute:"2-digit"}):pick("در انتظار داده","Waiting for data")}</small></div></div>
        <button className="dash27-refresh" disabled={refreshing} onClick={()=>void load(true)}><span className={refreshing?"spin":""}>↻</span>{refreshing?pick("در حال بروزرسانی","Refreshing"):pick("بروزرسانی زنده","Live refresh")}</button>
      </div>
    </section>

    {error&&<div className="runtime-error dash27-error">{error}</div>}
    {loading&&<div className="dash27-loading"><span className="spinner"/>{pick("در حال ساخت نمای زنده داشبورد...","Building live dashboard view...")}</div>}

    <section className="dash27-kpis">
      <KpiCard label={pick("کل کاربران","Total users")} value={String(summary?.total_users??stats?.users??"—")} meta={pick("کاربران ثبت‌شده","Registered customers")} icon="◌" tone="violet"/>
      <KpiCard label={pick("اشتراک فعال","Active subscriptions")} value={String(subStats.total?subStats.active:stats?.active_subscriptions??"—")} meta={subStats.total?`${subStats.activePct}% ${pick("از کل اشتراک‌ها","of subscriptions")}`:pick("وضعیت حساب‌ها","Account status")} icon="◇" tone="blue"/>
      <KpiCard label={pick("آنلاین اکنون","Online now")} value={String(summary?.online_users??"—")} meta={pick("اتصال زنده کاربران","Live user sessions")} icon="◎" tone="green"/>
      <KpiCard label={pick("فروش امروز","Sales today")} value={summary?money(summary.sales_today):"—"} meta={summary?`${pick("این ماه","Month")}: ${money(summary.sales_month)}`:pick("درآمد تأییدشده","Confirmed revenue")} icon="↗" tone="amber"/>
      <KpiCard label={pick("سلامت نودها","Node health")} value={summary?`${summary.online_nodes} / ${summary.total_nodes}`:stats?String(stats.online_nodes):"—"} meta={`${nodeHealthPct}% ${pick("در دسترس","available")}`} icon="▦" tone="cyan"/>
    </section>

    <section className="dash27-main-grid">
      <Card className="dash27-revenue-card">
        <div className="dash27-card-head"><div><span>{pick("فروش و درآمد","SALES & REVENUE")}</span><h2>{pick("روند درآمد ۳۰ روز گذشته","Revenue trend · last 30 days")}</h2></div><Badge tone="violet">{pick("زنده","Live")}</Badge></div>
        <div className="dash27-chart">
          <svg viewBox="0 0 600 200" preserveAspectRatio="none" aria-label={pick("نمودار درآمد ۳۰ روزه","30-day revenue chart")}>
            <defs><linearGradient id="runtimeRevenue27" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#7c5cff" stopOpacity=".32"/><stop offset="1" stopColor="#7c5cff" stopOpacity="0"/></linearGradient></defs>
            <line x1="0" y1="50" x2="600" y2="50" className="dash27-gridline"/><line x1="0" y1="100" x2="600" y2="100" className="dash27-gridline"/><line x1="0" y1="150" x2="600" y2="150" className="dash27-gridline"/>
            <polygon points={chart.fill} fill="url(#runtimeRevenue27)"/>
            <polyline points={chart.points} fill="none" stroke="#8063ff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <div className="chart-labels"><span>{sales[0]?.date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"})}</span><span>{sales[14]?.date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"})}</span><span>{sales[29]?.date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"})}</span></div>
        </div>
        <div className="dash27-sales-strip"><div><span>{pick("امروز","Today")}</span><b>{summary?money(summary.sales_today):"—"}</b></div><div><span>{pick("این هفته","This week")}</span><b>{summary?money(summary.sales_week):"—"}</b></div><div><span>{pick("این ماه","This month")}</span><b>{summary?money(summary.sales_month):"—"}</b></div></div>
      </Card>

      <Card className="dash27-health-card">
        <div className="dash27-card-head"><div><span>{pick("وضعیت سرویس","SERVICE HEALTH")}</span><h2>{pick("سلامت عملیاتی","Operational health")}</h2></div></div>
        <div className="dash27-health-score"><div className="dash27-ring" style={{"--score":`${nodeHealthPct}%`} as React.CSSProperties}><strong>{nodeHealthPct}%</strong><small>{pick("نودها","Nodes")}</small></div><div className="dash27-health-copy"><b>{nodeHealthPct>=90?pick("وضعیت عالی","Excellent"):nodeHealthPct>=70?pick("وضعیت پایدار","Stable"):pick("نیاز به بررسی","Needs attention")}</b><p>{pick("خلاصه وضعیت زیرساخت در لحظه","Real-time infrastructure overview")}</p></div></div>
        <div className="dash27-health-lines">
          <div><span><i className="green"/>{pick("نودهای آنلاین","Online nodes")}</span><b>{onlineNodes}/{nodes.length}</b></div>
          <div><span><i className="violet"/>{pick("تانل‌های آنلاین","Online tunnels")}</span><b>{onlineTunnels}/{tunnels.length} · {tunnelHealthPct}%</b></div>
          <div><span><i className="cyan"/>{pick("پروتکل‌های سالم","Healthy protocols")}</span><b>{protocolOnline}/{protocolReported||15}</b></div>
        </div>
      </Card>
    </section>

    <section className="dash27-mid-grid">
      <Card className="dash27-sub-card">
        <div className="dash27-card-head"><div><span>{pick("اشتراک‌ها","SUBSCRIPTIONS")}</span><h2>{pick("وضعیت اشتراک‌ها","Subscription status")}</h2></div><Link href="/admin/subscriptions">{pick("مشاهده همه","View all")} ←</Link></div>
        <div className="dash27-sub-body"><div className="donut dash27-donut" style={donutStyle}><div><b>{subStats.total.toLocaleString("fa-IR")}</b><small>{pick("کل اشتراک","Total")}</small></div></div><div className="dash27-legend"><div><i style={{background:"#7c5cff"}}/><span>{pick("فعال","Active")}</span><b>{subStats.activePct}%</b></div><div><i style={{background:"#f59e0b"}}/><span>{pick("منقضی","Expired")}</span><b>{subStats.expiredPct}%</b></div><div><i style={{background:"#f06a78"}}/><span>{pick("تعلیق","Suspended")}</span><b>{subStats.suspendedPct}%</b></div><div><i style={{background:"#20c997"}}/><span>{pick("سایر","Other")}</span><b>{subStats.otherPct}%</b></div></div></div>
      </Card>

      <Card className="dash27-activity-card">
        <div className="dash27-card-head"><div><span>{pick("جریان زنده","ACTIVITY STREAM")}</span><h2>{pick("فعالیت اخیر","Recent activity")}</h2></div><Link href="/admin/payments">{pick("همه تراکنش‌ها","All payments")} ←</Link></div>
        <div className="dash27-activity-list">{recentPayments.length?recentPayments.map((row,index)=><div className="dash27-activity" key={stringOf(row,"id")||index}><span className="dash27-activity-icon">↗</span><div><b>{paymentTitle(row,pick)}</b><small>{stringOf(row,"status","payment_status")||"—"}</small></div><i/></div>):<p className="muted">{pick("فعالیتی دریافت نشد","No activity returned")}</p>}</div>
      </Card>
    </section>

    <section className="dash27-nodes-section">
      <div className="dash27-section-title"><div><span>{pick("زیرساخت","INFRASTRUCTURE")}</span><h2>{pick("وضعیت سرورها","Server fleet")}</h2><p>{pick("وضعیت، کاربران و متریک‌های منابع هر نود","Status, users and resource telemetry for each node")}</p></div><Link href="/admin/nodes">{pick("مدیریت سرورها","Manage servers")} ←</Link></div>
      <div className="dash27-node-grid">{nodes.slice(0,6).map(n=>{
        const health=nodeHealth[n.id]||{};
        const row=n as unknown as RuntimeRow;
        const cpu=numOf(valueOf(health,"cpu_percent","cpu")??valueOf(row,"cpu_percent"));
        const ram=numOf(valueOf(health,"memory_percent","ram_percent","memory")??valueOf(row,"memory_percent"));
        const disk=numOf(valueOf(health,"disk_percent","disk")??valueOf(row,"disk_percent"));
        const isOnline=String(n.status).toLowerCase()==="online";
        const usage=n.capacity_users?Math.round(((n.current_users||0)/n.capacity_users)*100):0;
        return <div className="dash27-node" key={n.id}>
          <div className="dash27-node-head"><div className={`dash27-server-icon ${isOnline?"online":"offline"}`}>▣</div><div className="grow"><b>{n.name}</b><small dir="ltr">{n.public_ip||n.country_code||""}</small></div><span className={`dash27-state ${isOnline?"online":"offline"}`}><i/>{isOnline?pick("آنلاین","Online"):pick("آفلاین","Offline")}</span></div>
          <div className="dash27-node-users"><span>{pick("کاربران","Users")}</span><b>{n.current_users||0} / {n.capacity_users||0}</b><em>{usage}%</em></div>
          <div className="dash27-resources"><MetricBar label="CPU" value={cpu}/><MetricBar label="RAM" value={ram}/><MetricBar label="Disk" value={disk}/></div>
          {(cpu==null&&ram==null&&disk==null)&&<small className="dash27-telemetry-note">{pick("متریک منابع هنوز در پاسخ Health این نود گزارش نشده است","Resource telemetry is not yet exposed by this node health response")}</small>}
        </div>;
      })}{!nodes.length&&!loading&&<div className="dash27-empty">{pick("نودی دریافت نشد","No nodes returned")}</div>}</div>
    </section>

    <section className="dash27-bottom-grid">
      <Card className="dash27-tunnels-card"><div className="dash27-card-head"><div><span>{pick("مسیرهای شبکه","NETWORK PATHS")}</span><h2>{pick("تانل‌ها","Tunnels")}</h2></div><Link href="/admin/tunnels">{pick("مدیریت","Manage")} ←</Link></div><div className="dash27-tunnel-list">{tunnels.slice(0,6).map(t=>{const on=String(t.status).toLowerCase()==="online";return <div className="dash27-tunnel" key={t.id}><span className={`status-dot ${on?"online":"offline"}`}/><div><b>#{t.id} · {t.active_transport||t.transport||"Transport"}</b><small>{t.mode||pick("مسیر تونل","Tunnel path")}</small></div><strong>{t.latency_ms==null?"—":`${t.latency_ms} ms`}</strong><Badge tone={on?"ok":"warn"}>{t.status||"—"}</Badge></div>})}</div></Card>

      <Card className="dash27-protocol-card"><div className="dash27-card-head"><div><span>{pick("ماتریس سلامت","HEALTH MATRIX")}</span><h2>{pick("۱۵ پروتکل سرویس","15 service protocols")}</h2><small>{pick("۵ Classic + ۱۰ Modern","5 Classic + 10 Modern")}</small></div><Link href="/admin/protocols">{pick("مدیریت پروتکل‌ها","Manage protocols")} ←</Link></div><div className="dash27-protocol-grid">{protocols.map(p=><div className={`dash27-protocol ${p.reported?(p.online?"online":"offline"):"unknown"}`} key={p.key}><span className="dash27-protocol-icon">{p.online?"✓":p.reported?"!":"·"}</span><div><b>{p.label}</b><small>{p.reported?`${p.onlineNodes} ${pick("نود آنلاین","online nodes")}`:pick("بدون گزارش سلامت","No health report")}</small></div><span className="dash27-protocol-state">{p.reported?(p.online?pick("سالم","Healthy"):pick("آفلاین","Offline")):pick("نامشخص","Unknown")}</span></div>)}</div></Card>
    </section>

    <style jsx global>{`
      .dash27{--d-accent:#7c5cff;--d-accent2:#9b84ff;--d-green:#20c997;--d-cyan:#22b8cf;--d-amber:#f59e0b;--d-red:#f06a78;display:grid;gap:18px;padding-bottom:34px}.dash27 .card{border-color:color-mix(in srgb,var(--line) 75%,transparent);box-shadow:0 16px 50px rgba(36,25,70,.055)}
      .dash27-hero{position:relative;overflow:hidden;display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding:24px 26px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--surface) 94%,#7c5cff 6%),var(--surface));box-shadow:0 18px 55px rgba(67,45,122,.06)}.dash27-hero:after{content:"";position:absolute;inset:auto -70px -110px auto;width:300px;height:300px;border-radius:50%;background:radial-gradient(circle,rgba(124,92,255,.14),transparent 67%);pointer-events:none}.dash27-title{position:relative;z-index:1}.dash27-eyebrow{display:inline-flex;align-items:center;gap:7px;margin-bottom:7px;color:var(--d-accent);font-size:10px;font-weight:800;letter-spacing:.08em}.dash27-eyebrow i{width:7px;height:7px;border-radius:50%;background:var(--d-green);box-shadow:0 0 0 5px rgba(32,201,151,.1)}.dash27-title h1{margin:0;font-size:31px;letter-spacing:-.035em}.dash27-title p{margin:7px 0 0;color:var(--muted);font-size:12px}.dash27-actions{position:relative;z-index:1;display:flex;align-items:center;gap:10px}.dash27-live{display:flex;align-items:center;gap:9px;padding:9px 12px;border:1px solid var(--line);border-radius:13px;background:color-mix(in srgb,var(--surface2) 82%,transparent)}.dash27-live>span{width:9px;height:9px;border-radius:50%;background:var(--d-green);box-shadow:0 0 0 5px rgba(32,201,151,.12)}.dash27-live div{display:grid}.dash27-live b{font-size:10px}.dash27-live small{font-size:9px;color:var(--muted)}.dash27-refresh{display:inline-flex;align-items:center;gap:8px;min-height:42px;padding:0 15px;border:0;border-radius:13px;background:linear-gradient(135deg,#7657f6,#936fff);color:#fff;font:inherit;font-size:11px;font-weight:800;cursor:pointer;box-shadow:0 10px 24px rgba(124,92,255,.24)}.dash27-refresh:disabled{opacity:.65}.dash27-refresh span{font-size:18px}.dash27-refresh .spin{animation:spin .8s linear infinite}.dash27-loading{display:flex;align-items:center;justify-content:center;gap:9px;padding:12px;color:var(--muted);font-size:11px}.dash27-error{margin:0}
      .dash27-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.dash-kpi{position:relative;overflow:hidden;display:grid;grid-template-columns:44px 1fr;gap:11px;align-items:center;min-height:112px;padding:16px;border:1px solid var(--line);border-radius:18px;background:var(--surface);box-shadow:0 12px 35px rgba(26,19,54,.045)}.dash-kpi:after{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--kpi,#7c5cff)}.dash-kpi-violet{--kpi:#7c5cff}.dash-kpi-blue{--kpi:#4c7dff}.dash-kpi-green{--kpi:#20c997}.dash-kpi-amber{--kpi:#f59e0b}.dash-kpi-cyan{--kpi:#22b8cf}.dash-kpi-icon{display:grid;place-items:center;width:44px;height:44px;border-radius:14px;background:color-mix(in srgb,var(--kpi) 10%,var(--surface2));color:var(--kpi);font-size:22px}.dash-kpi-copy{display:grid;gap:2px;min-width:0}.dash-kpi-copy span{color:var(--muted);font-size:10px}.dash-kpi-copy strong{font-size:23px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dash-kpi-copy small{color:var(--muted);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .dash27-main-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(290px,.75fr);gap:14px}.dash27-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}.dash27-card-head>div{display:grid;gap:2px}.dash27-card-head span{color:var(--d-accent);font-size:9px;font-weight:800;letter-spacing:.09em}.dash27-card-head h2{margin:0;font-size:15px}.dash27-card-head small{color:var(--muted);font-size:9px}.dash27-card-head>a{color:var(--d-accent);font-size:10px;font-weight:700;text-decoration:none}.dash27-chart{height:220px;padding-top:4px}.dash27-chart svg{width:100%;height:190px;overflow:visible}.dash27-gridline{stroke:color-mix(in srgb,var(--line) 78%,transparent);stroke-width:1;stroke-dasharray:4 7}.dash27-sales-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.dash27-sales-strip>div{display:grid;gap:3px;padding:12px 14px;border:1px solid var(--line);border-radius:13px;background:var(--surface2)}.dash27-sales-strip span{color:var(--muted);font-size:9px}.dash27-sales-strip b{font-size:13px}.dash27-health-score{display:flex;align-items:center;gap:18px;padding:10px 0 18px}.dash27-ring{--score:0%;display:grid;place-items:center;align-content:center;width:112px;height:112px;flex:0 0 auto;border-radius:50%;background:radial-gradient(circle at center,var(--surface) 57%,transparent 59%),conic-gradient(var(--d-green) var(--score),color-mix(in srgb,var(--line) 65%,transparent) 0)}.dash27-ring strong{font-size:24px}.dash27-ring small{color:var(--muted);font-size:9px}.dash27-health-copy b{font-size:15px}.dash27-health-copy p{margin:5px 0 0;color:var(--muted);font-size:10px}.dash27-health-lines{display:grid;gap:8px}.dash27-health-lines>div{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border-radius:11px;background:var(--surface2)}.dash27-health-lines span{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:10px}.dash27-health-lines i{width:7px;height:7px;border-radius:50%}.dash27-health-lines i.green{background:var(--d-green)}.dash27-health-lines i.violet{background:var(--d-accent)}.dash27-health-lines i.cyan{background:var(--d-cyan)}.dash27-health-lines b{font-size:10px}
      .dash27-mid-grid{display:grid;grid-template-columns:.85fr 1.15fr;gap:14px}.dash27-sub-body{display:flex;align-items:center;justify-content:center;gap:25px;min-height:180px}.dash27-donut{width:132px;height:132px}.dash27-legend{display:grid;gap:9px;min-width:150px}.dash27-legend>div{display:grid;grid-template-columns:8px 1fr auto;align-items:center;gap:8px;padding-bottom:7px;border-bottom:1px solid color-mix(in srgb,var(--line) 75%,transparent)}.dash27-legend i{width:8px;height:8px;border-radius:50%}.dash27-legend span{font-size:10px;color:var(--muted)}.dash27-legend b{font-size:10px}.dash27-activity-list{display:grid}.dash27-activity{display:grid;grid-template-columns:32px 1fr 7px;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid color-mix(in srgb,var(--line) 75%,transparent)}.dash27-activity:last-child{border-bottom:0}.dash27-activity-icon{display:grid;place-items:center;width:32px;height:32px;border-radius:10px;background:rgba(32,201,151,.09);color:var(--d-green);font-weight:800}.dash27-activity>div{display:grid;gap:2px}.dash27-activity b{font-size:10px}.dash27-activity small{color:var(--muted);font-size:9px}.dash27-activity>i{width:7px;height:7px;border-radius:50%;background:var(--d-green)}
      .dash27-nodes-section{display:grid;gap:12px}.dash27-section-title{display:flex;align-items:end;justify-content:space-between;gap:15px;padding:0 4px}.dash27-section-title>div{display:grid;gap:2px}.dash27-section-title span{font-size:9px;font-weight:800;color:var(--d-accent);letter-spacing:.08em}.dash27-section-title h2{margin:0;font-size:17px}.dash27-section-title p{margin:2px 0 0;color:var(--muted);font-size:10px}.dash27-section-title>a{font-size:10px;color:var(--d-accent);text-decoration:none;font-weight:700}.dash27-node-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.dash27-node{display:grid;gap:13px;padding:15px;border:1px solid var(--line);border-radius:17px;background:var(--surface);box-shadow:0 12px 34px rgba(30,24,55,.045)}.dash27-node-head{display:flex;align-items:center;gap:10px}.dash27-server-icon{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:var(--surface2);color:var(--muted)}.dash27-server-icon.online{background:rgba(32,201,151,.09);color:var(--d-green)}.dash27-node-head .grow{display:grid;gap:1px;min-width:0}.dash27-node-head b{font-size:11px}.dash27-node-head small{color:var(--muted);font-size:9px}.dash27-state{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border-radius:999px;font-size:8px;font-weight:800}.dash27-state i{width:6px;height:6px;border-radius:50%;background:currentColor}.dash27-state.online{color:#159b70;background:rgba(32,201,151,.1)}.dash27-state.offline{color:#d95768;background:rgba(240,106,120,.1)}.dash27-node-users{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:8px;padding:9px 10px;border-radius:10px;background:var(--surface2);font-size:9px}.dash27-node-users span{color:var(--muted)}.dash27-node-users b{font-size:10px}.dash27-node-users em{font-style:normal;color:var(--d-accent);font-weight:800}.dash27-resources{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.dash-resource{display:grid;gap:6px}.dash-resource>div{display:flex;justify-content:space-between;gap:4px;font-size:8px}.dash-resource span{color:var(--muted)}.dash-resource b{font-size:8px}.dash-resource>i{display:block;height:5px;border-radius:999px;background:var(--surface2);overflow:hidden}.dash-resource>i em{display:block;height:100%;border-radius:inherit;background:var(--d-green)}.dash-resource.warning>i em{background:var(--d-amber)}.dash-resource.danger>i em{background:var(--d-red)}.dash-resource.unknown>i em{background:var(--line)}.dash27-telemetry-note{padding-top:1px;color:var(--muted);font-size:8px}.dash27-empty{grid-column:1/-1;padding:25px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:16px}
      .dash27-bottom-grid{display:grid;grid-template-columns:.7fr 1.3fr;gap:14px}.dash27-tunnel-list{display:grid}.dash27-tunnel{display:grid;grid-template-columns:8px 1fr auto auto;align-items:center;gap:9px;padding:10px 0;border-bottom:1px solid color-mix(in srgb,var(--line) 75%,transparent)}.dash27-tunnel:last-child{border-bottom:0}.dash27-tunnel>div{display:grid;gap:1px}.dash27-tunnel b{font-size:10px}.dash27-tunnel small{font-size:8px;color:var(--muted)}.dash27-tunnel strong{font-size:9px}.dash27-protocol-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.dash27-protocol{display:grid;grid-template-columns:30px 1fr auto;align-items:center;gap:8px;padding:9px 10px;border:1px solid var(--line);border-radius:12px;background:var(--surface2);transition:.18s ease}.dash27-protocol:hover{transform:translateY(-1px);border-color:color-mix(in srgb,var(--d-accent) 35%,var(--line))}.dash27-protocol-icon{display:grid;place-items:center;width:30px;height:30px;border-radius:9px;background:rgba(111,120,144,.09);color:var(--muted);font-size:11px;font-weight:900}.dash27-protocol.online .dash27-protocol-icon{background:rgba(32,201,151,.1);color:var(--d-green)}.dash27-protocol.offline .dash27-protocol-icon{background:rgba(240,106,120,.1);color:var(--d-red)}.dash27-protocol>div{display:grid;gap:1px;min-width:0}.dash27-protocol b{font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dash27-protocol small{font-size:7.5px;color:var(--muted)}.dash27-protocol-state{font-size:7.5px;font-weight:800;color:var(--muted)}.dash27-protocol.online .dash27-protocol-state{color:var(--d-green)}.dash27-protocol.offline .dash27-protocol-state{color:var(--d-red)}
      @media(max-width:1180px){.dash27-kpis{grid-template-columns:repeat(3,1fr)}.dash27-node-grid{grid-template-columns:repeat(2,1fr)}.dash27-protocol-grid{grid-template-columns:repeat(2,1fr)}}
      @media(max-width:860px){.dash27-hero{align-items:flex-start;flex-direction:column}.dash27-actions{width:100%;justify-content:space-between}.dash27-main-grid,.dash27-mid-grid,.dash27-bottom-grid{grid-template-columns:1fr}.dash27-kpis{grid-template-columns:repeat(2,1fr)}}
      @media(max-width:620px){.dash27{gap:12px}.dash27-hero{padding:18px;border-radius:18px}.dash27-title h1{font-size:25px}.dash27-actions{align-items:stretch;flex-direction:column}.dash27-refresh{justify-content:center}.dash27-kpis,.dash27-node-grid,.dash27-protocol-grid{grid-template-columns:1fr}.dash-kpi{min-height:92px}.dash27-sales-strip{grid-template-columns:1fr}.dash27-sub-body{align-items:center;flex-direction:column}.dash27-section-title{align-items:flex-start;flex-direction:column}.dash27-resources{grid-template-columns:repeat(3,1fr)}.dash27-tunnel{grid-template-columns:8px 1fr auto}.dash27-tunnel .badge{grid-column:2/4}.dash27-chart{height:190px}.dash27-chart svg{height:160px}}
    `}</style>
  </div></Shell>;
}
