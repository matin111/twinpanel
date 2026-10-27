"use client";

import {type FormEvent,useEffect,useMemo,useState} from "react";

import {Badge,Shell} from "./ui";
import styles from "./tunnel-control-center-v1.module.css";
import {TunnelServerPairSelectorV293} from "./tunnel-server-pair-selector-v293";
import type {AdminNode,AdminTunnel} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {modernTransportApi,type SmartTransportCandidate,type SmartTransportName,type SmartTransportState} from "../lib/modern-transport-api";
import {tunnelTransportApi,type TunnelTransportRow,type TunnelTransportState} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";

// TWINPANEL_TUNNEL_CONTROL_CENTER_V1
// TWINPANEL_MANUAL_CUTOVER_ELIGIBILITY_UI_V289
// TWINPANEL_SERVER_PAIR_SELECTION_NO_INSTALL_V293
// One data-driven control surface for every logical tunnel. Tunnel IDs are data,
// never UI feature flags. Manual cutover is health-based; SmartAuto qualification
// keeps its independent stability gate. Server selection is a logical-only action
// and never invokes create-managed or any transport installer.

type Draft={iran_node_id:number;exit_node_id:number;priority:number};
type Notice={tone:"ok"|"bad"|"warn";text:string}|null;

const labels:Record<string,string>={
  tp27_fast:"TP27 Fast",spoof_wg:"Spoof Tunnel",tp6_fast:"TP6 Fast",kernel_ipip:"Kernel IPIP",kernel_vxlan:"Kernel VXLAN",
  tp27_masque:"TP27 MASQUE H3",tp27_mieru_tcp:"TP27 Mieru TCP",tp27_tcp_direct:"TP27 Direct TCP",kernel_gre:"Kernel GRE",
  gost_tun:"GOST TUN/WSS",amneziawg:"AmneziaWG 3.1",netrix:"Netrix TUN",kcp_2027:"KCP 2027",arq_2027:"ARQ 2027",
  quic_2027:"QUIC 2027",tcp_2027:"TCP 2027",backhaul:"Backhaul",mtunnel:"MTunnel",ssh_tun:"SSH TUN",ssh_relay:"SSH Relay",
};

const normalize=(value:unknown)=>String(value??"").trim().toLowerCase();
const transportLabel=(value:unknown)=>labels[String(value??"").trim()]||String(value??"—");
const statusTone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const status=normalize(value);
  if(["online","active","healthy","ok","ready","qualified"].includes(status))return "ok";
  if(["offline","failed","error","down","stopped"].includes(status))return "bad";
  if(status==="manual")return "violet";
  return "warn";
};
const nodeLabel=(node:AdminNode|undefined,fallback:string)=>node?`${node.name} · ${node.public_ip||"—"}`:fallback;

function Modal({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}){
  return <div className={styles.modal} role="dialog" aria-modal="true">
    <button type="button" className={styles.modalBackdrop} aria-label="close" onClick={onClose}/>
    <div className={styles.modalCard}><div className={styles.modalHead}><b>{title}</b><button type="button" className={styles.iconButton} onClick={onClose}>×</button></div>{children}</div>
  </div>;
}

function Metric({label,value,hint}:{label:string;value:string|number;hint?:string}){
  return <div className={styles.metric}><span>{label}</span><b>{value}</b>{hint&&<small>{hint}</small>}</div>;
}

