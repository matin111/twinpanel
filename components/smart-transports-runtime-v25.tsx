"use client";

import {useEffect,useMemo,useState} from "react";

import {Badge,Card,Shell,Stat} from "./ui";
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
    if(!silent)setLoading(true);
    if(!silent)setError("");
    try{
      const [modern,all]=await Promise.all([
        modernTransportApi.state(id),
        tunnelTransportApi.transports(id),
      ]);
      setSmart(modern);
      setAllState(all);
      if(!silent){
        const spoof=(Array.isArray(modern.transports)?modern.transports:[]).find(row=>row.transport==="spoof_wg");
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
  const qualified=candidates.filter(row=>row.qualified).length;
  const online=candidates.filter(row=>normalized(row.status)==="online").length;
  const measured=candidates.filter(row=>Number(row.benchmark?.weighted_mbps||0)>0).length;
  const selectedTunnel=tunnels.find(row=>row.id===selected);
  const currentMode=normalized(smart?.mode||allState?.mode||"manual");
  const activeName=normalized(smart?.active_transport||allState?.active_transport);

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
    if(!window.confirm(pick(`نصب/بازسازی ${label(name)} روی همین تانل انجام شود؟`,`Install/rebuild ${label(name)} for this tunnel?`)))return;
    void run(`install-${name}`,pick(`${label(name)} نصب و بررسی شد.`,`${label(name)} install/qualification finished.`),()=>modernTransportApi.install(selected,name));
  };

  const remove=(row:SmartTransportCandidate)=>{
    const name=row.transport as SmartTransportName;
    if(normalized(name)===activeName){
      setError(pick("مسیر فعال Production از این صفحه حذف نمی‌شود.","The active production path cannot be removed here."));
      return;
    }
    if(!window.confirm(pick(`${label(name)} فقط از همین تانل حذف شود؟`,`Remove ${label(name)} only from this tunnel?`)))return;
    void run(`remove-${name}`,pick(`${label(name)} از همین تانل حذف شد.`,`${label(name)} was removed from this tunnel.`),()=>modernTransportApi.remove(selected,name));
  };

  const saveSpoof=()=>{
    const iran=iranSpoofIp.trim();
    const exit=exitSpoofIp.trim();
    if(!iran||!exit){
      setError(pick("هر دو IP اسپوف باید وارد شوند.","Both spoof IP addresses are required."));
      return;
    }
    void run("spoof-config",pick("تنظیمات Spoof Tunnel ذخیره شد.","Spoof Tunnel configuration saved."),()=>modernTransportApi.configureSpoof(selected,{iran_spoof_ip:iran,exit_spoof_ip:exit}));
  };

  const checkSpoofCompatibility=async()=>{
    if(!selected||busy)return;
    setBusy("spoof-compatibility");
    setError("");
    setSuccess("");
    try{
      const result=await modernTransportApi.checkSpoofCompatibility(selected);
      setSpoofCompatibility(result);
      setSuccess(
        result.compatible
          ?pick("هر دو سرور برای نصب Spoof Tunnel آماده‌اند. حالا IPهای Spoof را وارد و ذخیره کنید.","Both servers are ready for Spoof Tunnel. Enter and save the Spoof IPs next.")
          :pick("بررسی تمام شد؛ بعضی پیش‌نیازهای سرور نیاز به اصلاح دارند.","Check finished; some server prerequisites need attention.")
      );
    }catch(reason){
      setSpoofCompatibility(null);
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  const copySpoofGuideCommand=async()=>{
    if(!selected)return;
    const command=`cd /opt/twinpanel/current/backend
set -a
source /etc/twinpanel/backend.env
set +a
export PYTHONPATH="$PWD"

/opt/twinpanel/venv/bin/python3 - <<'PY'
import asyncio
import json

from app.database import SessionLocal
from app.routers.modern_transports import check_spoof_wg_compatibility

TUNNEL_ID = ${selected}
db = SessionLocal()

try:
    result = asyncio.run(
        check_spoof_wg_compatibility(
            tunnel_id=TUNNEL_ID,
            db=db,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
finally:
    db.close()
PY`;
    try{
      await navigator.clipboard.writeText(command);
      setError("");
      setSuccess(pick(`دستور عیب‌یابی Tunnel #${selected} کپی شد.`,`Tunnel #${selected} diagnostic command copied.`));
    }catch{
      setError(pick("کپی خودکار دستور در این مرورگر در دسترس نیست.","Automatic command copy is not available in this browser."));
    }
  };

  const setAuto=()=>{
    if(!window.confirm(pick("Smart Auto فقط بین مسیرهای تأییدشده TP27 Fast و Spoof Tunnel انتخاب می‌کند. فعال شود؟","Smart Auto will select only between qualified TP27 Fast and Spoof Tunnel paths. Enable it?")))return;
    void run("auto",pick("Smart Auto برای همین تانل فعال شد.","Smart Auto is enabled for this tunnel."),()=>modernTransportApi.setMode(selected,"auto"));
  };
  const setManual=(row:SmartTransportCandidate)=>void run(`manual-${row.transport}`,pick(`${label(row.transport)} به‌عنوان مسیر دستی Production اعمال شد.`,`${label(row.transport)} is now the manual production path.`),()=>modernTransportApi.setMode(selected,"manual",row.transport));

  const checkText=(value:unknown)=>value?pick("آماده","Ready"):pick("نیاز به بررسی","Check");

  return <Shell active="/admin/tunnel-transports">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div>
          <h1>{pick("مسیرهای تانل","Tunnel Transports")}</h1>
          <small>{pick("TP27 Fast مسیر Production فعلی است؛ Spoof Tunnel فقط بعد از تنظیم و تست کامل وارد مدار می‌شود.","TP27 Fast is the current production path; Spoof Tunnel enters service only after explicit configuration and full qualification.")}</small>
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
          <div><b>{pick("حالت انتخاب مسیر","Path selection mode")}</b><small>{pick("Manual حالت پیش‌فرض Production است. Smart Auto فقط بین Candidateهای تأییدشده فعلی انتخاب می‌کند.","Manual is the production default. Smart Auto selects only among the current qualified candidates.")}</small></div>
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
          const isSpoof=row.transport==="spoof_wg";
          const isActive=normalized(row.transport)===activeName;
          const spoofIpsEntered=Boolean(iranSpoofIp.trim()&&exitSpoofIp.trim());
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

            {isSpoof&&<div className="runtime-info-list">
              <details className="runtime-warning compact" open>
                <summary><b>{pick("راهنمای راه‌اندازی Spoof Tunnel","Spoof Tunnel setup guide")}</b></summary>
                <small>{pick("فقط این ۴ مرحله را به‌ترتیب انجام بده. تا مرحله قبلی کامل نشده، سراغ مرحله بعد نرو.","Follow these 4 steps in order. Finish each step before moving to the next one.")}</small>
                <div className="runtime-info-list">
                  <div><span>{pick("۱. بررسی سرورها","1. Check servers")}</span><b>{spoofCompatibility?(spoofCompatibility.compatible?pick("✅ آماده‌اند","✅ Ready"):pick("❌ نیاز به اصلاح","❌ Needs fix")):pick("⬅️ دکمه بررسی را بزن","⬅️ Run the check")}</b></div>
                  <div><span>{pick("۲. وارد کردن IPهای Spoof","2. Enter Spoof IPs")}</span><b>{spoofIpsEntered?pick("✅ وارد شده","✅ Entered"):pick("⬅️ هر دو IP را وارد کن","⬅️ Enter both IPs")}</b></div>
                  <div><span>{pick("۳. ذخیره IPها","3. Save IPs")}</span><b>{row.configured?pick("✅ ذخیره شده","✅ Saved"):spoofIpsEntered?pick("⬅️ دکمه ذخیره را بزن","⬅️ Save them"):pick("— بعد از مرحله ۲","— After step 2")}</b></div>
                  <div><span>{pick("۴. نصب و تست تانل","4. Install & test tunnel")}</span><b>{row.qualified?pick("✅ نصب و تأیید شده","✅ Installed & qualified"):installed?pick("⚠️ نصب شده؛ هنوز تأیید نشده","⚠️ Installed, not qualified yet"):row.configured?pick("⬅️ دکمه نصب و تست را بزن","⬅️ Install & test"):pick("— بعد از مرحله ۳","— After step 3")}</b></div>
                </div>
                <div className="runtime-warning compact">
                  {pick(
                    "نکته: مرحله ۱ فقط آماده‌بودن دو سرور را بررسی می‌کند. IPهای Spoof که در مرحله ۲ وارد می‌کنی باید از قبل برای شبکه/دیتاسنتر خودت معتبر و مجاز باشند.",
                    "Note: step 1 only checks whether both servers are ready. The Spoof IPs entered in step 2 must already be valid and authorized for your network/provider."
                  )}
                </div>
              </details>

              <div className="card-head">
                <div><b>{pick("مرحله ۱ — بررسی سرورها","Step 1 — Check servers")}</b><small>{pick("این تست چیزی را روی مسیر فعال تغییر نمی‌دهد.","This check does not change the active path.")}</small></div>
                {spoofCompatibility&&<Badge tone={spoofCompatibility.compatible?"ok":"bad"}>{spoofCompatibility.compatible?pick("آماده","READY"):pick("نیاز به اصلاح","NEEDS FIX")}</Badge>}
              </div>
              <div className="action-row">
                <button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void checkSpoofCompatibility()}>
                  {busy==="spoof-compatibility"?"…":pick("مرحله ۱: بررسی سرورها","Step 1: Check servers")}
                </button>
              </div>

              {spoofCompatibility&&<>
                <div><span>{pick("نتیجه بررسی سرورها","Server check result")}</span><b>{spoofCompatibility.compatible?pick("✅ هر دو آماده‌اند","✅ Both ready"):pick("❌ نیاز به اصلاح","❌ Needs fix")}</b></div>
                <details className="runtime-warning compact">
                  <summary><b>{pick("جزئیات فنی تست","Technical test details")}</b></summary>
                  <div className="runtime-info-list">
                    <div><span>{pick("Core بسته‌بندی‌شده","Bundled core")}</span><b>{spoofCompatibility.core?.ok?pick("سالم","OK"):pick("خطا","Error")}</b></div>
                    <div><span>{pick("Iran · Raw Socket","Iran · Raw Socket")}</span><b>{checkText(spoofCompatibility.iran.raw_socket)}</b></div>
                    <div><span>{pick("Iran · WireGuard","Iran · WireGuard")}</span><b>{checkText(Boolean(spoofCompatibility.iran.wg_tools&&spoofCompatibility.iran.wireguard_kernel&&spoofCompatibility.iran.tun_device))}</b></div>
                    <div><span>{pick("Iran · Route به خارج","Iran · Route to Exit")}</span><b>{checkText(spoofCompatibility.iran.route_to_peer)}</b></div>
                    <div><span>{pick("Exit · Raw Socket","Exit · Raw Socket")}</span><b>{checkText(spoofCompatibility.exit.raw_socket)}</b></div>
                    <div><span>{pick("Exit · WireGuard","Exit · WireGuard")}</span><b>{checkText(Boolean(spoofCompatibility.exit.wg_tools&&spoofCompatibility.exit.wireguard_kernel&&spoofCompatibility.exit.tun_device))}</b></div>
                    <div><span>{pick("Exit · Route به ایران","Exit · Route to Iran")}</span><b>{checkText(spoofCompatibility.exit.route_to_peer)}</b></div>
                    <div><span>{pick("Ping ایران → خارج","Ping Iran → Exit")}</span><b>{spoofCompatibility.iran.ping_peer?pick("پاس","Pass"):pick("پاس نشد (غیر بحرانی)","No reply (advisory)")}</b></div>
                    <div><span>{pick("Ping خارج → ایران","Ping Exit → Iran")}</span><b>{spoofCompatibility.exit.ping_peer?pick("پاس","Pass"):pick("پاس نشد (غیر بحرانی)","No reply (advisory)")}</b></div>
                  </div>
                  {spoofCompatibility.blockers.length>0&&<div className="runtime-error compact" dir="ltr">{spoofCompatibility.blockers.join(" · ")}</div>}
                </details>
                <div className="runtime-warning compact">
                  {pick(
                    "این نتیجه فقط می‌گوید دو سرور برای اجرای Spoof Tunnel آماده‌اند؛ معتبر بودن IPهای Spoof را تأیید نمی‌کند.",
                    "This result only confirms that both servers are ready for Spoof Tunnel; it does not validate the Spoof IPs themselves."
                  )}
                </div>
              </>}

              <label className="field"><span>{pick("مرحله ۲ — IP Spoof سمت ایران","Step 2 — Iran Spoof IP")}</span><input dir="ltr" value={iranSpoofIp} onChange={event=>setIranSpoofIp(event.target.value)} placeholder="IPv4" disabled={Boolean(busy)||normalized(row.status)==="online"}/></label>
              <label className="field"><span>{pick("مرحله ۲ — IP Spoof سمت خارج","Step 2 — Exit Spoof IP")}</span><input dir="ltr" value={exitSpoofIp} onChange={event=>setExitSpoofIp(event.target.value)} placeholder="IPv4" disabled={Boolean(busy)||normalized(row.status)==="online"}/></label>
              <div className="action-row"><button type="button" className="ghost" disabled={Boolean(busy)||normalized(row.status)==="online"} onClick={saveSpoof}>{busy==="spoof-config"?"…":pick("مرحله ۳: ذخیره IPها","Step 3: Save IPs")}</button></div>

              <details className="runtime-warning compact">
                <summary><b>{pick("عیب‌یابی دستی (اختیاری)","Manual diagnostics (optional)")}</b></summary>
                <small>{pick("فقط اگر دکمه «بررسی سرورها» خطا داد یا برای پشتیبانی خروجی کامل لازم داشتی، این دستور را روی سرور TwinPanel اجرا کن.","Use this only if the server check fails or support needs the full diagnostic output on the TwinPanel server.")}</small>
                <div className="action-row">
                  <button type="button" className="ghost" disabled={!selected} onClick={()=>void copySpoofGuideCommand()}>{pick(`کپی دستور عیب‌یابی Tunnel #${selected}`,`Copy Tunnel #${selected} diagnostic command`)}</button>
                </div>
              </details>

              <div><span>{pick("هسته","Core")}</span><b dir="ltr">{row.upstream_version||"v3.1.0-beta.0"}</b></div>
              <div><span>XDP</span><b dir="ltr">OFF · raw socket</b></div>
              {!row.configured&&<div className="runtime-warning compact">{pick("برای رفتن به مرحله ۴، هر دو IP را وارد کن و «مرحله ۳: ذخیره IPها» را بزن.","To continue to step 4, enter both IPs and click 'Step 3: Save IPs'.")}</div>}
            </div>}

            <div className="runtime-progress" aria-label={`${progress}%`}><span style={{width:`${progress}%`}}/></div>
            {row.description&&<small>{row.description}</small>}
            {quarantine&&<div className="runtime-warning compact">{pick("این Candidate موقتاً قرنطینه است تا دوباره سلامت آن بررسی شود.","This candidate is temporarily quarantined until it is requalified.")}</div>}
            {row.auto_block_reason&&<div className="runtime-warning compact" dir="ltr">{String(row.auto_block_reason)}</div>}
            {row.last_error&&<div className="runtime-error compact" dir="ltr">{String(row.last_error)}</div>}

            <div className="action-row">
              <button type="button" className="primary-soft" disabled={Boolean(busy)||(isSpoof&&!row.configured)} onClick={()=>install(row)}>{busy===`install-${row.transport}`?"…":isSpoof?(installed?pick("بازسازی و تست Spoof","Rebuild & test Spoof"):pick("مرحله ۴: نصب و تست Spoof","Step 4: Install & test Spoof")):installed?pick("بازسازی و تست","Rebuild & test"):pick("نصب و تست","Install & test")}</button>
              {row.selectable&&<button type="button" className="ghost" disabled={Boolean(busy)||isActive} onClick={()=>setManual(row)}>{busy===`manual-${row.transport}`?"…":isActive?pick("مسیر فعال","Active path"):pick("انتخاب دستی Production","Select production manual")}</button>}
              {installed&&<button type="button" className="danger" disabled={Boolean(busy)||isActive} onClick={()=>remove(row)}>{busy===`remove-${row.transport}`?"…":isActive?pick("مسیر فعال","Active path"):pick("حذف از این تانل","Remove")}</button>}
            </div>
          </Card>;
        })}
      </div>

      <Card>
        <div className="card-head"><div><b>{pick("مسیرهای باقی‌مانده","Remaining registered paths")}</b><small>{pick("مسیرهای قدیمی فقط تا پایان cleanup رسمی نمایش داده می‌شوند؛ مسیر فعال هرگز توسط cleanup حذف نمی‌شود.","Retired paths are shown only until official cleanup finishes; the active production path is never removed by cleanup.")}</small></div></div>
        {loading?<div className="runtime-loading">{pick("در حال دریافت…","Loading…")}</div>:visibleAllRows.length?<div className="table"><table><thead><tr><th>{pick("مسیر","Transport")}</th><th>{pick("وضعیت","Status")}</th><th>Latency</th><th>{pick("فعال","Enabled")}</th><th>{pick("آخرین سلامت","Last healthy")}</th></tr></thead><tbody>
          {visibleAllRows.map((row,index)=><tr key={String(row.id||`${row.transport}-${index}`)}><td dir="ltr"><b>{label(row.transport)}</b></td><td><Badge tone={tone(row.status)}>{String(row.status||"—")}</Badge></td><td dir="ltr">{row.latency_ms==null?"—":`${row.latency_ms} ms`}</td><td>{row.enabled===false?pick("خیر","No"):pick("بله","Yes")}</td><td>{row.last_healthy_at?new Date(String(row.last_healthy_at)).toLocaleString("fa-IR"):"—"}</td></tr>)}
        </tbody></table></div>:<div className="runtime-empty">{pick("فقط مسیرهای فعال Production باقی مانده‌اند.","Only production-active paths remain.")}</div>}
      </Card>
    </div>
  </Shell>;
}