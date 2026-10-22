"use client";

import {useEffect,useMemo,useState} from "react";

import {Badge,Card,Shell,Stat} from "./ui";
import {legacyControlApi} from "../lib/legacy-control-api";
import {tunnelTransportApi,type TunnelTransportRow,type TunnelTransportState} from "../lib/tunnel-transport-api";
import {modernTransportApi,type SmartTransportCandidate,type SmartTransportName,type SmartTransportState} from "../lib/modern-transport-api";
import {useI18n} from "../lib/i18n";

const labels:Record<string,string>={
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
const seconds=(value:unknown)=>{
  const n=Math.max(0,Number(value)||0);
  if(n>=60)return `${Math.floor(n/60)}m ${Math.round(n%60)}s`;
  return `${Math.round(n)}s`;
};

export function SmartTransportsRuntimeV25(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<Array<{id:number;iran_node_id:number;exit_node_id:number;status?:string;active_transport?:string|null;preferred_transport?:string|null}>>([]);
  const [selected,setSelected]=useState(0);
  const [smart,setSmart]=useState<SmartTransportState|null>(null);
  const [allState,setAllState]=useState<TunnelTransportState|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");

  const loadTunnels=async()=>{
    const rows=await legacyControlApi.tunnels();
    setTunnels(rows);
    setSelected(current=>current&&rows.some(row=>row.id===current)?current:(rows[0]?.id||0));
  };

  const loadState=async(id:number,silent=false)=>{
    if(!id){setSmart(null);setAllState(null);setLoading(false);return;}
    if(!silent)setLoading(true);
    if(!silent)setError("");
    try{
      const [modern,all]=await Promise.all([
        modernTransportApi.state(id),
        tunnelTransportApi.transports(id),
      ]);
      setSmart(modern);
      setAllState(all);
    }catch(reason){
      if(!silent)setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      if(!silent)setLoading(false);
    }
  };

  useEffect(()=>{void loadTunnels().catch(reason=>{setError(reason instanceof Error?reason.message:String(reason));setLoading(false);});},[]);
  useEffect(()=>{
    if(!selected)return;
    void loadState(selected);
    const timer=window.setInterval(()=>void loadState(selected,true),10000);
    return()=>window.clearInterval(timer);
  },[selected]);

  const candidates=useMemo(()=>Array.isArray(smart?.transports)?smart!.transports:[],[smart]);
  const allRows=useMemo(()=>Array.isArray(allState?.transports)?allState!.transports as TunnelTransportRow[]:[],[allState]);
  const qualified=candidates.filter(row=>row.qualified).length;
  const online=candidates.filter(row=>normalized(row.status)==="online").length;
  const measured=candidates.filter(row=>Number(row.benchmark?.weighted_mbps||0)>0).length;
  const selectedTunnel=tunnels.find(row=>row.id===selected);
  const currentMode=normalized(smart?.mode||allState?.mode||"manual");

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
    if(!window.confirm(pick(`نصب/بازسازی ${label(name)} روی همین تانل انجام شود؟`,`Install/rebuild ${label(name)} for this tunnel?`)))return;
    void run(`install-${name}`,pick(`${label(name)} نصب و بررسی شد.`,`${label(name)} install/qualification finished.`),()=>modernTransportApi.install(selected,name));
  };

  const remove=(row:SmartTransportCandidate)=>{
    const name=row.transport as SmartTransportName;
    if(!window.confirm(pick(`${label(name)} فقط از همین تانل حذف شود؟`,`Remove ${label(name)} only from this tunnel?`)))return;
    void run(`remove-${name}`,pick(`${label(name)} از همین تانل حذف شد.`,`${label(name)} was removed from this tunnel.`),()=>modernTransportApi.remove(selected,name));
  };

  const setAuto=()=>{
    if(!window.confirm(pick("Smart Auto اختیاری است و می‌تواند مسیر فعال را بعد از Health/Benchmark تغییر دهد. فعال شود؟","Smart Auto is optional and may switch the active path after health/benchmark checks. Enable it?")))return;
    void run("auto",pick("Smart Auto برای همین تانل فعال شد.","Smart Auto is enabled for this tunnel."),()=>modernTransportApi.setMode(selected,"auto"));
  };
  const setManual=(row:SmartTransportCandidate)=>void run(`manual-${row.transport}`,pick(`${label(row.transport)} به‌عنوان مسیر دستی Production اعمال شد.`,`${label(row.transport)} is now the manual production path.`),()=>modernTransportApi.setMode(selected,"manual",row.transport));

  return <Shell active="/admin/tunnel-transports">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div>
          <h1>{pick("مسیرهای تانل","Tunnel Transports")}</h1>
          <small>{pick("حالت دستی پیش‌فرض Production است؛ Smart Auto فقط با فعال‌سازی صریح مدیر وارد مدار می‌شود.","Manual mode is the production default; Smart Auto is opt-in and only activates explicitly.")}</small>
        </div>
        <button type="button" className="ghost" disabled={loading||Boolean(busy)} onClick={()=>{void loadTunnels();if(selected)void loadState(selected);}}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
      </div>

      {error&&<div className="runtime-error">{error}</div>}
      {success&&<div className="runtime-success">{success}</div>}

      <Card>
        <div className="card-head">
          <div><b>{pick("تانل منطقی","Logical tunnel")}</b><small>{pick("هر Candidate فقط روی Pair انتخاب‌شده نصب یا حذف می‌شود.","Every candidate is installed or removed only for the selected pair.")}</small></div>
          <Badge tone={tone(selectedTunnel?.status)}>{selectedTunnel?.status||"—"}</Badge>
        </div>
        <label className="field"><span>{pick("مسیر ایران → خارج","Iran → Exit pair")}</span><select value={selected} onChange={event=>setSelected(Number(event.target.value))}>
          {tunnels.length===0&&<option value={0}>{pick("تانلی ثبت نشده","No tunnel registered")}</option>}
          {tunnels.map(row=><option key={row.id} value={row.id}>#{row.id} · Iran #{row.iran_node_id} → Exit #{row.exit_node_id}</option>)}
        </select></label>
      </Card>

      <div className="stats dashboard-stats">
        <Stat label={pick("Candidateها","Candidates")} value={String(candidates.length)} icon="⇄"/>
        <Stat label={pick("آنلاین","Online")} value={String(online)} icon="✓"/>
        <Stat label={pick("تأییدشده","Qualified")} value={String(qualified)} icon="◉"/>
        <Stat label={pick("تست سرعت‌شده","Benchmarked")} value={String(measured)} icon="↯"/>
        <Stat label={pick("مسیر فعال","Active path")} value={label(smart?.active_transport||allState?.active_transport)} icon="→"/>
      </div>

      <Card>
        <div className="card-head">
          <div><b>{pick("حالت انتخاب مسیر","Path selection mode")}</b><small>{pick("Manual حالت پیش‌فرض Production است. Smart Auto فقط در حالت auto اجازه Promotion و جابه‌جایی مسیر دارد.","Manual is the production default. Smart Auto may promote or switch paths only while mode=auto.")}</small></div>
          <Badge tone={currentMode==="auto"?"warn":"ok"}>{currentMode||"manual"}</Badge>
        </div>
        <div className="runtime-info-list">
          <div><span>{pick("پیش‌فرض Production","Production default")}</span><b dir="ltr">manual</b></div>
          <div><span>{pick("فعال فعلی","Active")}</span><b dir="ltr">{label(smart?.active_transport||allState?.active_transport)}</b></div>
          <div><span>{pick("ترجیحی","Preferred")}</span><b dir="ltr">{label(smart?.preferred_transport||allState?.preferred_transport)}</b></div>
          <div><span>{pick("سیاست Auto","Auto policy")}</span><b dir="ltr">{smart?.promotion_policy||"health_then_speed"}</b></div>
        </div>
        <div className="action-row"><button type="button" className="ghost" disabled={!selected||Boolean(busy)||currentMode==="auto"} onClick={setAuto}>{busy==="auto"?"…":currentMode==="auto"?pick("Smart Auto فعال است","Smart Auto enabled"):pick("فعال‌سازی اختیاری Smart Auto","Enable optional Smart Auto")}</button></div>
      </Card>

      <div className="module-grid two">
        {candidates.map(row=>{
          const benchmark=row.benchmark||{};
          const installed=normalized(row.status)!=="not_installed";
          const quarantine=Number(row.quarantine_until_epoch||0)>Date.now()/1000;
          const progress=Math.min(100,Math.round((Number(row.stable_seconds||0)/Math.max(1,Number(row.required_stable_seconds||60)))*100));
          return <Card key={row.transport} className="transport-runtime-card">
            <div className="card-head">
              <div><b>{row.label||label(row.transport)}</b><small>{row.iran_profile||row.family||"Transport Candidate"}</small></div>
              <Badge tone={row.qualified?"ok":tone(row.status)}>{row.qualified?pick("تأییدشده","QUALIFIED"):String(row.status||"not_installed")}</Badge>
            </div>

            <div className="runtime-info-list">
              <div><span>Latency</span><b>{row.latency_ms==null?"—":`${row.latency_ms} ms`}</b></div>
              <div><span>{pick("پایداری","Stability")}</span><b dir="ltr">{seconds(row.stable_seconds)} / {seconds(row.required_stable_seconds||60)}</b></div>
              <div><span>{pick("دانلود","Download")}</span><b dir="ltr">{mbps(benchmark.download_mbps)}</b></div>
              <div><span>{pick("آپلود","Upload")}</span><b dir="ltr">{mbps(benchmark.upload_mbps)}</b></div>
              <div><span>{pick("امتیاز سرعت","Weighted speed")}</span><b dir="ltr">{mbps(benchmark.weighted_mbps)}</b></div>
              <div><span>{pick("قابل انتخاب","Selectable")}</span><b>{row.selectable?pick("بله","Yes"):pick("خیر","No")}</b></div>
            </div>

            <div className="runtime-progress" aria-label={`${progress}%`}><span style={{width:`${progress}%`}}/></div>
            {row.description&&<small>{row.description}</small>}
            {quarantine&&<div className="runtime-warning compact">{pick("این Candidate موقتاً قرنطینه است تا دوباره سلامت آن بررسی شود.","This candidate is temporarily quarantined until it is requalified.")}</div>}
            {row.auto_block_reason&&<div className="runtime-warning compact" dir="ltr">{String(row.auto_block_reason)}</div>}
            {row.last_error&&<div className="runtime-error compact" dir="ltr">{String(row.last_error)}</div>}

            <div className="action-row">
              <button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>install(row)}>{busy===`install-${row.transport}`?"…":installed?pick("بازسازی و تست","Rebuild & test"):pick("نصب و تست","Install & test")}</button>
              {row.selectable&&<button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>setManual(row)}>{busy===`manual-${row.transport}`?"…":pick("انتخاب دستی Production","Select production manual")}</button>}
              {installed&&<button type="button" className="danger" disabled={Boolean(busy)} onClick={()=>remove(row)}>{busy===`remove-${row.transport}`?"…":pick("حذف از این تانل","Remove")}</button>}
            </div>
          </Card>;
        })}
      </div>

      <Card>
        <div className="card-head"><div><b>{pick("همه مسیرهای ثبت‌شده","All registered paths")}</b><small>{pick("مسیرهای قدیمی برای مشاهده و Rollback باقی می‌مانند؛ جابه‌جایی خودکار فقط وقتی mode=auto باشد مجاز است.","Legacy paths remain visible for rollback; automatic switching is allowed only while mode=auto.")}</small></div></div>
        {loading?<div className="runtime-loading">{pick("در حال دریافت…","Loading…")}</div>:allRows.length?<div className="table"><table><thead><tr><th>{pick("مسیر","Transport")}</th><th>{pick("وضعیت","Status")}</th><th>Latency</th><th>{pick("فعال","Enabled")}</th><th>{pick("آخرین سلامت","Last healthy")}</th></tr></thead><tbody>
          {allRows.map((row,index)=><tr key={String(row.id||`${row.transport}-${index}`)}><td dir="ltr"><b>{label(row.transport)}</b></td><td><Badge tone={tone(row.status)}>{String(row.status||"—")}</Badge></td><td dir="ltr">{row.latency_ms==null?"—":`${row.latency_ms} ms`}</td><td>{row.enabled===false?pick("خیر","No"):pick("بله","Yes")}</td><td>{row.last_healthy_at?new Date(String(row.last_healthy_at)).toLocaleString("fa-IR"):"—"}</td></tr>)}
        </tbody></table></div>:<div className="runtime-empty">{pick("هنوز مسیری ثبت نشده است.","No path is registered yet.")}</div>}
      </Card>
    </div>
  </Shell>;
}
