"use client";

import {useEffect,useMemo,useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import styles from "./outbound-performance-lab.module.css";


type OutboundRow={type:string;tag:string;server?:string;server_port?:number};
type NodeRow={id:number;name:string;public_ip:string;outbounds:OutboundRow[]};
type Inventory={nodes:NodeRow[]};
type Profile="quick"|"standard"|"full";
type ScoreProfile="balanced"|"latency"|"download"|"upload"|"stability";
type Budget={
  profile:Profile;parallel_streams:number;payload_total_upper_bound_mib:number;
  estimated_wire_upper_bound_mib:number;estimated_wire_upper_bound_bytes:number;
};
type Transfer={
  measured_payload_mib?:number;measured_download_bytes?:number;measured_upload_bytes?:number;
  payload_total_upper_bound_mib?:number;estimated_wire_upper_bound_mib?:number;
};
type Freshness={state?:"fresh"|"recent"|"stale"|"unknown";age_seconds?:number|null};
type Result={
  ok:boolean;tag:string;score?:number;score_version?:number;quality?:string;exit_ip?:string|null;
  latency_ms?:number|null;latency_p50_ms?:number|null;latency_p95_ms?:number|null;
  jitter_ms?:number|null;probe_loss_pct?:number|null;download_mbps?:number|null;upload_mbps?:number|null;
  parallel_download_mbps?:number|null;parallel_upload_mbps?:number|null;
  loaded_latency_ms?:number|null;loaded_latency_p50_ms?:number|null;loaded_latency_p95_ms?:number|null;
  loaded_jitter_ms?:number|null;loaded_probe_loss_pct?:number|null;bufferbloat_ms?:number|null;
  tls_ms?:number|null;ttfb_ms?:number|null;http_version?:string|null;advanced_error?:string|null;
  stability_score?:number|null;confidence_score?:number|null;confidence_level?:string|null;
  transfer?:Transfer;freshness?:Freshness;
};
type Recommendation={tag?:string;score?:number;stability_score?:number;confidence_score?:number;metric?:string;value?:number|null};
type Recommendations={
  source?:string;best_overall?:Recommendation|null;lowest_latency?:Recommendation|null;
  best_download?:Recommendation|null;best_upload?:Recommendation|null;most_stable?:Recommendation|null;
  lowest_bufferbloat?:Recommendation|null;
};
type LabState={
  benchmarkable_tags:string[];latest:Record<string,Result>;ranking:Result[];profiles:Budget[];
  recommendations:Recommendations;updated_at?:string|null;
};
type Tuning={
  kernel?:string|null;default_interface?:string|null;tcp_congestion_control?:string|null;
  tcp_available_congestion_control?:string[];default_qdisc?:string|null;live_qdisc?:string|null;
  tcp_mtu_probing?:string|null;bbr_supported?:boolean;bbr_loadable?:boolean;fq_loadable?:boolean;accelerator_active?:boolean;
};

async function api<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    const detail=payload&&typeof payload==="object"&&"detail" in payload?(payload as {detail?:unknown}).detail:null;
    if(typeof detail==="string")throw new Error(detail);
    if(detail&&typeof detail==="object"){
      const item=detail as {message?:unknown;error?:unknown;reason?:unknown};
      const text=[item.message,item.error,item.reason].filter(Boolean).map(String).join(" · ");
      if(text)throw new Error(text);
    }
    throw new Error(`API ${response.status}`);
  }
  return payload as T;
}

function fmt(value:number|null|undefined,digits=1){return value==null?"—":Number(value).toFixed(digits)}
function best(a:number|null|undefined,b:number|null|undefined){return Math.max(Number(a||0),Number(b||0))||null}
function tone(q?:string){return q==="excellent"||q==="good"?styles.good:q==="fair"?styles.fair:styles.bad}
function mib(bytes:number|null|undefined){return bytes==null?"—":`${(Number(bytes)/1024/1024).toFixed(1)} MiB`}

