"use client";

import {useEffect,useMemo,useState} from "react";

import {Badge,Card,Shell} from "./ui";
import {legacyControlApi} from "../lib/legacy-control-api";
import {tunnelTransportApi,type TunnelTransportRow,type TunnelTransportState} from "../lib/tunnel-transport-api";
import {
  modernTransportApi,
  type SmartTransportCandidate,
  type SmartTransportName,
  type SmartTransportState,
  type SpoofCompatibilityResult,
} from "../lib/modern-transport-api";
import {useI18n} from "../lib/i18n";

const labels:Record<string,string>={
  tp27_fast:"TP27 Fast",
  spoof_wg:"Spoof Tunnel",
  tp6_fast:"TP6 Fast",
  kernel_ipip:"Kernel IPIP",
  kernel_vxlan:"Kernel VXLAN",
  tp27_masque:"TP27 MASQUE H3",
  tp27_mieru_tcp:"TP27 Mieru TCP",
  tp27_tcp_direct:"TP27 Direct TCP",
  kernel_gre:"Kernel GRE",
  gost_tun:"GOST TUN/WSS",
  amneziawg:"AmneziaWG 3.1",
  netrix:"Netrix TUN",
  kcp_2027:"KCP 2027",
  arq_2027:"ARQ 2027",
  quic_2027:"QUIC 2027",
  tcp_2027:"TCP 2027",
  backhaul:"Backhaul",
  mtunnel:"MTunnel",
  ssh_tun:"SSH TUN",
  ssh_relay:"SSH Relay",
};

const protocols=[
  {key:"cisco",fa:"Cisco / OpenConnect",en:"Cisco / OpenConnect"},
  {key:"openvpn",fa:"OpenVPN",en:"OpenVPN"},
  {key:"wireguard",fa:"WireGuard",en:"WireGuard"},
  {key:"l2tp",fa:"L2TP / IPsec",en:"L2TP / IPsec"},
  {key:"xray",fa:"Xray / V2Ray",en:"Xray / V2Ray"},
] as const;

const normalized=(value:unknown)=>String(value??"").trim().toLowerCase();
const label=(value:unknown)=>labels[String(value??"").trim()]||String(value??"—");
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const status=normalized(value);
  if(["online","active","healthy","ok","ready","qualified"].includes(status))return "ok";
  if(["offline","failed","error","down","stopped"].includes(status))return "bad";
  return "warn";
};
const mbps=(value:unknown)=>{
  const n=Number(value);
  return Number.isFinite(n)&&n>0?`${n.toFixed(n>=100?0:1)} Mbps`:"—";
};
const duration=(value:unknown)=>{
  const n=Math.max(0,Number(value)||0);
  if(n>=60)return `${Math.floor(n/60)}m ${Math.round(n%60)}s`;
  return `${Math.round(n)}s`;
};

