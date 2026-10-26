"use client";

import {useEffect,useMemo,useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {PageHead,Shell} from "./ui";
import styles from "./outbound-performance-lab.module.css";


type OutboundRow={type:string;tag:string;server?:string;server_port?:number;managed?:boolean;imported?:boolean};
type OutboundNode={id:number;name:string;public_ip:string;service_active:boolean;outbounds:OutboundRow[];default_tag?:string|null};
type Inventory={ok:boolean;nodes:OutboundNode[]};
type BenchmarkProfile="quick"|"standard"|"full";
type ScoreProfile="balanced"|"latency"|"download"|"upload"|"stability";
type BenchmarkResult={
  ok:boolean;
  tag:string;
  profile:BenchmarkProfile;
  tested_at?:string|null;
  tcp_ok?:boolean|null;
  tcp_ms?:number|null;
  e2e_ok?:boolean;
  exit_ip?:string|null;
  http_code?:number|null;
  latency_ms?:number|null;
  jitter_ms?:number|null;
  probe_loss_pct?:number|null;
  download_mbps?:number|null;
  upload_mbps?:number|null;
  download_bytes?:number;
  upload_bytes?:number;
  throughput_ok?:boolean;
  score?:number;
  quality?:string;
  score_profile?:ScoreProfile;
  error?:string|null;
};
type PerformanceState={
  ok:boolean;
  node_id:number;
  node_name:string;
  benchmarkable_tags:string[];
  profiles:BenchmarkProfile[];
  score_profiles:ScoreProfile[];
  latest:Record<string,BenchmarkResult>;
  history:Record<string,BenchmarkResult[]>;
  ranking:BenchmarkResult[];
  updated_at?:string|null;
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
    if(payload&&typeof payload==="object"&&"detail" in payload){
      const detail=(payload as {detail?:unknown}).detail;
      if(typeof detail==="string")throw new Error(detail);
      if(detail&&typeof detail==="object"){
        const item=detail as {message?:unknown;error?:unknown;reason?:unknown};
        const message=[item.message,item.error,item.reason].filter(Boolean).map(String).join(" · ");
        if(message)throw new Error(message);
      }
    }
    throw new Error(`API ${response.status}`);
  }
  return payload as T;
}

function fmt(value:number|null|undefined,digits=1){return value==null?"—":value.toFixed(digits)}
function mb(value:number|undefined){return value?`${(value/1_000_000).toFixed(1)} MB`:"—"}
function qualityClass(value:string|undefined){return value==="excellent"||value==="good"?styles.good:value==="fair"?styles.fair:styles.bad}
function endpoint(row:OutboundRow|undefined){if(!row)return "—";if(row.type==="direct")return "Internet / WAN";return [row.server,row.server_port].filter(Boolean).join(":")||row.type.toUpperCase()}