export function OutboundPerformanceInline({nodeId}:{nodeId:number}){
  const {pick}=useI18n();
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [state,setState]=useState<LabState|null>(null);
  const [tuning,setTuning]=useState<Tuning|null>(null);
  const [tests,setTests]=useState<Record<string,Result>>({});
  const [profile,setProfile]=useState<Profile>("standard");
  const [scoreProfile,setScoreProfile]=useState<ScoreProfile>("balanced");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [progress,setProgress]=useState("");

  const node=useMemo(()=>inventory?.nodes.find(item=>item.id===nodeId)??null,[inventory,nodeId]);
  const rows=useMemo(()=>new Map((node?.outbounds||[]).map(item=>[item.tag,item])),[node]);
  const current=useMemo(()=>({...state?.latest,...tests}),[state,tests]);
  const ranking=useMemo(()=>Object.values(current).sort((a,b)=>Number(b.score||0)-Number(a.score||0)),[current]);
  const bestRoute=useMemo(()=>ranking.find(item=>item.ok&&Number(item.score||0)>0)??null,[ranking]);
  const budget=useMemo(()=>state?.profiles.find(item=>item.profile===profile)??null,[state,profile]);
  const routeCount=state?.benchmarkable_tags.length||0;
  const allTestEstimate=budget?Number((budget.estimated_wire_upper_bound_mib*routeCount).toFixed(1)):null;
  const recommendations=state?.recommendations||{};

  const loadNode=async(id:number)=>{
    if(!id)return;
    const [inv,lab,tune]=await Promise.all([
      api<Inventory>("/v1/settings/vpn/outbounds"),
      api<LabState>(`/v1/settings/vpn/outbound-performance-lab/${id}`),
      api<Tuning>(`/v1/settings/vpn/outbound-performance/${id}/tuning`),
    ]);
    setInventory(inv);setState(lab);setTuning(tune);setTests({});
  };
  useEffect(()=>{if(nodeId)void loadNode(nodeId).catch(exc=>setError(exc instanceof Error?exc.message:String(exc)));},[nodeId]);

  const runOne=async(tag:string)=>{
    const result=await api<Result>(`/v1/settings/vpn/outbound-performance-lab/${nodeId}/${encodeURIComponent(tag)}/test`,{method:"POST",body:JSON.stringify({profile,score_profile:scoreProfile})});
    setTests(old=>({...old,[tag]:result}));return result;
  };
  const testOne=async(tag:string)=>{
    setBusy(`test:${tag}`);setError("");setNotice("");
    try{
      const r=await runOne(tag);
      setNotice(pick(`${tag}: دانلود ${fmt(best(r.download_mbps,r.parallel_download_mbps),2)} · آپلود ${fmt(best(r.upload_mbps,r.parallel_upload_mbps),2)} Mbps · P95 ${fmt(r.latency_p95_ms,1)} ms`,`${tag}: ${fmt(best(r.download_mbps,r.parallel_download_mbps),2)} down · ${fmt(best(r.upload_mbps,r.parallel_upload_mbps),2)} Mbps up · P95 ${fmt(r.latency_p95_ms,1)} ms`));
      await loadNode(nodeId);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };
  const testAll=async()=>{
    const tags=state?.benchmarkable_tags||[];
    if(!tags.length)return;
    const estimate=allTestEstimate==null?"—":`${allTestEstimate} MiB`;
    if(!window.confirm(pick(`تست ${tags.length} مسیر با پروفایل ${profile} اجرا شود؟ سقف تقریبی مصرف شبکه ${estimate} است و مسیر Production تغییر نمی‌کند.`,`Test ${tags.length} routes with ${profile}? Approximate network upper bound is ${estimate}; production routing will not change.`)))return;
    setBusy("all");setError("");setNotice("");
    try{
      for(let i=0;i<tags.length;i++){
        setProgress(pick(`در حال تست ${i+1} از ${tags.length}: ${tags[i]}`,`Testing ${i+1}/${tags.length}: ${tags[i]}`));
        try{await runOne(tags[i]);}
        catch(exc){setTests(old=>({...old,[tags[i]]:{ok:false,tag:tags[i],score:0,advanced_error:exc instanceof Error?exc.message:String(exc)}}));}
      }
      await loadNode(nodeId);
      setNotice(pick("تست کامل همه مسیرها تمام شد و رتبه‌بندی دوباره محاسبه شد.","All route benchmarks completed and ranking was recalculated."));
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");setProgress("");}
  };
  const selectBest=async()=>{
    if(!bestRoute)return;
    if(!window.confirm(pick(`مسیر پیش‌فرض نود روی ${bestRoute.tag} قرار بگیرد؟ این تغییر فقط با تأیید شما انجام می‌شود.`,`Set node default route to ${bestRoute.tag}? This change happens only with your confirmation.`)))return;
    setBusy("best");setError("");
    try{await api(`/v1/settings/vpn/outbounds/${nodeId}/default`,{method:"POST",body:JSON.stringify({tag:bestRoute.tag})});window.location.reload();}
    catch(exc){setError(exc instanceof Error?exc.message:String(exc));setBusy("");}
  };
  const applyTuning=async()=>{
    if(!window.confirm(pick("BBR + FQ با Backup و Rollback فعال شود؟ Route، MTU، Firewall و qdisc زنده تغییر نمی‌کنند.","Enable BBR + FQ with backup/rollback? Routes, MTU, firewall and the live qdisc are not changed.")))return;
    setBusy("tune");setError("");
    try{await api(`/v1/settings/vpn/outbound-performance/${nodeId}/tuning/apply`,{method:"POST",body:JSON.stringify({profile:"bbr_fq"})});await loadNode(nodeId);setNotice(pick("BBR + FQ اعمال شد؛ برای مقایسه A/B دوباره تست سرعت بگیرید.","BBR + FQ applied; rerun the benchmark for an A/B comparison."));}
    catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };
  const rollback=async()=>{
    if(!window.confirm(pick("تنظیمات TCP به Backup قبل از TwinPanel برگردد؟","Restore the TCP settings saved before TwinPanel tuning?")))return;
    setBusy("rollback");setError("");
    try{await api(`/v1/settings/vpn/outbound-performance/${nodeId}/tuning/rollback`,{method:"POST"});await loadNode(nodeId);setNotice(pick("Rollback کامل شد.","Rollback completed."));}
    catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const canTune=Boolean((tuning?.bbr_supported||tuning?.bbr_loadable)&&tuning?.fq_loadable&&!tuning?.accelerator_active);
  const recommendationCards=[
    [pick("بهترین کلی","Best overall"),recommendations.best_overall],
    [pick("کمترین تأخیر","Lowest latency"),recommendations.lowest_latency],
    [pick("بیشترین دانلود","Best download"),recommendations.best_download],
    [pick("بیشترین آپلود","Best upload"),recommendations.best_upload],
    [pick("پایدارترین","Most stable"),recommendations.most_stable],
    [pick("کمترین Bufferbloat","Lowest bufferbloat"),recommendations.lowest_bufferbloat],
  ] as const;

  return <section id="outbound-performance" className={`${styles.page} ${styles.panel}`}>
    <div className={styles.panelHead}>
      <div><div className={styles.kicker}>PERFORMANCE V3 · REAL PATH · P95</div><h2>{pick("سرعت، پایداری و بهینه‌سازی Outbound","Outbound speed, stability & optimization")}</h2><p>{pick("Download/Upload واقعی روی مسیر انتخاب‌شده، Parallel Throughput، P50/P95، Idle/Loaded Latency، Jitter، Bufferbloat، TLS/TTFB و Confidence؛ بدون تغییر خودکار Route.","Real download/upload through the selected path, parallel throughput, P50/P95, idle/loaded latency, jitter, bufferbloat, TLS/TTFB and confidence; no automatic route switching.")}</p></div>
      <div className={styles.toolbar}>
        <label><span>{pick("پروفایل تست","Profile")}</span><select className={styles.select} value={profile} onChange={event=>setProfile(event.target.value as Profile)} disabled={Boolean(busy)}><option value="quick">Quick</option><option value="standard">Standard</option><option value="full">Full</option></select></label>
        <label><span>{pick("اولویت","Ranking")}</span><select className={styles.select} value={scoreProfile} onChange={event=>setScoreProfile(event.target.value as ScoreProfile)} disabled={Boolean(busy)}><option value="balanced">Balanced</option><option value="latency">Latency</option><option value="download">Download</option><option value="upload">Upload</option><option value="stability">Stability</option></select></label>
        <button className={styles.button} onClick={()=>void testAll()} disabled={Boolean(busy)||!routeCount}>{busy==="all"?pick("در حال تست...","Testing..."):pick("تست همه مسیرها","Test all")}</button>
        <button className={styles.secondary} onClick={()=>void selectBest()} disabled={Boolean(busy)||!bestRoute}>{busy==="best"?pick("اعمال...","Applying..."):pick("اعمال بهترین مسیر","Apply best route")}</button>
      </div>
    </div>

    <div className={styles.stats}>
      <article className={styles.stat}><span>{pick("سقف مصرف هر مسیر","Per-route upper bound")}</span><strong>{budget?`${budget.estimated_wire_upper_bound_mib} MiB`:"—"}</strong><small>{pick("برآورد شبکه؛ Payload و مرحله Loaded محدود شده‌اند.","Network estimate; payload and loaded phase are bounded.")}</small></article>
      <article className={styles.stat}><span>{pick("سقف تست همه","Test-all upper bound")}</span><strong>{allTestEstimate==null?"—":`${allTestEstimate} MiB`}</strong><small>{routeCount} {pick("مسیر قابل Benchmark","benchmarkable routes")}</small></article>
      <article className={styles.stat}><span>{pick("بهترین مسیر فعلی","Current best")}</span><strong>{bestRoute?.tag||"—"}</strong><small>{bestRoute?`Score ${fmt(bestRoute.score,0)} · Confidence ${fmt(bestRoute.confidence_score,0)}`:pick("نیازمند تست واقعی","Requires a real benchmark")}</small></article>
      <article className={styles.stat}><span>{pick("TCP Accelerator","TCP accelerator")}</span><strong>{tuning?.accelerator_active?"BBR + FQ":pick("اختیاری","Optional")}</strong><small>{pick("فقط با تأیید Admin و Rollback واقعی","Admin-confirmed with real rollback")}</small></article>
    </div>

    <div className={styles.explain}>
      {recommendationCards.map(([label,item])=><article key={label}><b>{label}</b><p>{item?.tag||"—"}{item?.value!=null?` · ${fmt(item.value,1)}`:""}</p></article>)}
    </div>

    {progress?<div className={styles.progress}>{progress}</div>:null}{error?<div className={styles.error}>{error}</div>:null}{notice?<div className={styles.notice}>{notice}</div>:null}
    <div className={styles.ranking}>{ranking.length?ranking.map(item=>{const row=rows.get(item.tag);return <article className={styles.routeCard} key={item.tag}>
      <div className={styles.routeTop}><div className={styles.routeTitle}><b>{item.tag}</b><small>{row?.type==="direct"?"Internet / WAN":[row?.server,row?.server_port].filter(Boolean).join(":")||"—"} · {item.exit_ip||"Exit IP —"}</small><span className={`${styles.quality} ${tone(item.quality)}`}>{item.quality||"untested"}</span></div><div className={styles.score}><strong>{fmt(item.score,0)}</strong><span>V3 SCORE</span></div></div>
      <div className={styles.metrics}>
        <div className={styles.metric}><span>Download</span><b>{fmt(best(item.download_mbps,item.parallel_download_mbps),2)} Mbps</b></div>
        <div className={styles.metric}><span>Upload</span><b>{fmt(best(item.upload_mbps,item.parallel_upload_mbps),2)} Mbps</b></div>
        <div className={styles.metric}><span>Latency P50 / P95</span><b>{fmt(item.latency_p50_ms,1)} / {fmt(item.latency_p95_ms,1)} ms</b></div>
        <div className={styles.metric}><span>Loaded P50 / P95</span><b>{fmt(item.loaded_latency_p50_ms,1)} / {fmt(item.loaded_latency_p95_ms,1)} ms</b></div>
        <div className={styles.metric}><span>Bufferbloat</span><b>{fmt(item.bufferbloat_ms,1)} ms</b></div>
        <div className={styles.metric}><span>Jitter</span><b>{fmt(item.jitter_ms,1)} / {fmt(item.loaded_jitter_ms,1)} ms</b></div>
        <div className={styles.metric}><span>Probe Loss</span><b>{fmt(item.probe_loss_pct,1)} / {fmt(item.loaded_probe_loss_pct,1)}%</b></div>
        <div className={styles.metric}><span>Stability</span><b>{fmt(item.stability_score,0)} / 100</b></div>
        <div className={styles.metric}><span>Confidence</span><b>{fmt(item.confidence_score,0)} / 100 · {item.confidence_level||"—"}</b></div>
        <div className={styles.metric}><span>TLS / TTFB</span><b>{fmt(item.tls_ms,1)} / {fmt(item.ttfb_ms,1)} ms</b></div>
        <div className={styles.metric}><span>HTTP</span><b>{item.http_version||"—"}</b></div>
        <div className={styles.metric}><span>{pick("Payload اندازه‌گیری‌شده","Measured payload")}</span><b>{item.transfer?.measured_payload_mib==null?"—":`${fmt(item.transfer.measured_payload_mib,1)} MiB`}</b></div>
      </div>
      <div className={styles.cardActions}><button onClick={()=>void testOne(item.tag)} disabled={Boolean(busy)}>{busy===`test:${item.tag}`?pick("در حال تست...","Testing..."):pick("تست این مسیر","Test route")}</button></div>{item.advanced_error?<small>{item.advanced_error}</small>:null}
    </article>}):<div className={styles.empty}>{pick("هنوز تستی ثبت نشده؛ «تست همه مسیرها» را بزنید.","No benchmark yet; run Test all.")}</div>}</div>

    <div className={styles.explain}>
      <article><b>{pick("TCP Host","TCP host")}</b><p>{tuning?.kernel||"—"} · {tuning?.default_interface||"—"}<br/>CC: {tuning?.tcp_congestion_control||"—"} · qdisc: {tuning?.default_qdisc||"—"}</p></article>
      <article><b>BBR + FQ</b><p>{tuning?.accelerator_active?pick("فعال است. تست قبل/بعد معیار تصمیم باشد.","Active. Use before/after benchmarks as the decision gate."):pick("اختیاری و با Backup؛ فقط با تأیید Admin. برای مسیرهای TCP مفید است و وعده افزایش سرعت UDP نیست.","Opt-in with backup and admin confirmation. It targets TCP paths and does not promise UDP acceleration.")}</p><div className={styles.cardActions}><button onClick={()=>void applyTuning()} disabled={Boolean(busy)||!canTune}>{pick("اعمال BBR + FQ","Apply BBR + FQ")}</button><button onClick={()=>void rollback()} disabled={Boolean(busy)}>{pick("Rollback","Rollback")}</button></div></article>
      <article><b>{pick("قواعد ایمنی","Safety")}</b><p>{pick("Target تست ثابت و کنترل‌شده است؛ URL دلخواه کاربر پذیرفته نمی‌شود. TP27/VXLAN، Route، MTU و Firewall در Benchmark دست‌کاری نمی‌شوند.","The benchmark target is fixed and server-controlled; user URLs are not accepted. TP27/VXLAN, routes, MTU and firewall are not mutated by benchmarks.")}</p></article>
    </div>
  </section>;
}
