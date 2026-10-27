"use client";

import {useEffect,useMemo,useState} from "react";

import {Badge,Card} from "./ui";
import {legacyControlApi} from "../lib/legacy-control-api";
import {tunnelTransportApi} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";


type LogicalTunnel={
  id:number;
  iran_node_id:number;
  exit_node_id:number;
  status?:string;
  active_transport?:string|null;
  preferred_transport?:string|null;
};

type Tp27Result=Record<string,unknown>;

const text=(value:unknown)=>value===null||value===undefined||value===""?"—":String(value);
const normalized=(value:unknown)=>String(value??"").trim().toLowerCase();
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const status=normalized(value);
  if(["online","healthy","ok","active","qualified","true"].includes(status))return "ok";
  if(["offline","failed","error","down","false"].includes(status))return "bad";
  return "warn";
};

function obj(value:unknown):Record<string,unknown>{
  return value&&typeof value==="object"&&!Array.isArray(value)?value as Record<string,unknown>:{};
}

export function Tp27RepairDockV271(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<LogicalTunnel[]>([]);
  const [selected,setSelected]=useState(0);
  const [result,setResult]=useState<Tp27Result|null>(null);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");
  const [open,setOpen]=useState(false);

  const loadTunnels=async()=>{
    const rows=await legacyControlApi.tunnels() as LogicalTunnel[];
    setTunnels(rows);
    setSelected(current=>current&&rows.some(row=>row.id===current)?current:(rows[0]?.id||0));
  };

  useEffect(()=>{
    void loadTunnels().catch(reason=>setError(reason instanceof Error?reason.message:String(reason)));
  },[]);

  const selectedTunnel=useMemo(()=>tunnels.find(row=>row.id===selected),[tunnels,selected]);
  const repairState=obj(result?.repair_state);
  const carrier=obj(result?.carrier);
  const iran=obj(carrier.iran);
  const exit=obj(carrier.exit);
  const selectedProfile=text(result?.selected_profile||result?.profile||repairState.selected_profile);
  const fouPort=text(result?.fou_port||repairState.fou_port);
  const lastRepair=text(repairState.last_repair_at);
  const lastResult=text(repairState.last_result);
  const healthy=result?Boolean(result.healthy??obj(result.after).healthy):null;

  const execute=async(kind:"diagnose"|"repair"|"rebuild")=>{
    if(!selected||busy)return;

    if(kind==="repair"&&!window.confirm(pick(
      "TP27 بررسی شود و فقط اگر Carrier واقعاً ناسالم است تعمیر شود؟ حالت Manual/Auto و مسیر Active تغییر نمی‌کند.",
      "Diagnose TP27 and repair only if the carrier is truly unhealthy? Manual/Auto mode and Active Transport are preserved."
    )))return;

    if(kind==="rebuild"&&!window.confirm(pick(
      "Carrier داخلی TP27 عمداً بازسازی شود؟ این عملیات ممکن است برای چند ثانیه اتصال همین تانل را قطع کند؛ مسیر منطقی و تنظیم Manual/Auto عوض نمی‌شود.",
      "Force rebuild the TP27 carrier? This can interrupt this tunnel for a few seconds; the logical transport and Manual/Auto policy are preserved."
    )))return;

    setBusy(kind);
    setError("");
    setSuccess("");

    try{
      const response=kind==="diagnose"
        ?await tunnelTransportApi.tp27Diagnose(selected)
        :kind==="repair"
          ?await tunnelTransportApi.tp27Repair(selected)
          :await tunnelTransportApi.tp27Rebuild(selected);

      setResult(response as Tp27Result);
      setSuccess(
        kind==="diagnose"
          ?pick("تشخیص TP27 دریافت شد.","TP27 diagnosis loaded.")
          :kind==="repair"
            ?pick("چرخه تعمیر TP27 کامل شد.","TP27 repair cycle completed.")
            :pick("Carrier TP27 بازسازی و ارزیابی شد.","TP27 carrier was rebuilt and validated.")
      );
      await loadTunnels();
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  return <div
    style={{
      position:"fixed",
      insetInlineStart:"18px",
      bottom:"18px",
      zIndex:1200,
      width:open?"min(430px, calc(100vw - 36px))":"auto",
      maxHeight:"calc(100vh - 36px)",
      overflow:"auto",
    }}
  >
    {!open?<button
      type="button"
      className="primary"
      onClick={()=>setOpen(true)}
      style={{boxShadow:"0 12px 34px rgba(0,0,0,.28)"}}
    >
      {pick("تعمیرات TP27","TP27 Repair")}
    </button>:<Card className="tp27-repair-dock">
      <div className="card-head">
        <div>
          <b>{pick("تعمیرات TP27 Fast","TP27 Fast Repair")}</b>
          <small>{pick("تشخیص و ترمیم Carrier بدون تغییر مسیر منطقی","Carrier diagnostics and repair without changing logical transport")}</small>
        </div>
        <button type="button" className="mini-btn" onClick={()=>setOpen(false)}>×</button>
      </div>

      <label className="field">
        <span>{pick("تانل","Tunnel")}</span>
        <select value={selected} disabled={Boolean(busy)} onChange={event=>{setSelected(Number(event.target.value));setResult(null);setError("");setSuccess("");}}>
          {tunnels.length===0&&<option value={0}>{pick("تانلی ثبت نشده","No tunnel registered")}</option>}
          {tunnels.map(row=><option key={row.id} value={row.id}>#{row.id} · Iran #{row.iran_node_id} → Exit #{row.exit_node_id}</option>)}
        </select>
      </label>

      {selectedTunnel&&<div className="runtime-info-list">
        <div><span>{pick("وضعیت","Status")}</span><Badge tone={tone(selectedTunnel.status)}>{text(selectedTunnel.status)}</Badge></div>
        <div><span>{pick("مسیر فعال","Active")}</span><b dir="ltr">{text(selectedTunnel.active_transport)}</b></div>
      </div>}

      <div className="action-grid">
        <button type="button" className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void execute("diagnose")}>{busy==="diagnose"?"…":pick("تشخیص TP27","Diagnose TP27")}</button>
        <button type="button" className="primary-soft" disabled={!selected||Boolean(busy)} onClick={()=>void execute("repair")}>{busy==="repair"?"…":pick("تعمیر TP27","Repair TP27")}</button>
        <button type="button" className="danger" disabled={!selected||Boolean(busy)} onClick={()=>void execute("rebuild")}>{busy==="rebuild"?"…":pick("بازسازی Carrier","Rebuild Carrier")}</button>
      </div>

      {error&&<div className="runtime-error compact">{error}</div>}
      {success&&<div className="runtime-success compact">{success}</div>}

      {result&&<div className="runtime-info-list">
        <div><span>{pick("Carrier","Carrier")}</span><b dir="ltr">{selectedProfile}{selectedProfile==="gre-fou"&&fouPort!=="—"?` · UDP/${fouPort}`:""}</b></div>
        <div><span>{pick("سلامت دوطرفه","Bidirectional health")}</span><Badge tone={healthy===true?"ok":healthy===false?"bad":"warn"}>{healthy===true?pick("سالم","Healthy"):healthy===false?pick("ناسالم","Unhealthy"):"—"}</Badge></div>
        <div><span>Iran → Exit</span><b>{iran.peer_reachable===true?"✓":iran.peer_reachable===false?"✕":"—"}</b></div>
        <div><span>Exit → Iran</span><b>{exit.peer_reachable===true?"✓":exit.peer_reachable===false?"✕":"—"}</b></div>
        <div><span>{pick("آخرین تعمیر","Last repair")}</span><b dir="ltr">{lastRepair}</b></div>
        <div><span>{pick("نتیجه آخر","Last result")}</span><b dir="ltr">{lastResult}</b></div>
      </div>}

      <p className="tp-section-note">
        {pick(
          "Repair پس از تشخیص، فقط Carrier خود TP27 را ترمیم می‌کند. Rebuild عمداً Carrier را از نو می‌سازد. هیچ‌کدام Manual/Auto، Active Transport، VXLAN یا پروتکل‌های VPN را تغییر نمی‌دهند.",
          "Repair mutates only the TP27 carrier after diagnosis. Rebuild intentionally recreates that carrier. Neither changes Manual/Auto, Active Transport, VXLAN or VPN protocols."
        )}
      </p>
    </Card>}
  </div>;
}
