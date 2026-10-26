"use client";

import {useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import policyStyles from "./outbound-policy-center.module.css";
import styles from "./outbound-performance-lab.module.css";


type OutboundRow={type:string;tag:string;server?:string;server_port?:number};
type NodeRow={id:number;name:string;public_ip:string;outbounds:OutboundRow[]};
type Inventory={nodes:NodeRow[]};
type Profile="quick"|"standard"|"full";
type ScoreProfile="balanced"|"latency"|"download"|"upload"|"stability";
type Result={
  ok:boolean;tag:string;score?:number;quality?:string;exit_ip?:string|null;
  latency_ms?:number|null;jitter_ms?:number|null;probe_loss_pct?:number|null;
  download_mbps?:number|null;upload_mbps?:number|null;parallel_download_mbps?:number|null;parallel_upload_mbps?:number|null;
  loaded_latency_ms?:number|null;loaded_jitter_ms?:number|null;loaded_probe_loss_pct?:number|null;bufferbloat_ms?:number|null;
  tls_ms?:number|null;ttfb_ms?:number|null;http_version?:string|null;advanced_error?:string|null;
};
type AdvancedState={benchmarkable_tags:string[];latest:Record<string,Result>};
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

export function OutboundPerformanceInline(){
  const {pick}=useI18n();
  const [target,setTarget]=useState<Element|null>(null);
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [nodeId,setNodeId]=useState(0);
  const [state,setState]=useState<AdvancedState|null>(null);
  const [tuning,setTuning]=useState<Tuning|null>(null);
  const [tests,setTests]=useState<Record<string,Result>>({});
  const [profile,setProfile]=useState<Profile>("standard");
  const [scoreProfile,setScoreProfile]=useState<ScoreProfile>("balanced");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [progress,setProgress]=useState("");

  useEffect(()=>{
    const find=()=>document.querySelector(`.${policyStyles.page}`);
    const existing=find();
    if(existing){setTarget(existing);return;}
    const timer=window.setInterval(()=>{const node=find();if(node){setTarget(node);window.clearInterval(timer);}},50);
    return()=>window.clearInterval(timer);
  },[]);

  const node=useMemo(()=>inventory?.nodes.find(item=>item.id===nodeId)??null,[inventory,nodeId]);
  const rows=useMemo(()=>new Map((node?.outbounds||[]).map(item=>[item.tag,item])),[node]);
  const current=useMemo(()=>({...state?.latest,...tests}),[state,tests]);
  const ranking=useMemo(()=>Object.values(current).sort((a,b)=>Number(b.score||0)-Number(a.score||0)),[current]);

  const loadInventory=async()=>{
    const data=await api<Inventory>("/v1/settings/vpn/outbounds");setInventory(data);
    setNodeId(currentId=>data.nodes.some(item=>item.id===currentId)?currentId:(data.nodes[0]?.id||0));
  };
  const loadNode=async(id:number)=>{
    if(!id)return;
    const [advanced,tune]=await Promise.all([
      api<AdvancedState>(`/v1/settings/vpn/outbound-performance/${id}/advanced-state`),
      api<Tuning>(`/v1/settings/vpn/outbound-performance/${id}/tuning`),
    ]);
    setState(advanced);setTuning(tune);setTests({});
  };
  useEffect(()=>{void loadInventory().catch(exc=>setError(exc instanceof Error?exc.message:String(exc)));},[]);
  useEffect(()=>{if(nodeId)void loadNode(nodeId).catch(exc=>setError(exc instanceof Error?exc.message:String(exc)));},[nodeId]);

  const runOne=async(tag:string)=>{
    const result=await api<Result>(`/v1/settings/vpn/outbound-performance/${nodeId}/${encodeURIComponent(tag)}/advanced-test`,{method:"POST",body:JSON.stringify({profile,score_profile:scoreProfile})});
    setTests(old=>({...old,[tag]:result}));return result;
  };
  const testOne=async(tag:string)=>{setBusy(`test:${tag}`);setError("");setNotice("");try{const r=await runOne(tag);setNotice(pick(`${tag}: دانلود ${fmt(best(r.download_mbps,r.parallel_download_mbps),2)} · آپلود ${fmt(best(r.upload_mbps,r.parallel_upload_mbps),2)} Mbps · Bufferbloat ${fmt(r.bufferbloat_ms,0)} ms`,`${tag}: ${fmt(best(r.download_mbps,r.parallel_download_mbps),2)} down · ${fmt(best(r.upload_mbps,r.parallel_upload_mbps),2)} Mbps up · ${fmt(r.bufferbloat_ms,0)} ms bufferbloat`));await loadNode(nodeId);}catch(exc){setError(exc instanceof Error?exc.message:String(exc));}finally{setBusy("");}};
  const testAll=async()=>{const tags=state?.benchmarkable_tags||[];setBusy("all");setError("");setNotice("");try{for(let i=0;i<tags.length;i++){setProgress(pick(`در حال تست ${i+1} از ${tags.length}: ${tags[i]}`,`Testing ${i+1}/${tags.length}: ${tags[i]}`));try{await runOne(tags[i]);}catch(exc){setTests(old=>({...old,[tags[i]]:{ok:false,tag:tags[i],score:0,advanced_error:exc instanceof Error?exc.message:String(exc)}}));}}await loadNode(nodeId);setNotice(pick("تست کامل همه مسیرها تمام شد.","All route benchmarks completed."));}catch(exc){setError(exc instanceof Error?exc.message:String(exc));}finally{setBusy("");setProgress("");}};
  const applyTuning=async()=>{if(!window.confirm(pick("BBR + FQ با Backup و Rollback فعال شود؟ Route، MTU، Firewall و qdisc زنده تغییر نمی‌کنند.","Enable BBR + FQ with backup/rollback? Routes, MTU, firewall and the live qdisc are not changed.")))return;setBusy("tune");setError("");try{await api(`/v1/settings/vpn/outbound-performance/${nodeId}/tuning/apply`,{method:"POST",body:JSON.stringify({profile:"bbr_fq"})});await loadNode(nodeId);setNotice(pick("BBR + FQ اعمال شد؛ برای مقایسه دوباره تست سرعت بگیرید.","BBR + FQ applied; rerun the benchmark for an A/B comparison."));}catch(exc){setError(exc instanceof Error?exc.message:String(exc));}finally{setBusy("");}};
  const rollback=async()=>{if(!window.confirm(pick("تنظیمات TCP به Backup قبل از TwinPanel برگردد؟","Restore the TCP settings saved before TwinPanel tuning?")))return;setBusy("rollback");setError("");try{await api(`/v1/settings/vpn/outbound-performance/${nodeId}/tuning/rollback`,{method:"POST"});await loadNode(nodeId);setNotice(pick("Rollback کامل شد.","Rollback completed."));}catch(exc){setError(exc instanceof Error?exc.message:String(exc));}finally{setBusy("");}};

  if(!target)return null;
  const canTune=Boolean((tuning?.bbr_supported||tuning?.bbr_loadable)&&tuning?.fq_loadable&&!tuning?.accelerator_active);

  return createPortal(<section id="outbound-performance" className={styles.panel}>
    <div className={styles.panelHead}>
      <div><div className={styles.kicker}>PERFORMANCE · SPEED · BUFFERBLOAT</div><h2>{pick("سرعت و بهینه‌سازی Outbound","Outbound speed & optimization")}</h2><p>{pick("همین‌جا داخل Outbound: Download/Upload، Parallel Throughput، Idle/Loaded Latency، Jitter، Bufferbloat، TLS/TTFB و TCP Accelerator.","Integrated directly in Outbound: download/upload, parallel throughput, idle/loaded latency, jitter, bufferbloat, TLS/TTFB and TCP acceleration.")}</p></div>
      <div className={styles.toolbar}><label><span>{pick("نود","Node")}</span><select className={styles.select} value={nodeId} onChange={event=>setNodeId(Number(event.target.value))} disabled={Boolean(busy)}>{(inventory?.nodes||[]).map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select></label><label><span>{pick("پروفایل تست","Profile")}</span><select className={styles.select} value={profile} onChange={event=>setProfile(event.target.value as Profile)} disabled={Boolean(busy)}><option value="quick">Quick</option><option value="standard">Standard</option><option value="full">Full</option></select></label><label><span>{pick("اولویت","Ranking")}</span><select className={styles.select} value={scoreProfile} onChange={event=>setScoreProfile(event.target.value as ScoreProfile)} disabled={Boolean(busy)}><option value="balanced">Balanced</option><option value="latency">Latency</option><option value="download">Download</option><option value="upload">Upload</option><option value="stability">Stability</option></select></label><button className={styles.button} onClick={()=>void testAll()} disabled={Boolean(busy)||!(state?.benchmarkable_tags.length)}>{busy==="all"?pick("در حال تست...","Testing..."):pick("تست همه مسیرها","Test all")}</button></div>
    </div>
    {progress?<div className={styles.progress}>{progress}</div>:null}{error?<div className={styles.error}>{error}</div>:null}{notice?<div className={styles.notice}>{notice}</div>:null}
    <div className={styles.ranking}>{ranking.length?ranking.map(item=>{const row=rows.get(item.tag);return <article className={styles.routeCard} key={item.tag}><div className={styles.routeTop}><div className={styles.routeTitle}><b>{item.tag}</b><small>{row?.type==="direct"?"Internet / WAN":[row?.server,row?.server_port].filter(Boolean).join(":")||"—"} · {item.exit_ip||"Exit IP —"}</small><span className={`${styles.quality} ${tone(item.quality)}`}>{item.quality||"untested"}</span></div><div className={styles.score}><strong>{fmt(item.score,0)}</strong><span>SCORE</span></div></div><div className={styles.metrics}><div className={styles.metric}><span>Download</span><b>{fmt(best(item.download_mbps,item.parallel_download_mbps),2)} Mbps</b></div><div className={styles.metric}><span>Upload</span><b>{fmt(best(item.upload_mbps,item.parallel_upload_mbps),2)} Mbps</b></div><div className={styles.metric}><span>Idle / Loaded</span><b>{fmt(item.latency_ms,1)} / {fmt(item.loaded_latency_ms,1)} ms</b></div><div className={styles.metric}><span>Bufferbloat</span><b>{fmt(item.bufferbloat_ms,1)} ms</b></div><div className={styles.metric}><span>Jitter</span><b>{fmt(item.jitter_ms,1)} / {fmt(item.loaded_jitter_ms,1)} ms</b></div><div className={styles.metric}><span>TLS / TTFB</span><b>{fmt(item.tls_ms,1)} / {fmt(item.ttfb_ms,1)} ms</b></div><div className={styles.metric}><span>Probe Loss</span><b>{fmt(item.probe_loss_pct,1)} / {fmt(item.loaded_probe_loss_pct,1)}%</b></div><div className={styles.metric}><span>HTTP</span><b>{item.http_version||"—"}</b></div></div><div className={styles.cardActions}><button onClick={()=>void testOne(item.tag)} disabled={Boolean(busy)}>{busy===`test:${item.tag}`?pick("در حال تست...","Testing..."):pick("تست این مسیر","Test route")}</button></div>{item.advanced_error?<small>{item.advanced_error}</small>:null}</article>}):<div className={styles.empty}>{pick("هنوز تستی ثبت نشده؛ «تست همه مسیرها» را بزنید.","No benchmark yet; run Test all.")}</div>}</div>
    <div className={styles.explain}><article><b>{pick("TCP Host","TCP host")}</b><p>{tuning?.kernel||"—"} · {tuning?.default_interface||"—"}<br/>CC: {tuning?.tcp_congestion_control||"—"} · qdisc: {tuning?.default_qdisc||"—"}</p></article><article><b>BBR + FQ</b><p>{tuning?.accelerator_active?pick("فعال است. تست قبل/بعد معیار تصمیم باشد.","Active. Use before/after benchmarks as the decision gate."):pick("اختیاری و با Backup؛ فقط با تأیید Admin.","Opt-in with backup; admin confirmation required.")}</p><div className={styles.cardActions}><button onClick={()=>void applyTuning()} disabled={Boolean(busy)||!canTune}>{pick("اعمال BBR + FQ","Apply BBR + FQ")}</button><button onClick={()=>void rollback()} disabled={Boolean(busy)}>{pick("Rollback","Rollback")}</button></div></article><article><b>{pick("قواعد ایمنی","Safety")}</b><p>{pick("TP27/VXLAN، Route، MTU، Firewall و qdisc زنده در Benchmark/Apply دست‌کاری نمی‌شوند.","TP27/VXLAN, routes, MTU, firewall and the live qdisc are not mutated by benchmark/apply.")}</p></article></div>
  </section>,target);
}