export function TunnelControlCenterV1(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [selectedId,setSelectedId]=useState(0);
  const [smart,setSmart]=useState<SmartTransportState|null>(null);
  const [registered,setRegistered]=useState<TunnelTransportState|null>(null);
  const [loading,setLoading]=useState(true);
  const [detailLoading,setDetailLoading]=useState(false);
  const [busy,setBusy]=useState("");
  const [notice,setNotice]=useState<Notice>(null);
  const [search,setSearch]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [draft,setDraft]=useState<Draft>({iran_node_id:0,exit_node_id:0,priority:100});
  const [spoofIran,setSpoofIran]=useState("");
  const [spoofExit,setSpoofExit]=useState("");

  const nodeMap=useMemo(()=>new Map(nodes.map(node=>[node.id,node])),[nodes]);
  const iranNodes=useMemo(()=>nodes.filter(node=>normalize(node.node_type)==="iran"),[nodes]);
  const exitNodes=useMemo(()=>nodes.filter(node=>normalize(node.node_type)==="exit"),[nodes]);
  const selectedTunnel=useMemo(()=>tunnels.find(row=>row.id===selectedId)||null,[tunnels,selectedId]);
  const selectedIran=selectedTunnel?nodeMap.get(selectedTunnel.iran_node_id):undefined;
  const selectedExit=selectedTunnel?nodeMap.get(selectedTunnel.exit_node_id):undefined;
  const candidates=useMemo(()=>Array.isArray(smart?.transports)?smart!.transports:[],[smart]);
  const registeredRows=useMemo(()=>Array.isArray(registered?.transports)?registered!.transports as TunnelTransportRow[]:[],[registered]);
  const activeTransport=normalize(smart?.active_transport||registered?.active_transport||selectedTunnel?.active_transport||selectedTunnel?.preferred_transport||selectedTunnel?.transport);
  const mode=normalize(smart?.mode||registered?.mode||selectedTunnel?.mode||"manual");

  const filteredTunnels=useMemo(()=>{
    const q=search.trim().toLowerCase();
    if(!q)return tunnels;
    return tunnels.filter(tunnel=>{
      const iran=nodeMap.get(tunnel.iran_node_id);const exit=nodeMap.get(tunnel.exit_node_id);
      return `${tunnel.id} ${tunnel.status||""} ${tunnel.active_transport||""} ${iran?.name||""} ${iran?.public_ip||""} ${exit?.name||""} ${exit?.public_ip||""}`.toLowerCase().includes(q);
    });
  },[tunnels,nodeMap,search]);

  const onlineCount=tunnels.filter(row=>normalize(row.status)==="online").length;
  const degradedCount=tunnels.filter(row=>normalize(row.status)==="degraded").length;
  const failedCount=Math.max(0,tunnels.length-onlineCount-degradedCount);
  const onlineCandidates=candidates.filter(row=>normalize(row.status)==="online").length;
  const autoQualifiedCandidates=candidates.filter(row=>Boolean(row.qualified)).length;
  const manualReadyCandidates=candidates.filter(row=>Boolean(row.manual_selectable)).length;

  const loadBase=async(silent=false,preferredId?:number)=>{
    if(!silent)setLoading(true);
    try{
      const [tunnelRows,nodeRows]=await Promise.all([legacyControlApi.tunnels(),legacyControlApi.nodes()]);
      setTunnels(tunnelRows);setNodes(nodeRows);
      setSelectedId(current=>{
        if(preferredId&&tunnelRows.some(row=>row.id===preferredId))return preferredId;
        if(current&&tunnelRows.some(row=>row.id===current))return current;
        return tunnelRows[0]?.id||0;
      });
    }catch(reason){if(!silent)setNotice({tone:"bad",text:reason instanceof Error?reason.message:String(reason)});}finally{if(!silent)setLoading(false);}
  };

  const loadDetail=async(id:number,silent=false)=>{
    if(!id){setSmart(null);setRegistered(null);return;}
    if(!silent)setDetailLoading(true);
    try{
      const [smartState,registeredState]=await Promise.all([modernTransportApi.state(id),tunnelTransportApi.transports(id)]);
      setSmart(smartState);setRegistered(registeredState);
      const spoof=(smartState.transports||[]).find(row=>row.transport==="spoof_wg");
      if(!silent){setSpoofIran(String(spoof?.configuration?.iran_spoof_ip||""));setSpoofExit(String(spoof?.configuration?.exit_spoof_ip||""));}
    }catch(reason){if(!silent)setNotice({tone:"bad",text:reason instanceof Error?reason.message:String(reason)});}finally{if(!silent)setDetailLoading(false);}
  };

  useEffect(()=>{void loadBase();const timer=window.setInterval(()=>void loadBase(true),15000);return()=>window.clearInterval(timer);},[]);
  useEffect(()=>{
    if(!selectedId){setSmart(null);setRegistered(null);return;}
    setNotice(null);void loadDetail(selectedId);
    const timer=window.setInterval(()=>void loadDetail(selectedId,true),10000);return()=>window.clearInterval(timer);
  },[selectedId]);

  const run=async(key:string,success:string,action:()=>Promise<unknown>,refresh=true)=>{
    if(busy)return null;setBusy(key);setNotice(null);
    try{
      const result=await action();setNotice({tone:"ok",text:success});await loadBase(true);if(refresh&&selectedId)await loadDetail(selectedId,true);return result;
    }catch(reason){setNotice({tone:"bad",text:reason instanceof Error?reason.message:String(reason)});return null;}finally{setBusy("");}
  };

  const openCreate=()=>{
    const iran=iranNodes.find(node=>normalize(node.status)==="online")||iranNodes[0];
    const exit=exitNodes.find(node=>normalize(node.status)==="online")||exitNodes[0];
    setDraft({iran_node_id:iran?.id||0,exit_node_id:exit?.id||0,priority:100});setCreateOpen(true);setNotice(null);
  };

  const createTunnel=async(event:FormEvent)=>{
    event.preventDefault();if(busy||!draft.iran_node_id||!draft.exit_node_id)return;setBusy("create");setNotice(null);
    try{
      const result=await legacyControlApi.createManagedTunnel({...draft,transport:"auto",is_active:true});
      const id=Number(result?.tunnel?.id||0);if(!id)throw new Error(pick("پاسخ ساخت تانل معتبر نبود.","Managed tunnel creation returned no tunnel ID."));
      setCreateOpen(false);await loadBase(true,id);setSelectedId(id);
      setNotice({tone:"ok",text:pick(`Tunnel #${id} ساخته شد و همان Pair باز شد.`,`Tunnel #${id} was created and opened.`)});
    }catch(reason){setNotice({tone:"bad",text:reason instanceof Error?reason.message:String(reason)});}finally{setBusy("");}
  };

  const onServerPairSelected=(tunnel:AdminTunnel)=>{
    const id=Number(tunnel.id||0);
    if(!id)return;
    setSelectedId(id);
    void loadBase(true,id);
    setNotice({tone:"ok",text:pick(`سرورها انتخاب شدند و Pair #${id} باز شد؛ هیچ Tunnel/Transport نصب یا بازسازی نشد.`,`Servers selected and pair #${id} opened; no tunnel or transport was installed or rebuilt.`)});
  };

  const setAuto=()=>{if(selectedId)void run(`auto-${selectedId}`,pick("Smart Auto برای همین Tunnel فعال شد.","Smart Auto enabled for this tunnel."),()=>modernTransportApi.setMode(selectedId,"auto"));};

  const setManual=(row:SmartTransportCandidate)=>{
    if(!selectedId||!row.manual_selectable)return;
    const name=row.transport as SmartTransportName;
    if(!window.confirm(pick(`مسیر Production این Tunnel به ${transportLabel(name)} تغییر کند؟ Cutover فقط بعد از fresh full health probe و تأیید هر دو Agent انجام می‌شود.`,`Switch this tunnel's production path to ${transportLabel(name)}? Cutover is protected by a fresh full health probe and both-Agent acceptance.`)))return;
    void run(`manual-${name}`,pick(`${transportLabel(name)} مسیر دستی Production شد.`,`${transportLabel(name)} is now the manual production path.`),()=>modernTransportApi.setMode(selectedId,"manual",name));
  };

  const installOrRepair=(row:SmartTransportCandidate)=>{
    if(!selectedId)return;const name=row.transport as SmartTransportName;
    if(name==="spoof_wg"&&!row.configured){setNotice({tone:"warn",text:pick("ابتدا IPهای Spoof را در همین کارت ذخیره کن.","Save both Spoof IPs in this card first.")});return;}
    const installed=normalize(row.status)!=="not_installed";
    if(!window.confirm(pick(`${installed?"تعمیر و تست":"نصب و تست"} ${transportLabel(name)} فقط روی Tunnel #${selectedId} انجام شود؟`,`Run ${installed?"repair and qualification":"install and qualification"} for ${transportLabel(name)} on tunnel #${selectedId}?`)))return;
    void run(`install-${name}`,pick(`${transportLabel(name)} اجرا و ارزیابی شد.`,`${transportLabel(name)} installation/repair and qualification finished.`),()=>modernTransportApi.install(selectedId,name));
  };

  const probe=(row:SmartTransportCandidate)=>{if(selectedId){const name=row.transport as SmartTransportName;void run(`probe-${name}`,pick(`تست سلامت ${transportLabel(name)} بروزرسانی شد.`,`Fresh health test finished for ${transportLabel(name)}.`),()=>modernTransportApi.probe(selectedId,name));}};

  const remove=(row:SmartTransportCandidate)=>{
    if(!selectedId)return;const name=row.transport as SmartTransportName;
    if(normalize(name)===activeTransport){setNotice({tone:"warn",text:pick("مسیر فعال قابل حذف نیست.","The active production path cannot be removed.")});return;}
    if(!window.confirm(pick(`${transportLabel(name)} از Tunnel #${selectedId} حذف شود؟`,`Remove ${transportLabel(name)} from tunnel #${selectedId}?`)))return;
    void run(`remove-${name}`,pick(`${transportLabel(name)} از همین Tunnel حذف شد.`,`${transportLabel(name)} was removed from this tunnel.`),()=>modernTransportApi.remove(selectedId,name));
  };

  const saveSpoof=()=>{if(selectedId&&spoofIran.trim()&&spoofExit.trim())void run("spoof-config",pick("تنظیمات Spoof برای همین Tunnel ذخیره شد.","Spoof settings saved for this tunnel."),()=>modernTransportApi.configureSpoof(selectedId,{iran_spoof_ip:spoofIran.trim(),exit_spoof_ip:spoofExit.trim()}));};

  const repairTunnel=()=>{
    if(!selectedId)return;if(!window.confirm(pick(`تعمیر عمیق Tunnel #${selectedId} اجرا شود؟ مسیرهای سالم بی‌دلیل تعویض نمی‌شوند.`,`Run deep repair for tunnel #${selectedId}? Healthy paths will not be replaced without evidence.`)))return;
    void run(`deep-repair-${selectedId}`,pick("تعمیر عمیق تمام شد و وضعیت دوباره دریافت شد.","Deep repair completed and state was refreshed."),()=>tunnelTransportApi.managedDeepRepair(selectedId));
  };

  const deleteTunnel=()=>{
    if(!selectedTunnel)return;if(!window.confirm(pick(`Tunnel #${selectedTunnel.id} حذف شود؟ این عملیات فقط برای Pair انتخاب‌شده است.`,`Delete tunnel #${selectedTunnel.id}? This affects only the selected pair.`)))return;
    const id=selectedTunnel.id;void run(`delete-${id}`,pick(`Tunnel #${id} حذف شد.`,`Tunnel #${id} deleted.`),()=>legacyControlApi.deleteTunnel(id),false).then(result=>{if(result!==null){setSelectedId(0);setSmart(null);setRegistered(null);void loadBase(true);}});
  };

  const manualReason=(row:SmartTransportCandidate)=>{
    if(normalize(row.transport)===activeTransport)return pick("مسیر فعال فعلی","Current active path");
    if(row.manual_selectable)return pick("آماده انتخاب دستی؛ Cutover با fresh probe محافظت می‌شود.","Manual ready; cutover is protected by a fresh probe.");
    if(row.manual_block_reason)return String(row.manual_block_reason);
    if(normalize(row.status)==="not_installed")return pick("ابتدا نصب و تست شود","Install and qualify first");
    if(normalize(row.status)!=="online")return pick("مسیر Online نیست","Transport is not online");
    return pick("سلامت مسیر باید دوباره تأیید شود","Transport health must be revalidated");
  };

  return <Shell active="/admin/tunnels">
    <div className={styles.page}>
      <header className={styles.hero}>
        <div><div className={styles.eyebrow}>TwinPanel · Network Fabric</div><h1>{pick("مرکز کنترل تانل‌ها","Tunnel Control Center")}</h1><p>{pick("یک UI و یک قرارداد برای ساخت، تست، انتخاب مسیر و تعمیر همه Tunnelها. شماره Tunnel هیچ قابلیت ویژه‌ای ایجاد نمی‌کند.","One control surface and one contract for creating, testing, selecting and repairing every tunnel. Tunnel IDs never unlock special UI behavior.")}</p></div>
        <div className={styles.heroActions}><button type="button" className={styles.secondaryButton} disabled={loading||Boolean(busy)} onClick={()=>void loadBase()}>{loading?"…":pick("بروزرسانی","Refresh")}</button><TunnelServerPairSelectorV293 disabled={loading||Boolean(busy)} onSelected={onServerPairSelected}/><button type="button" className={styles.primaryButton} onClick={openCreate}>＋ {pick("Tunnel جدید","New tunnel")}</button></div>
      </header>

      {notice&&<div className={`${styles.notice} ${notice.tone==="bad"?styles.noticeBad:notice.tone==="warn"?styles.noticeWarn:styles.noticeOk}`}>{notice.text}</div>}

      <section className={styles.stats}><Metric label={pick("کل Pairها","Pairs")} value={tunnels.length}/><Metric label={pick("آنلاین","Online")} value={onlineCount}/><Metric label="Degraded" value={degradedCount}/><Metric label={pick("نیاز به بررسی","Needs attention")} value={failedCount}/></section>

      <div className={styles.workspace}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHead}><div><b>{pick("Tunnelها","Tunnels")}</b><small>Iran → Exit</small></div><span>{filteredTunnels.length}</span></div>
          <input className={styles.search} value={search} onChange={event=>setSearch(event.target.value)} placeholder={pick("نام، IP یا ID...","Name, IP or ID...")}/>
          <div className={styles.tunnelList}>
            {loading&&<div className={styles.empty}>{pick("در حال دریافت...","Loading...")}</div>}
            {!loading&&filteredTunnels.length===0&&<div className={styles.empty}>{pick("Tunnel ثبت نشده. از «انتخاب سرور» Pair را بدون نصب ثبت کن یا Tunnel جدید بساز.","No tunnel registered. Use Select servers to register a pair without install, or create a new tunnel.")}</div>}
            {filteredTunnels.map(tunnel=>{
              const iran=nodeMap.get(tunnel.iran_node_id);const exit=nodeMap.get(tunnel.exit_node_id);const active=selectedId===tunnel.id;
              return <button key={tunnel.id} type="button" className={`${styles.tunnelItem} ${active?styles.tunnelItemActive:""}`} onClick={()=>setSelectedId(tunnel.id)}>
                <div className={styles.tunnelItemTop}><b>#{tunnel.id}</b><Badge tone={statusTone(tunnel.status)}>{String(tunnel.status||"—")}</Badge></div>
                <span>{iran?.name||`Iran #${tunnel.iran_node_id}`} <i>→</i> {exit?.name||`Exit #${tunnel.exit_node_id}`}</span>
                <small dir="ltr">{iran?.public_ip||"—"} → {exit?.public_ip||"—"}</small>
                <div className={styles.tunnelMeta}><em>{transportLabel(tunnel.active_transport||tunnel.preferred_transport||tunnel.transport)}</em><em>{normalize(tunnel.mode||"manual")}</em></div>
              </button>;
            })}
          </div>
        </aside>

        <main className={styles.main}>
          {!selectedTunnel&&<div className={styles.zeroState}><div className={styles.zeroIcon}>⇄</div><h2>{pick("یک Tunnel را انتخاب کن","Select a tunnel")}</h2><p>{pick("برای Pair موجود از «انتخاب سرور» استفاده کن؛ این کار نصب مجدد ندارد. برای Provision کامل از Tunnel جدید استفاده کن.","Use Select servers for an existing/logical pair without reinstall. Use New tunnel only for full provisioning.")}</p></div>}
          {selectedTunnel&&<>
            <section className={styles.topologyCard}>
              <div className={styles.topologyHead}><div><span>{pick("Pair انتخاب‌شده","Selected pair")}</span><h2>Tunnel #{selectedTunnel.id}</h2></div><div className={styles.topologyActions}><Badge tone={statusTone(selectedTunnel.status)}>{String(selectedTunnel.status||"—")}</Badge><button type="button" className={styles.dangerButton} disabled={Boolean(busy)} onClick={deleteTunnel}>{pick("حذف Tunnel","Delete")}</button></div></div>
              <div className={styles.topology}>
                <div className={styles.nodeBox}><span>IRAN</span><b>{selectedIran?.name||`Node #${selectedTunnel.iran_node_id}`}</b><small dir="ltr">{selectedIran?.public_ip||"—"}</small><em>{selectedIran?.status||"—"}</em></div>
                <div className={styles.linkBox}><small>{pick("مسیر فعال","Active path")}</small><b>{transportLabel(activeTransport)}</b><div className={styles.linkLine}><span/><i>→</i><span/></div><em>{mode.toUpperCase()}</em></div>
                <div className={styles.nodeBox}><span>EXIT</span><b>{selectedExit?.name||`Node #${selectedTunnel.exit_node_id}`}</b><small dir="ltr">{selectedExit?.public_ip||"—"}</small><em>{selectedExit?.status||"—"}</em></div>
              </div>
            </section>

            <section className={styles.controlBar}>
              <div><span>{pick("حالت کنترل","Control mode")}</span><b>{mode==="auto"?"SMART AUTO":"MANUAL"}</b></div>
              <div><span>{pick("Candidate آنلاین","Online candidates")}</span><b>{onlineCandidates}</b></div>
              <div><span>{pick("Manual آماده","Manual ready")}</span><b>{manualReadyCandidates}</b></div>
              <div><span>{pick("تأیید Auto","Auto qualified")}</span><b>{autoQualifiedCandidates}</b></div>
              <div className={styles.controlActions}><button type="button" className={styles.secondaryButton} disabled={Boolean(busy)||mode==="auto"} onClick={setAuto}>{mode==="auto"?pick("Smart Auto فعال","Smart Auto active"):pick("فعال‌سازی Smart Auto","Enable Smart Auto")}</button><button type="button" className={styles.secondaryButton} disabled={Boolean(busy)} onClick={repairTunnel}>{busy===`deep-repair-${selectedId}`?"…":pick("تعمیر و تشخیص","Repair & diagnose")}</button></div>
            </section>
            <div className={styles.notice + " " + styles.noticeWarn}>{pick("شرط ۶۰ ثانیه فقط برای Smart Auto است؛ انتخاب دستی بر اساس سلامت واقعی مسیر انجام می‌شود و endpoint قبل از Cutover یک fresh full health probe و تأیید هر دو Agent می‌گیرد.","The 60-second gate is only for Smart Auto. Manual selection is health-based and the endpoint requires a fresh full health probe and both-Agent acceptance before cutover.")}</div>

            <section>
              <div className={styles.sectionHead}><div><span>Data plane</span><h3>{pick("Transport Candidateها","Transport candidates")}</h3></div><small>{detailLoading?pick("در حال بروزرسانی...","Refreshing..."):pick("Install → Test → Select. همان کنترل برای همه Tunnelها.","Install → Test → Select. Same controls for every tunnel.")}</small></div>
              <div className={styles.candidateGrid}>
                {candidates.map(row=>{
                  const name=row.transport as SmartTransportName;const installed=normalize(row.status)!=="not_installed";const isActive=normalize(name)===activeTransport;const manualSelectable=Boolean(row.manual_selectable);const reason=manualReason(row);
                  return <article key={name} className={`${styles.candidateCard} ${isActive?styles.candidateActive:""}`}>
                    <div className={styles.candidateHead}><div><span>{row.family||row.iran_profile||"TRANSPORT"}</span><h4>{row.label||transportLabel(name)}</h4></div><Badge tone={row.qualified?"ok":statusTone(row.status)}>{row.qualified?pick("AUTO QUALIFIED","AUTO QUALIFIED"):String(row.status||"not_installed")}</Badge></div>
                    <div className={styles.candidateMetrics}>
                      <div><span>Latency</span><b>{row.latency_ms==null?"—":`${row.latency_ms} ms`}</b></div>
                      <div><span>{pick("پایداری Auto","Auto stability")}</span><b>{Math.round(Number(row.stable_seconds||0))}s</b></div>
                      <div><span>{pick("Manual","Manual")}</span><b>{isActive?pick("فعال","Active"):manualSelectable?pick("آماده","Ready"):pick("قفل","Locked")}</b></div>
                    </div>
                    {name==="spoof_wg"&&<div className={styles.spoofBox}><b>Spoof configuration</b><div className={styles.inlineFields}><label><span>Iran IP</span><input dir="ltr" value={spoofIran} onChange={event=>setSpoofIran(event.target.value)} placeholder="IPv4"/></label><label><span>Exit IP</span><input dir="ltr" value={spoofExit} onChange={event=>setSpoofExit(event.target.value)} placeholder="IPv4"/></label></div><button type="button" className={styles.smallButton} disabled={Boolean(busy)||!spoofIran.trim()||!spoofExit.trim()} onClick={saveSpoof}>{pick("ذخیره IPها","Save IPs")}</button></div>}
                    <p className={styles.reason}>{reason}</p>
                    {row.last_error&&<details className={styles.errorDetails}><summary>{pick("آخرین خطا","Last error")}</summary><code dir="ltr">{String(row.last_error)}</code></details>}
                    <div className={styles.cardActions}>
                      {installed&&<button type="button" className={styles.smallButton} disabled={Boolean(busy)} onClick={()=>probe(row)}>{busy===`probe-${name}`?"…":pick("تست سلامت","Health test")}</button>}
                      <button type="button" className={styles.smallPrimary} disabled={Boolean(busy)||(name==="spoof_wg"&&!row.configured)} onClick={()=>installOrRepair(row)}>{busy===`install-${name}`?"…":installed?pick("تعمیر و تست","Repair & test"):pick("نصب و تست","Install & test")}</button>
                      <button type="button" className={styles.smallButton} disabled={Boolean(busy)||isActive||!manualSelectable} title={reason} onClick={()=>setManual(row)}>{busy===`manual-${name}`?"…":isActive?pick("مسیر فعال","Active path"):manualSelectable?pick("انتخاب دستی","Select manual"):pick("هنوز آماده نیست","Not ready")}</button>
                      {installed&&!isActive&&<button type="button" className={styles.smallDanger} disabled={Boolean(busy)} onClick={()=>remove(row)}>{pick("حذف","Remove")}</button>}
                    </div>
                  </article>;
                })}
                {!detailLoading&&candidates.length===0&&<div className={styles.empty}>{pick("Candidate مدرنی برای این Tunnel ثبت نشده است.","No modern candidates are registered for this tunnel.")}</div>}
              </div>
            </section>

            <section className={styles.registryCard}>
              <div className={styles.sectionHead}><div><span>Registry</span><h3>{pick("تمام مسیرهای ثبت‌شده","All registered paths")}</h3></div><small>{pick("نمایش وضعیت واقعی DB؛ کنترل اصلی بالا برای همه Tunnelها واحد است.","DB visibility only; the primary control surface above is identical for every tunnel.")}</small></div>
              <div className={styles.registryTable}><div className={styles.registryRowHead}><span>{pick("مسیر","Transport")}</span><span>{pick("وضعیت","Status")}</span><span>Latency</span><span>{pick("فعال","Enabled")}</span></div>{registeredRows.map((row,index)=><div key={String(row.id||`${row.transport}-${index}`)} className={styles.registryRow}><b>{transportLabel(row.transport)}</b><Badge tone={statusTone(row.status)}>{String(row.status||"—")}</Badge><span dir="ltr">{row.latency_ms==null?"—":`${row.latency_ms} ms`}</span><span>{row.enabled===false?pick("خیر","No"):pick("بله","Yes")}</span></div>)}</div>
            </section>
          </>}
        </main>
      </div>

      {createOpen&&<Modal title={pick("ساخت Tunnel جدید","Create new tunnel")} onClose={()=>!busy&&setCreateOpen(false)}>
        <form className={styles.createForm} onSubmit={createTunnel}>
          <div className={styles.createIntro}><b>{pick("یک Pair، یک Control Plane","One pair, one control plane")}</b><p>{pick("Backend رسمی create-managed نودها را آماده می‌کند. بعد از ساخت همین Control Center همان Tunnel را باز می‌کند؛ هیچ UI مخصوص ID ساخته نمی‌شود.","The official create-managed backend prepares the pair. After creation this same control center opens it; no ID-specific UI is created.")}</p></div>
          <label><span>{pick("نود ایران","Iran node")}</span><select value={draft.iran_node_id} onChange={event=>setDraft(value=>({...value,iran_node_id:Number(event.target.value)}))}>{iranNodes.map(node=><option key={node.id} value={node.id}>{nodeLabel(node,`#${node.id}`)} · {node.status||"—"}</option>)}</select></label>
          <div className={styles.flowArrow}>↓</div>
          <label><span>{pick("نود خروجی","Exit node")}</span><select value={draft.exit_node_id} onChange={event=>setDraft(value=>({...value,exit_node_id:Number(event.target.value)}))}>{exitNodes.map(node=><option key={node.id} value={node.id}>{nodeLabel(node,`#${node.id}`)} · {node.status||"—"}</option>)}</select></label>
          <label><span>{pick("اولویت","Priority")}</span><input type="number" min={1} max={9999} value={draft.priority} onChange={event=>setDraft(value=>({...value,priority:Number(event.target.value)||100}))}/></label>
          <div className={styles.createFooter}><button type="button" className={styles.secondaryButton} disabled={Boolean(busy)} onClick={()=>setCreateOpen(false)}>{pick("انصراف","Cancel")}</button><button type="submit" className={styles.primaryButton} disabled={Boolean(busy)||!draft.iran_node_id||!draft.exit_node_id}>{busy==="create"?pick("در حال ساخت و آماده‌سازی...","Creating and provisioning..."):pick("ساخت و آماده‌سازی Tunnel","Create & provision tunnel")}</button></div>
        </form>
      </Modal>}
    </div>
  </Shell>;
}