export function SmartTransportsRuntimeV26(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<Array<{id:number;iran_node_id:number;exit_node_id:number;status?:string;active_transport?:string|null;preferred_transport?:string|null}>>([]);
  const [selected,setSelected]=useState(0);
  const [smart,setSmart]=useState<SmartTransportState|null>(null);
  const [allState,setAllState]=useState<TunnelTransportState|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");
  const [iranSpoofIp,setIranSpoofIp]=useState("");
  const [exitSpoofIp,setExitSpoofIp]=useState("");
  const [spoofCompatibility,setSpoofCompatibility]=useState<SpoofCompatibilityResult|null>(null);

  const loadTunnels=async()=>{
    const rows=await legacyControlApi.tunnels();
    setTunnels(rows);
    setSelected(current=>current&&rows.some(row=>row.id===current)?current:(rows[0]?.id||0));
  };

  const loadState=async(id:number,silent=false)=>{
    if(!id){setSmart(null);setAllState(null);setLoading(false);return;}
    if(!silent){setLoading(true);setError("");}
    try{
      const [modern,all]=await Promise.all([
        modernTransportApi.state(id),
        tunnelTransportApi.transports(id),
      ]);
      setSmart(modern);
      setAllState(all);
      if(!silent){
        const spoof=(modern.transports||[]).find(row=>row.transport==="spoof_wg");
        setIranSpoofIp(String(spoof?.configuration?.iran_spoof_ip||""));
        setExitSpoofIp(String(spoof?.configuration?.exit_spoof_ip||""));
      }
    }catch(reason){
      if(!silent)setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      if(!silent)setLoading(false);
    }
  };

  useEffect(()=>{void loadTunnels().catch(reason=>{setError(reason instanceof Error?reason.message:String(reason));setLoading(false);});},[]);
  useEffect(()=>{
    if(!selected)return;
    setSpoofCompatibility(null);
    void loadState(selected);
    const timer=window.setInterval(()=>void loadState(selected,true),10000);
    return()=>window.clearInterval(timer);
  },[selected]);

  const candidates=useMemo(()=>Array.isArray(smart?.transports)?smart!.transports:[],[smart]);
  const allRows=useMemo(()=>Array.isArray(allState?.transports)?allState!.transports as TunnelTransportRow[]:[],[allState]);
  const candidateNames=useMemo(()=>new Set(candidates.map(row=>String(row.transport))),[candidates]);
  const visibleAllRows=useMemo(()=>allRows.filter(row=>candidateNames.has(String(row.transport))||(row.enabled!==false&&normalized(row.status)!=="not_installed")),[allRows,candidateNames]);
  const selectedTunnel=tunnels.find(row=>row.id===selected);
  const currentMode=normalized(smart?.mode||allState?.mode||"manual");
  const activeName=normalized(smart?.active_transport||allState?.active_transport);
  const preferredName=normalized(smart?.preferred_transport||allState?.preferred_transport);
  const online=candidates.filter(row=>normalized(row.status)==="online");
  const qualified=candidates.filter(row=>row.qualified);
  const failoverReady=qualified.filter(row=>normalized(row.transport)!==activeName);
  const activeCandidate=candidates.find(row=>normalized(row.transport)===activeName);

  const run=async(key:string,message:string,action:()=>Promise<unknown>)=>{
    if(!selected||busy)return;
    setBusy(key);setError("");setSuccess("");
    try{
      await action();
      setSuccess(message);
      await loadState(selected,true);
      await loadTunnels();
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  const install=(row:SmartTransportCandidate)=>{
    const name=row.transport as SmartTransportName;
    if(name==="spoof_wg"&&!row.configured){
      setError(pick("ابتدا IP اسپوف ایران و خارج را ذخیره کنید.","Save the Iran and Exit spoof IPs first."));
      return;
    }
    if(!window.confirm(pick(`نصب/بازسازی و Qualification مسیر ${label(name)} انجام شود؟`,`Install/rebuild and qualify ${label(name)}?`)))return;
    void run(`install-${name}`,pick(`${label(name)} نصب و ارزیابی شد.`,`${label(name)} installation and qualification finished.`),()=>modernTransportApi.install(selected,name));
  };

  const remove=(row:SmartTransportCandidate)=>{
    const name=row.transport as SmartTransportName;
    if(normalized(name)===activeName){
      setError(pick("مسیر فعال Production قابل حذف نیست.","The active production path cannot be removed."));
      return;
    }
    if(!window.confirm(pick(`${label(name)} از همین تانل حذف شود؟`,`Remove ${label(name)} from this tunnel?`)))return;
    void run(`remove-${name}`,pick(`${label(name)} حذف شد.`,`${label(name)} was removed.`),()=>modernTransportApi.remove(selected,name));
  };

  const setAuto=()=>{
    if(!window.confirm(pick(
      "Smart Auto فقط بین مسیرهای نصب‌شده، آنلاین و تأییدشده انتخاب می‌کند. همه سرویس‌های L3 با مسیر منتخب جابه‌جا می‌شوند. فعال شود؟",
      "Smart Auto selects only installed, online and qualified paths. All L3 services follow the selected path. Enable it?"
    )))return;
    void run("auto",pick("Smart Auto برای این تانل فعال شد.","Smart Auto is enabled for this tunnel."),()=>modernTransportApi.setMode(selected,"auto"));
  };

  const setManual=(row:SmartTransportCandidate)=>{
    const name=row.transport as SmartTransportName;
    if(!window.confirm(pick(`مسیر Production به ${label(name)} تغییر کند؟ همه سرویس‌های L3 از مسیر جدید تبعیت می‌کنند.`,`Switch production to ${label(name)}? All L3 services will follow the new path.`)))return;
    void run(`manual-${name}`,pick(`${label(name)} مسیر دستی Production شد.`,`${label(name)} is now the manual production path.`),()=>modernTransportApi.setMode(selected,"manual",name));
  };

  const saveSpoof=()=>{
    const iran=iranSpoofIp.trim();
    const exit=exitSpoofIp.trim();
    if(!iran||!exit){setError(pick("هر دو IP اسپوف الزامی است.","Both spoof IPs are required."));return;}
    void run("spoof-config",pick("IPهای Spoof ذخیره شد.","Spoof IPs saved."),()=>modernTransportApi.configureSpoof(selected,{iran_spoof_ip:iran,exit_spoof_ip:exit}));
  };

  const checkSpoof=async()=>{
    if(!selected||busy)return;
    setBusy("spoof-check");setError("");setSuccess("");
    try{
      const result=await modernTransportApi.checkSpoofCompatibility(selected);
      setSpoofCompatibility(result);
      setSuccess(result.compatible?pick("هر دو سرور برای Spoof آماده‌اند.","Both servers are ready for Spoof."):pick("پیش‌نیازهای Spoof کامل نیست.","Spoof prerequisites are incomplete."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/tunnel-transports">
    <div className="page tp-transport-page">
      <section className="tp-hero">
        <div className="tp-hero-copy">
          <div className="tp-eyebrow">{pick("Transport Control Plane","Transport Control Plane")}</div>
          <h1>{pick("مسیرهای تانل و Failover","Tunnel Transports & Failover")}</h1>
          <p>{pick(
            "Cisco، OpenVPN، WireGuard، L2TP و Xray روی یک لایه L3 مشترک قرار دارند و همیشه از Active Transport همان تانل تبعیت می‌کنند. مسیر Standby فقط بعد از Qualification وارد Failover می‌شود.",
            "Cisco, OpenVPN, WireGuard, L2TP and Xray share one L3 service plane and always follow the tunnel active transport. A standby path joins failover only after qualification."
          )}</p>
        </div>
        <div className="tp-hero-actions">
          <button type="button" className="ghost" disabled={loading||Boolean(busy)} onClick={()=>{void loadTunnels();if(selected)void loadState(selected);}}>{loading?"…":pick("بروزرسانی وضعیت","Refresh status")}</button>
        </div>
      </section>

      {error&&<div className="runtime-error tp-message">{error}</div>}
      {success&&<div className="runtime-success tp-message">{success}</div>}

      <section className="tp-controlbar">
        <div className="tp-pair-select">
          <span>{pick("تانل","Tunnel")}</span>
          <select value={selected} onChange={event=>setSelected(Number(event.target.value))}>
            {tunnels.length===0&&<option value={0}>{pick("تانلی ثبت نشده","No tunnel registered")}</option>}
            {tunnels.map(row=><option key={row.id} value={row.id}>#{row.id} · Iran #{row.iran_node_id} → Exit #{row.exit_node_id}</option>)}
          </select>
          <Badge tone={tone(selectedTunnel?.status)}>{selectedTunnel?.status||"—"}</Badge>
        </div>
        <div className="tp-mode-actions">
          <span className={`tp-mode-pill ${currentMode==="auto"?"is-auto":"is-manual"}`}>{currentMode==="auto"?"Smart Auto":"Manual"}</span>
          <button type="button" className="primary-soft" disabled={!selected||Boolean(busy)||currentMode==="auto"} onClick={setAuto}>{busy==="auto"?"…":currentMode==="auto"?pick("Smart Auto فعال","Smart Auto enabled"):pick("فعال‌سازی Smart Auto","Enable Smart Auto")}</button>
        </div>
      </section>

      <section className="tp-overview-grid">
        <div className="tp-overview-card accent"><span>{pick("مسیر فعال","Active transport")}</span><strong dir="ltr">{label(activeName)}</strong><small>{pick("مسیر واقعی Production","Current production path")}</small></div>
        <div className="tp-overview-card"><span>{pick("مسیر ترجیحی","Preferred")}</span><strong dir="ltr">{label(preferredName)}</strong><small>{smart?.promotion_policy||"health_then_speed"}</small></div>
        <div className="tp-overview-card"><span>{pick("مسیرهای آنلاین","Online paths")}</span><strong>{online.length}</strong><small>{pick(`${qualified.length} مسیر تأییدشده`,`${qualified.length} qualified`)}</small></div>
        <div className="tp-overview-card"><span>{pick("Failover آماده","Failover ready")}</span><strong>{failoverReady.length}</strong><small>{failoverReady.length?failoverReady.map(row=>label(row.transport)).join(" · "):pick("مسیر Standby تأییدشده نداریم","No qualified standby yet")}</small></div>
      </section>

      <section className="tp-service-plane">
        <div className="tp-section-head">
          <div><span className="tp-eyebrow">{pick("Unified L3 Service Plane","Unified L3 Service Plane")}</span><h2>{pick("پوشش پروتکل‌ها","Protocol coverage")}</h2></div>
          <Badge tone="ok">{pick("متصل به Active Transport","BOUND TO ACTIVE")}</Badge>
        </div>
        <div className="tp-protocol-row">
          {protocols.map(protocol=><div className="tp-protocol-chip" key={protocol.key}><span className="tp-protocol-dot"/><b>{pick(protocol.fa,protocol.en)}</b><small>{pick("Active + Failover","Active + Failover")}</small></div>)}
        </div>
        <p className="tp-section-note">{pick(
          "این وضعیت به معنی اجرای هم‌زمان دو Transport نیست؛ فقط یک مسیر Active ترافیک را حمل می‌کند و Candidateهای Qualified برای Failover آماده می‌مانند.",
          "This does not mean two transports carry traffic simultaneously; one path is active while qualified candidates remain ready for failover."
        )}</p>
      </section>

      <div className="tp-transport-grid">
        {candidates.map(row=>{
          const benchmark=row.benchmark||{};
          const installed=normalized(row.status)!=="not_installed";
          const isActive=normalized(row.transport)===activeName;
          const isPreferred=normalized(row.transport)===preferredName;
          const isSpoof=row.transport==="spoof_wg";
          const progress=Math.min(100,Math.round((Number(row.stable_seconds||0)/Math.max(1,Number(row.required_stable_seconds||60)))*100));
          const standbyReady=Boolean(row.qualified&&!isActive);
          return <Card key={row.transport} className={`tp-transport-card ${isActive?"is-active":""} ${standbyReady?"is-standby":""}`}>
            <div className="tp-card-top">
              <div>
                <div className="tp-card-title-row"><h3>{row.label||label(row.transport)}</h3>{isActive&&<span className="tp-role active">{pick("ACTIVE","ACTIVE")}</span>}{!isActive&&standbyReady&&<span className="tp-role standby">{pick("STANDBY","STANDBY")}</span>}{isPreferred&&!isActive&&<span className="tp-role preferred">{pick("PREFERRED","PREFERRED")}</span>}</div>
                <p>{row.iran_profile||row.family||"Full-L3 transport"}</p>
              </div>
              <Badge tone={row.qualified?"ok":tone(row.status)}>{row.qualified?pick("تأییدشده","QUALIFIED"):String(row.status||"not_installed")}</Badge>
            </div>

            <div className="tp-metric-grid">
              <div><span>Latency</span><b dir="ltr">{row.latency_ms==null?"—":`${row.latency_ms} ms`}</b></div>
              <div><span>{pick("پایداری","Stability")}</span><b dir="ltr">{duration(row.stable_seconds)}</b></div>
              <div><span>{pick("دانلود","Download")}</span><b dir="ltr">{mbps(benchmark.download_mbps)}</b></div>
              <div><span>{pick("آپلود","Upload")}</span><b dir="ltr">{mbps(benchmark.upload_mbps)}</b></div>
              <div><span>{pick("امتیاز","Score")}</span><b dir="ltr">{mbps(benchmark.weighted_mbps)}</b></div>
              <div><span>{pick("Failover","Failover")}</span><b>{isActive?pick("مسیر اصلی","Primary"):standbyReady?pick("آماده","Ready"):pick("در انتظار تأیید","Pending")}</b></div>
            </div>

            <div className="tp-progress"><span style={{width:`${progress}%`}}/></div>

            <div className="tp-card-protocols">
              {protocols.map(protocol=><span key={protocol.key}>{pick(protocol.fa,protocol.en)}</span>)}
            </div>

            {row.description&&<p className="tp-description">{row.description}</p>}
            {row.auto_block_reason&&<div className="runtime-warning compact" dir="ltr">{String(row.auto_block_reason)}</div>}
            {row.last_error&&<div className="runtime-error compact" dir="ltr">{String(row.last_error)}</div>}

            {isSpoof&&<details className="tp-spoof-panel">
              <summary>{pick("تنظیمات Spoof Tunnel","Spoof Tunnel setup")}</summary>
              <div className="tp-spoof-content">
                <div className="tp-spoof-status">
                  <span>{pick("آمادگی سرورها","Server readiness")}</span>
                  <b>{spoofCompatibility?(spoofCompatibility.compatible?pick("آماده","Ready"):pick("نیاز به اصلاح","Needs fix")):pick("بررسی نشده","Not checked")}</b>
                  <button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void checkSpoof()}>{busy==="spoof-check"?"…":pick("بررسی سرورها","Check servers")}</button>
                </div>
                <div className="tp-spoof-fields">
                  <label><span>{pick("IP Spoof ایران","Iran spoof IP")}</span><input dir="ltr" value={iranSpoofIp} onChange={event=>setIranSpoofIp(event.target.value)} disabled={Boolean(busy)||normalized(row.status)==="online"} placeholder="IPv4"/></label>
                  <label><span>{pick("IP Spoof خارج","Exit spoof IP")}</span><input dir="ltr" value={exitSpoofIp} onChange={event=>setExitSpoofIp(event.target.value)} disabled={Boolean(busy)||normalized(row.status)==="online"} placeholder="IPv4"/></label>
                </div>
                <button type="button" className="primary-soft" disabled={Boolean(busy)||normalized(row.status)==="online"} onClick={saveSpoof}>{busy==="spoof-config"?"…":pick("ذخیره IPها","Save IPs")}</button>
              </div>
            </details>}

            <div className="tp-card-actions">
              <button type="button" className="primary-soft" disabled={Boolean(busy)||(isSpoof&&!row.configured)} onClick={()=>install(row)}>{busy===`install-${row.transport}`?"…":installed?pick("بازسنجی و تست","Requalify & test"):pick("نصب و تست","Install & test")}</button>
              {row.selectable&&<button type="button" className="ghost" disabled={Boolean(busy)||isActive} onClick={()=>setManual(row)}>{busy===`manual-${row.transport}`?"…":isActive?pick("مسیر فعال","Active path"):pick("انتخاب به‌عنوان Production","Use as production")}</button>}
              {installed&&!isActive&&<button type="button" className="danger" disabled={Boolean(busy)} onClick={()=>remove(row)}>{busy===`remove-${row.transport}`?"…":pick("حذف","Remove")}</button>}
            </div>
          </Card>;
        })}
      </div>

      <Card className="tp-registry-card">
        <div className="tp-section-head"><div><span className="tp-eyebrow">{pick("Registry","Registry")}</span><h2>{pick("وضعیت همه مسیرهای ثبت‌شده","All registered transports")}</h2></div></div>
        {loading?<div className="runtime-loading">{pick("در حال دریافت…","Loading…")}</div>:visibleAllRows.length?<div className="table"><table><thead><tr><th>{pick("مسیر","Transport")}</th><th>{pick("وضعیت","Status")}</th><th>Latency</th><th>{pick("فعال","Enabled")}</th><th>{pick("آخرین سلامت","Last healthy")}</th></tr></thead><tbody>
          {visibleAllRows.map((row,index)=><tr key={String(row.id||`${row.transport}-${index}`)}><td dir="ltr"><b>{label(row.transport)}</b></td><td><Badge tone={tone(row.status)}>{String(row.status||"—")}</Badge></td><td dir="ltr">{row.latency_ms==null?"—":`${row.latency_ms} ms`}</td><td>{row.enabled===false?pick("خیر","No"):pick("بله","Yes")}</td><td>{row.last_healthy_at?new Date(String(row.last_healthy_at)).toLocaleString("fa-IR"):"—"}</td></tr>)}
        </tbody></table></div>:<div className="runtime-empty">{pick("مسیر دیگری ثبت نشده است.","No other transport is registered.")}</div>}
      </Card>

      <div className="tp-footnote">{pick(
        `Active اکنون ${label(activeCandidate?.transport||activeName)} است. تغییر مسیر فقط با انتخاب دستی یا Smart Auto انجام می‌شود؛ نصب Candidate به‌تنهایی مسیر کاربران را عوض نمی‌کند.`,
        `The active path is ${label(activeCandidate?.transport||activeName)}. Traffic changes only through manual selection or Smart Auto; installing a candidate alone never switches users.`
      )}</div>
    </div>
  </Shell>;
}