export function OutboundPerformanceLab(){
  const {pick,lang}=useI18n();
  const fa=lang==="fa";
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [state,setState]=useState<PerformanceState|null>(null);
  const [nodeId,setNodeId]=useState(0);
  const [profile,setProfile]=useState<BenchmarkProfile>("standard");
  const [scoreProfile,setScoreProfile]=useState<ScoreProfile>("balanced");
  const [tests,setTests]=useState<Record<string,BenchmarkResult>>({});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [progress,setProgress]=useState("");
  const [notice,setNotice]=useState("");
  const [error,setError]=useState("");

  const node=useMemo(()=>inventory?.nodes.find(item=>item.id===nodeId)??null,[inventory,nodeId]);
  const rows=useMemo(()=>new Map((node?.outbounds||[]).map(item=>[item.tag,item])),[node]);
  const current=useMemo(()=>({...state?.latest,...tests}),[state,tests]);
  const ranking=useMemo(()=>Object.values(current).sort((a,b)=>{
    if(Boolean(a.ok)!==Boolean(b.ok))return a.ok?-1:1;
    return Number(b.score||0)-Number(a.score||0);
  }),[current]);
  const best=ranking.find(item=>item.ok&&Number(item.score||0)>0)||null;
  const passed=ranking.filter(item=>item.ok).length;
  const avgDown=ranking.filter(item=>item.download_mbps!=null).reduce((sum,item)=>sum+Number(item.download_mbps||0),0)/(ranking.filter(item=>item.download_mbps!=null).length||1);
  const avgUp=ranking.filter(item=>item.upload_mbps!=null).reduce((sum,item)=>sum+Number(item.upload_mbps||0),0)/(ranking.filter(item=>item.upload_mbps!=null).length||1);

  const loadInventory=async()=>{
    const data=await api<Inventory>("/v1/settings/vpn/outbounds");
    setInventory(data);
    setNodeId(currentId=>data.nodes.some(item=>item.id===currentId)?currentId:(data.nodes[0]?.id||0));
  };

  const loadState=async(id:number)=>{
    if(!id)return;
    const data=await api<PerformanceState>(`/v1/settings/vpn/outbound-performance/${id}`);
    setState(data);
    setTests({});
  };

  useEffect(()=>{
    void (async()=>{
      setLoading(true);setError("");
      try{await loadInventory();}catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
      finally{setLoading(false);}
    })();
  },[]);

  useEffect(()=>{
    if(!nodeId)return;
    void (async()=>{
      setLoading(true);setError("");setNotice("");
      try{await loadState(nodeId);}catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
      finally{setLoading(false);}
    })();
  },[nodeId]);

  const perform=async(tag:string)=>{
    if(!nodeId)throw new Error("NODE_REQUIRED");
    const result=await api<BenchmarkResult>(`/v1/settings/vpn/outbound-performance/${nodeId}/${encodeURIComponent(tag)}/test`,{
      method:"POST",
      body:JSON.stringify({profile,score_profile:scoreProfile}),
    });
    setTests(previous=>({...previous,[tag]:result}));
    return result;
  };

  const testOne=async(tag:string)=>{
    setBusy(`test:${tag}`);setError("");setNotice("");setProgress("");
    try{
      const result=await perform(tag);
      setNotice(result.ok
        ?pick(`${tag}: دانلود ${fmt(result.download_mbps,2)} Mbps · آپلود ${fmt(result.upload_mbps,2)} Mbps · امتیاز ${fmt(result.score,0)}`,`${tag}: ${fmt(result.download_mbps,2)} Mbps down · ${fmt(result.upload_mbps,2)} Mbps up · score ${fmt(result.score,0)}`)
        :pick(`Benchmark ${tag} کامل نشد.`,`Benchmark failed for ${tag}.`));
      await loadState(nodeId);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const testAll=async()=>{
    const tags=state?.benchmarkable_tags||[];
    if(!tags.length)return;
    setBusy("all");setError("");setNotice("");
    try{
      for(let index=0;index<tags.length;index++){
        const tag=tags[index];
        setProgress(pick(`در حال تست ${index+1} از ${tags.length}: ${tag}`,`Testing ${index+1} of ${tags.length}: ${tag}`));
        try{await perform(tag);}catch(exc){
          const message=exc instanceof Error?exc.message:String(exc);
          setTests(previous=>({...previous,[tag]:{ok:false,tag,profile,error:message,score:0,quality:"failed",score_profile:scoreProfile}}));
        }
      }
      await loadState(nodeId);
      setNotice(pick("تست ترتیبی همه مسیرها کامل شد؛ Ranking با آخرین نتایج به‌روزرسانی شد.","Sequential benchmark finished; ranking was refreshed from the latest results."));
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");setProgress("");}
  };

  const selectBest=async()=>{
    if(!nodeId||!best)return;
    setBusy("best");setError("");setNotice("");
    try{
      await api<unknown>(`/v1/settings/vpn/outbounds/${nodeId}/default`,{method:"POST",body:JSON.stringify({tag:best.tag})});
      await loadInventory();
      setNotice(pick(`بهترین مسیر تست‌شده «${best.tag}» با امتیاز ${fmt(best.score,0)} به‌عنوان Default اعمال شد.`,`Best tested route “${best.tag}” (score ${fmt(best.score,0)}) is now the default.`));
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const profileCost=profile==="quick"?"≈ 1.5 MB":profile==="standard"?"≈ 22 MB":"≈ 51 MB";
  const profileText=profile==="quick"
    ?pick("بررسی سریع برای Health و تخمین اولیه سرعت","Fast health check with a lightweight throughput estimate")
    :profile==="standard"
      ?pick("تعادل مناسب بین دقت و مصرف ترافیک","Balanced accuracy and traffic usage")
      :pick("نمونه‌های بزرگ‌تر برای لینک‌های پرسرعت","Larger ramp samples for high-throughput links");

  return <Shell active="/admin/outbound-performance">
    <div className={styles.page} dir={fa?"rtl":"ltr"}>
      <PageHead title={pick("آزمایشگاه سرعت Outbound","Outbound Performance Lab")}/>
      <section className={styles.hero}>
        <div>
          <div className={styles.kicker}>TWINPANEL · ROUTE-BOUND BENCHMARK</div>
          <h1>{pick("سرعت واقعی هر مسیر را جداگانه اندازه بگیرید","Measure every egress route independently")}</h1>
          <p>{pick(
            "هر تست داخل یک Sing-box موقت با Route Final همان Outbound اجرا می‌شود؛ مسیر Production تغییر نمی‌کند. Download/Upload، Latency، HTTP Jitter، Probe Loss، Exit IP و Score در یک Ranking واحد ثبت می‌شوند.",
            "Each test runs in an isolated temporary Sing-box with that outbound as its final route. Production routing is untouched while download/upload, latency, HTTP jitter, probe loss, exit IP and score are recorded into one ranking.",
          )}</p>
          <a className={styles.back} href="/admin/outbounds">← {pick("بازگشت به Outbound Policy","Back to Outbound Policy")}</a>
        </div>
        <div className={styles.heroActions}>
          <label><span>{pick("نود","Node")}</span><select className={styles.select} value={nodeId} onChange={event=>setNodeId(Number(event.target.value))} disabled={Boolean(busy)||loading}>{(inventory?.nodes||[]).map(item=><option value={item.id} key={item.id}>{item.name} · {item.public_ip}</option>)}</select></label>
          <button className={styles.secondary} onClick={()=>void loadState(nodeId)} disabled={Boolean(busy)||loading}>{loading?pick("در حال دریافت...","Loading..."):pick("به‌روزرسانی نتایج","Refresh results")}</button>
        </div>
      </section>

      {error?<div className={styles.error}>{error}</div>:null}
      {notice?<div className={styles.notice}>{notice}</div>:null}

      <section className={styles.stats}>
        <article className={styles.stat}><span>{pick("مسیرهای قابل Benchmark","Benchmarkable routes")}</span><strong>{state?.benchmarkable_tags.length||0}</strong><small>{pick("Direct + Outboundهای مدیریت‌شده","Direct + managed imported outbounds")}</small></article>
        <article className={styles.stat}><span>{pick("تست سالم","Healthy tests")}</span><strong>{passed}</strong><small>{pick("آخرین نتیجه هر مسیر","Latest result per route")}</small></article>
        <article className={styles.stat}><span>{pick("میانگین Download","Average download")}</span><strong>{ranking.length?`${avgDown.toFixed(1)} Mbps`:"—"}</strong><small>{pick("فقط نتایج دارای Throughput","Measured throughput only")}</small></article>
        <article className={styles.stat}><span>{pick("میانگین Upload","Average upload")}</span><strong>{ranking.length?`${avgUp.toFixed(1)} Mbps`:"—"}</strong><small>{pick("تست Route-bound","Route-bound measurement")}</small></article>
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHead}>
          <div><div className={styles.kicker}>PERFORMANCE MATRIX</div><h2>{pick("Benchmark و Ranking مسیرها","Benchmark & route ranking")}</h2><p>{profileText} · {pick("مصرف تقریبی هر مسیر","Approx. traffic per route")}: {profileCost}</p></div>
          <div className={styles.toolbar}>
            <label><span>{pick("پروفایل تست","Test profile")}</span><select className={styles.select} value={profile} onChange={event=>setProfile(event.target.value as BenchmarkProfile)} disabled={Boolean(busy)}><option value="quick">Quick</option><option value="standard">Standard</option><option value="full">Full</option></select></label>
            <label><span>{pick("اولویت Ranking","Ranking priority")}</span><select className={styles.select} value={scoreProfile} onChange={event=>setScoreProfile(event.target.value as ScoreProfile)} disabled={Boolean(busy)}><option value="balanced">{pick("متعادل","Balanced")}</option><option value="latency">Latency</option><option value="download">Download</option><option value="upload">Upload</option><option value="stability">{pick("پایداری","Stability")}</option></select></label>
            <button className={styles.button} onClick={()=>void testAll()} disabled={Boolean(busy)||!(state?.benchmarkable_tags.length)}>{busy==="all"?pick("در حال تست...","Testing..."):pick("تست همه مسیرها","Test all routes")}</button>
            <button className={styles.secondary} onClick={()=>void selectBest()} disabled={Boolean(busy)||!best}>{busy==="best"?pick("اعمال...","Applying..."):pick("اعمال بهترین مسیر","Use best route")}</button>
          </div>
        </div>
        {progress?<div className={styles.progress}>{progress}</div>:null}
        {!ranking.length?<div className={styles.empty}>{pick("هنوز Benchmark ثبت نشده؛ Quick یا Standard را انتخاب و «تست همه مسیرها» را اجرا کنید.","No benchmark results yet. Choose Quick or Standard and run “Test all routes”.")}</div>:null}
        <div className={styles.ranking}>{ranking.map((result,index)=>{
          const row=rows.get(result.tag);
          const history=state?.history?.[result.tag]||[];
          const score=Math.max(0,Math.min(100,Number(result.score||0)));
          const defaultRoute=node?.default_tag||"direct";
          return <article className={styles.routeCard} key={result.tag}>
            <div className={styles.routeTop}>
              <div className={styles.routeTitle}><b>{index+1}. {result.tag}</b><small>{endpoint(row)}{defaultRoute===result.tag?` · ${pick("پیش‌فرض فعلی","current default")}`:""}</small><span className={`${styles.quality} ${qualityClass(result.quality)}`}>{result.quality||"untested"}</span></div>
              <div className={styles.score}><strong>{result.score!=null?Math.round(result.score):"—"}</strong><span>SCORE</span></div>
            </div>
            <div className={styles.scoreBar}><i style={{width:`${score}%`}}/></div>
            <div className={styles.metrics}>
              <div className={styles.metric}><span>Download</span><b>{result.download_mbps!=null?`${fmt(result.download_mbps,2)} Mbps`:"—"}</b></div>
              <div className={styles.metric}><span>Upload</span><b>{result.upload_mbps!=null?`${fmt(result.upload_mbps,2)} Mbps`:"—"}</b></div>
              <div className={styles.metric}><span>Latency</span><b>{result.latency_ms!=null?`${fmt(result.latency_ms)} ms`:"—"}</b></div>
              <div className={styles.metric}><span>HTTP Jitter</span><b>{result.jitter_ms!=null?`${fmt(result.jitter_ms)} ms`:"—"}</b></div>
              <div className={styles.metric}><span>{pick("Probe Loss","Probe Loss")}</span><b>{result.probe_loss_pct!=null?`${fmt(result.probe_loss_pct)}%`:"—"}</b></div>
              <div className={styles.metric}><span>Exit IP</span><b className={styles.mono}>{result.exit_ip||"—"}</b></div>
              <div className={styles.metric}><span>{pick("داده دانلود","Download data")}</span><b>{mb(result.download_bytes)}</b></div>
              <div className={styles.metric}><span>{pick("داده آپلود","Upload data")}</span><b>{mb(result.upload_bytes)}</b></div>
              <div className={styles.metric}><span>TCP</span><b>{result.tcp_ok===true?`PASS · ${fmt(result.tcp_ms)} ms`:result.tag==="direct"?"N/A":"FAIL"}</b></div>
            </div>
            <div className={styles.history}><span>{pick("تاریخچه","History")}</span>{history.slice(-12).map((item,hIndex)=><i key={`${result.tag}-${hIndex}`} title={`${item.score??0}`} style={{height:`${Math.max(5,Math.min(22,Number(item.score||0)/5))}px`}}/>)}<span>{history.length}</span></div>
            {result.error?<div className={styles.error}>{result.error}</div>:null}
            <div className={styles.cardActions}><button onClick={()=>void testOne(result.tag)} disabled={Boolean(busy)}>{busy===`test:${result.tag}`?pick("در حال تست...","Testing..."):pick("تست مجدد","Retest")}</button>{defaultRoute!==result.tag&&result.ok?<button onClick={async()=>{setBusy(`default:${result.tag}`);setError("");try{await api(`/v1/settings/vpn/outbounds/${nodeId}/default`,{method:"POST",body:JSON.stringify({tag:result.tag})});await loadInventory();setNotice(pick(`مسیر ${result.tag} به‌عنوان Default اعمال شد.`,`${result.tag} is now the default route.`));}catch(exc){setError(exc instanceof Error?exc.message:String(exc));}finally{setBusy("");}}} disabled={Boolean(busy)}>{pick("Default کردن","Set default")}</button>:null}</div>
          </article>;
        })}</div>
        <div className={styles.explain}>
          <article><b>{pick("Throughput واقعی","Real throughput")}</b><p>{pick("Download/Upload از داخل همان Outbound با endpoint رسمی Cloudflare اندازه‌گیری می‌شود و از Direct سیستم میان‌بر نمی‌زند.","Download/upload are measured through the selected outbound against Cloudflare's speed endpoints, never bypassing through the host's direct WAN.")}</p></article>
          <article><b>{pick("Jitter و Loss دقیقاً چیست؟","What do jitter and loss mean?")}</b><p>{pick("Jitter از تغییر زمان پاسخ HTTP بین نمونه‌ها محاسبه می‌شود. Loss درصد Probeهای HTTP ناموفق است و عمداً Packet Loss نامیده نمی‌شود.","Jitter is derived from variation between HTTP response samples. Loss is failed HTTP probe percentage and is intentionally not labeled packet loss.")}</p></article>
          <article><b>{pick("Smart Select بدون Flapping","Smart select without flapping")}</b><p>{pick("Ranking هیچ مسیری را خودکار عوض نمی‌کند. «اعمال بهترین مسیر» فقط بعد از تست و اقدام ادمین Default را تغییر می‌دهد؛ Policyهای صریح هر پروتکل دست‌نخورده می‌مانند.","Ranking never switches routes by itself. “Use best route” changes only the node default after an admin action; explicit per-protocol policies remain untouched.")}</p></article>
        </div>
      </section>
    </div>
  </Shell>;
}
