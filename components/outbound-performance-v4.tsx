"use client";

import {useEffect,useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import styles from "./outbound-performance-v4.module.css";


type NodeRow={id:number;name:string;public_ip:string};
type Inventory={nodes:NodeRow[]};
type MetricRow={
  tag?:string;score?:number;stability_score?:number;confidence_score?:number;
  effective_download_mbps?:number|null;effective_upload_mbps?:number|null;
  latency_p95_ms?:number|null;loaded_latency_p95_ms?:number|null;bufferbloat_ms?:number|null;
  bufferbloat_grade?:string;use_case_scores?:Record<string,number>;
};
type SmartRoute={
  current_tag:string;candidate_tag?:string|null;should_switch:boolean;reason:string;score_gain?:number|null;
  current?:MetricRow|null;candidate?:MetricRow|null;
};
type Tuning={
  kernel?:string;tcp_congestion_control?:string;default_qdisc?:string;live_qdisc?:string;
  tcp_mtu_probing?:string;bbr_supported?:boolean;bbr_loadable?:boolean;fq_loadable?:boolean;accelerator_active?:boolean;
  v4_backup_available?:boolean;v4_active?:boolean;v4_state_path?:string;
};
type V4State={
  node_id:number;node_name:string;benchmarkable_tags:string[];smart_route:SmartRoute;tuning:Tuning;
  capabilities:Record<string,boolean>;
};
type AbResult={
  baseline:MetricRow;tuned:MetricRow;decision:{keep_tuning:boolean;score_gain?:number|null;download_gain_pct?:number|null;upload_gain_pct?:number|null;loaded_latency_regression_pct?:number|null;reason:string};
  rolled_back:boolean;effective_tuning_active:boolean;
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

function num(value:number|null|undefined,digits=1){return value==null?"—":Number(value).toFixed(digits)}
function reasonLabel(reason:string,fa:boolean){
  const map:Record<string,[string,string]>={
    current_is_best:["مسیر فعلی بهترین است","Current route is best"],
    candidate_clears_hysteresis:["کاندید با اختلاف امن بهتر است","Candidate clears hysteresis"],
    current_failed:["مسیر فعلی در تست تازه Fail شده است","Current route failed a fresh test"],
    current_unmeasured:["ابتدا مسیر فعلی را Benchmark کن","Benchmark the current route first"],
    current_stale_retest:["نتیجه مسیر فعلی قدیمی است؛ دوباره تست کن","Current measurement is stale; retest it"],
    current_low_confidence_retest:["Confidence مسیر فعلی کافی نیست؛ Retest لازم است","Current confidence is too low; retest it"],
    hysteresis_hold:["اختلاف برای سوییچ کافی نیست","Hysteresis holds the current route"],
    no_eligible_candidate:["کاندید تازه و قابل‌اعتماد نداریم","No fresh trusted candidate"],
    hold:["مسیر حفظ می‌شود","Hold current route"],
  };
  const pair=map[reason]||[reason,reason];return fa?pair[0]:pair[1];
}
function useCaseLine(row:MetricRow|undefined,fa:boolean){
  const scores=row?.use_case_scores;
  if(!scores)return "";
  return `${fa?"Realtime":"Realtime"} ${num(scores.realtime)} · ${fa?"Stream":"Stream"} ${num(scores.streaming)} · ${fa?"Bulk":"Bulk"} ${num(scores.bulk)} · ${fa?"Upload":"Upload"} ${num(scores.upload_backup)}`;
}

export function OutboundPerformanceV4(){
  const {pick,lang}=useI18n();
  const fa=lang==="fa";
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [nodeId,setNodeId]=useState(0);
  const [state,setState]=useState<V4State|null>(null);
  const [tag,setTag]=useState("");
  const [profile,setProfile]=useState<"quick"|"standard"|"full">("standard");
  const [ab,setAb]=useState<AbResult|null>(null);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  const loadState=async(id:number)=>{
    if(!id)return;
    const data=await api<V4State>(`/v1/settings/vpn/outbound-performance-v4/${id}`);
    setState(data);
    setTag(current=>data.benchmarkable_tags.includes(current)?current:(data.smart_route.candidate_tag||data.smart_route.current_tag||data.benchmarkable_tags[0]||""));
  };
  const load=async()=>{
    setError("");
    const inv=await api<Inventory>("/v1/settings/vpn/outbounds");
    setInventory(inv);
    const id=inv.nodes.some(item=>item.id===nodeId)?nodeId:(inv.nodes[0]?.id||0);
    setNodeId(id);
    if(id)await loadState(id);
  };
  useEffect(()=>{void load().catch(exc=>setError(exc instanceof Error?exc.message:String(exc)));},[]);
  useEffect(()=>{if(nodeId)void loadState(nodeId).catch(exc=>setError(exc instanceof Error?exc.message:String(exc)));},[nodeId]);

  const smart=async()=>{
    if(!state?.smart_route.should_switch||!state.smart_route.candidate_tag)return;
    if(!window.confirm(pick(`مسیر پیش‌فرض به ${state.smart_route.candidate_tag} تغییر کند؟ Guard فقط نتیجه تازه، مسیر فعلی اندازه‌گیری‌شده و Confidence کافی را قبول می‌کند.`,`Switch default route to ${state.smart_route.candidate_tag}? The guard requires fresh results, a measured current route and sufficient confidence.`)))return;
    setBusy("smart");setError("");setNotice("");
    try{
      const result=await api<{applied:boolean;default_tag:string}>(`/v1/settings/vpn/outbound-performance-v4/${nodeId}/smart-route`,{method:"POST",body:JSON.stringify({apply:true})});
      setNotice(result.applied?pick(`مسیر هوشمند روی ${result.default_tag} اعمال شد.`,`Smart route applied: ${result.default_tag}.`):pick("Guard اجازه سوییچ نداد.","Guard kept the current route."));
      await loadState(nodeId);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const tune=async()=>{
    if(state?.tuning.v4_backup_available)return;
    if(!window.confirm(pick("BBR + FQ + PLPMTUD محافظه‌کارانه فعال شود؟ Backup ساخته می‌شود و live qdisc تعویض نمی‌شود.","Enable BBR + FQ + conservative PLPMTUD? A backup is created and the live qdisc is not replaced.")))return;
    setBusy("tune");setError("");setNotice("");
    try{
      await api(`/v1/settings/vpn/outbound-performance-v4/${nodeId}/tuning/apply`,{method:"POST"});
      setNotice(pick("شتاب‌دهنده دستی اعمال شد. برای اجرای A/B با Baseline تمیز، ابتدا Rollback v4 را بزن.","Manual tuning is active. Roll back v4 before running a clean A/B baseline."));
      await loadState(nodeId);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const rollback=async()=>{
    if(!state?.tuning.v4_backup_available)return;
    if(!window.confirm(pick("تنظیمات v4 به وضعیت Backup برگردد؟","Restore v4 tuning to its backup state?")))return;
    setBusy("rollback");setError("");setNotice("");
    try{await api(`/v1/settings/vpn/outbound-performance-v4/${nodeId}/tuning/rollback`,{method:"POST"});setNotice(pick("Rollback انجام شد و Baseline تمیز دوباره قابل تست است.","Rollback completed; a clean A/B baseline is available again."));await loadState(nodeId);}
    catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const optimize=async()=>{
    if(!tag||state?.tuning.v4_backup_available)return;
    const traffic=profile==="full"?pick("این تست Full مصرف شبکه بیشتری دارد.","Full profile uses more network traffic."):"";
    if(!window.confirm(pick(`A/B واقعی روی ${tag} اجرا شود؟ Baseline گرفته می‌شود، BBR/FQ/PLPMTUD اعمال می‌شود و اگر سود امن نداشته باشد خودکار Rollback می‌شود. ${traffic}`,`Run a real A/B test on ${tag}? It benchmarks baseline, applies BBR/FQ/PLPMTUD and automatically rolls back when no safe gain is measured. ${traffic}`)))return;
    setBusy("ab");setError("");setNotice("");setAb(null);
    try{
      const result=await api<AbResult>(`/v1/settings/vpn/outbound-performance-v4/${nodeId}/${encodeURIComponent(tag)}/ab-optimize`,{method:"POST",body:JSON.stringify({profile,score_profile:"balanced",auto_rollback:true})});
      setAb(result);
      setNotice(result.rolled_back?pick("بهبود امن تأیید نشد و تنظیمات خودکار Rollback شد.","No safe gain was confirmed; tuning was automatically rolled back."):pick("بهبود اندازه‌گیری شد و تنظیمات حفظ شد.","Measured improvement confirmed; tuning was kept."));
      await loadState(nodeId);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const smartRoute=state?.smart_route;
  const tuningLocked=Boolean(state?.tuning.v4_backup_available);
  const tuneAvailable=Boolean((state?.tuning.bbr_supported||state?.tuning.bbr_loadable)&&state?.tuning.fq_loadable&&!tuningLocked);

  return <section className={styles.wrap} dir={fa?"rtl":"ltr"}>
    <div className={styles.head}>
      <div><span>PERFORMANCE V4 · SAFE A/B · SMART GUARD</span><h2>{pick("بهینه‌سازی هوشمند سرعت Outbound","Smart Outbound performance optimizer")}</h2><p>{pick("A/B واقعی دانلود و آپلود، BBR + FQ + PLPMTUD، امتیاز کاربردی و سوییچ محافظت‌شده با Confidence و Hysteresis.","Real download/upload A/B testing, BBR + FQ + PLPMTUD, use-case scoring and guarded switching with confidence and hysteresis.")}</p></div>
      <div className={styles.controls}><select value={nodeId} onChange={e=>setNodeId(Number(e.target.value))} disabled={Boolean(busy)}>{(inventory?.nodes||[]).map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select><button onClick={()=>void loadState(nodeId)} disabled={Boolean(busy)}>{pick("تازه‌سازی","Refresh")}</button></div>
    </div>

    {error?<div className={styles.error}>{error}</div>:null}
    {notice?<div className={styles.notice}>{notice}</div>:null}
    {tuningLocked?<div className={styles.notice}>{pick("Tuning v4 فعال است یا Backup معتبر دارد. برای Baseline مستقل و A/B جدید، ابتدا Rollback v4 را انجام بده.","V4 tuning is active or has a valid rollback state. Roll back v4 before starting a new independent A/B baseline.")}</div>:null}

    <div className={styles.grid}>
      <article className={styles.card}><small>{pick("مسیر فعلی","Current route")}</small><strong>{smartRoute?.current_tag||"—"}</strong><em>{pick("Score","Score")}: {num(smartRoute?.current?.score)} · Confidence {num(smartRoute?.current?.confidence_score)}%</em></article>
      <article className={styles.card}><small>{pick("کاندید هوشمند","Smart candidate")}</small><strong>{smartRoute?.candidate_tag||"—"}</strong><em>{reasonLabel(smartRoute?.reason||"hold",fa)}{smartRoute?.score_gain!=null?` · Δ ${num(smartRoute.score_gain)}`:""}</em></article>
      <article className={styles.card}><small>TCP</small><strong>{state?.tuning.tcp_congestion_control||"—"} · {state?.tuning.default_qdisc||"—"}</strong><em>PLPMTUD: {state?.tuning.tcp_mtu_probing||"—"} · {state?.tuning.v4_active?pick("V4 فعال","V4 active"):pick("V4 غیرفعال","V4 inactive")}</em></article>
    </div>

    <div className={styles.actions}>
      <button onClick={()=>void smart()} disabled={Boolean(busy)||!smartRoute?.should_switch}>{busy==="smart"?pick("اعمال...","Applying..."):pick("اعمال Smart Best","Apply Smart Best")}</button>
      <button onClick={()=>void tune()} disabled={Boolean(busy)||!tuneAvailable}>{busy==="tune"?pick("اعمال...","Applying..."):(tuningLocked?pick("Tuning v4 فعال است","V4 tuning active"):"BBR + FQ + PLPMTUD")}</button>
      <button className={styles.secondary} onClick={()=>void rollback()} disabled={Boolean(busy)||!tuningLocked}>{busy==="rollback"?pick("بازگردانی...","Rolling back..."):pick("Rollback تنظیمات v4","Rollback v4 tuning")}</button>
    </div>

    <div className={styles.abBox}>
      <div><span>A/B OPTIMIZER</span><h3>{pick("مقایسه قبل و بعد روی مسیر واقعی","Before/after comparison on the real route")}</h3><p>{tuningLocked?pick("برای جلوگیری از Baseline اشتباه، A/B تا زمان Rollback v4 قفل است.","A/B is locked until v4 is rolled back so the baseline stays clean."):pick("اگر Score/Throughput بهتر نشود یا Loaded Latency/Loss بدتر شود، Rollback خودکار انجام می‌شود.","If score/throughput does not improve safely or loaded latency/loss regresses, tuning is automatically rolled back.")}</p></div>
      <div className={styles.abControls}><select value={tag} onChange={e=>setTag(e.target.value)} disabled={Boolean(busy)||tuningLocked}>{(state?.benchmarkable_tags||[]).map(item=><option key={item} value={item}>{item}</option>)}</select><select value={profile} onChange={e=>setProfile(e.target.value as "quick"|"standard"|"full")} disabled={Boolean(busy)||tuningLocked}><option value="quick">Quick</option><option value="standard">Standard</option><option value="full">Full</option></select><button onClick={()=>void optimize()} disabled={Boolean(busy)||!tag||tuningLocked}>{busy==="ab"?pick("در حال تست...","Testing..."):pick("اجرای A/B + Auto Rollback","Run A/B + Auto Rollback")}</button></div>
    </div>

    {ab?<div className={styles.resultGrid}>
      <article><span>Baseline</span><b>{num(ab.baseline.effective_download_mbps,2)} ↓ / {num(ab.baseline.effective_upload_mbps,2)} ↑ Mbps</b><small>Score {num(ab.baseline.score)} · P95 {num(ab.baseline.latency_p95_ms)} ms · Loaded {num(ab.baseline.loaded_latency_p95_ms)} ms</small><small>{useCaseLine(ab.baseline,fa)}</small></article>
      <article><span>Tuned</span><b>{num(ab.tuned.effective_download_mbps,2)} ↓ / {num(ab.tuned.effective_upload_mbps,2)} ↑ Mbps</b><small>Score {num(ab.tuned.score)} · P95 {num(ab.tuned.latency_p95_ms)} ms · Loaded {num(ab.tuned.loaded_latency_p95_ms)} ms</small><small>{useCaseLine(ab.tuned,fa)}</small></article>
      <article><span>{pick("تصمیم","Decision")}</span><b>{ab.rolled_back?pick("Rollback شد","Rolled back"):pick("حفظ شد","Kept")}</b><small>ΔScore {num(ab.decision.score_gain)} · Down {num(ab.decision.download_gain_pct)}% · Up {num(ab.decision.upload_gain_pct)}%</small><small>{ab.decision.reason}</small></article>
    </div>:null}

    <div className={styles.foot}>{pick("Packet Loss این بخش Application Probe Loss است و به‌عنوان UDP/ICMP Loss واقعی نمایش داده نمی‌شود. HTTP/3 نیز از روی SOCKS ادعا نمی‌شود. TCP Fast Open / MPTCP / UDP Fragment نیز بدون A/B کنترل‌شده به‌صورت خودکار فعال نمی‌شوند.","Packet loss here is application probe loss, not claimed as true UDP/ICMP loss. HTTP/3 is not claimed through SOCKS. TCP Fast Open / MPTCP / UDP Fragment are not auto-enabled without a controlled A/B path.")}</div>
  </section>;
}
