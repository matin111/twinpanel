"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {adminApi,RuntimeRow} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const parsed=Number(value??0);return Number.isFinite(parsed)?parsed:0;};
const stringList=(value:unknown)=>Array.isArray(value)?value.map(item=>String(item)).filter(Boolean):[];
const numberList=(value:unknown)=>Array.isArray(value)?value.map(item=>Number(item)).filter(item=>Number.isFinite(item)&&item>0):[];

const PROTOCOLS=[
  ["cisco","Cisco / OpenConnect"],["openvpn","OpenVPN"],["wireguard","WireGuard"],["l2tp","L2TP / IPsec"],["v2ray","V2Ray / Xray"],
  ["hysteria2","Hysteria2"],["tuic","TUIC"],["anytls","AnyTLS"],["naive","NaiveProxy"],["shadowtls","ShadowTLS"],
  ["snell","Snell"],["mieru","Mieru"],["trusttunnel","TrustTunnel"],["amneziawg","AmneziaWG"],["sudoku","Sudoku"],
] as const;
const ALL_PROTOCOLS=PROTOCOLS.map(([key])=>key);

type PlanDraft={
  name:string;description:string;duration_days:number;traffic_gb:number;device_limit:number;price_toman:number;is_active:boolean;
  protocols:string[];node_ids:number[];trial_enabled:boolean;trial_duration_days:number;trial_traffic_mb:number;
};

const EMPTY_DRAFT:PlanDraft={
  name:"",description:"",duration_days:30,traffic_gb:50,device_limit:1,price_toman:0,is_active:true,
  protocols:[...ALL_PROTOCOLS],node_ids:[],trial_enabled:false,trial_duration_days:1,trial_traffic_mb:500,
};

function Notice({error,ok}:{error:string;ok:string}){
  return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;
}
function Check({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}){
  return <label className="toggle module-toggle compact-toggle"><span>{label}</span><input type="checkbox" checked={checked} onChange={event=>onChange(event.target.checked)}/><i/></label>;
}

export function LegacyPlansRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);
  const [nodes,setNodes]=useState<RuntimeRow[]>([]);
  const [q,setQ]=useState("");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [editing,setEditing]=useState<RuntimeRow|null>(null);
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState<PlanDraft>({...EMPTY_DRAFT});

  const load=async()=>{
    setError("");
    try{
      const [planRows,nodeRows]=await Promise.all([adminApi.plans(),adminApi.nodes()]);
      setRows(planRows);setNodes(nodeRows as unknown as RuntimeRow[]);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };
  useEffect(()=>{void load();},[]);

  const exitNodes=useMemo(()=>nodes.filter(row=>s(row.node_type).trim().toLowerCase()==="exit"),[nodes]);
  const allNodeIds=useMemo(()=>exitNodes.map(row=>n(row.id)).filter(Boolean),[exitNodes]);
  const nodeNameById=useMemo(()=>new Map(exitNodes.map(row=>[n(row.id),s(row.name)||`#${n(row.id)}`])),[exitNodes]);
  const filtered=useMemo(()=>{const value=q.trim().toLowerCase();return value?rows.filter(row=>`${row.id??""} ${row.name??""} ${row.description??""}`.toLowerCase().includes(value)):rows;},[rows,q]);

  const start=(row?:RuntimeRow)=>{
    if(row){
      setEditing(row);
      const protocols=stringList(row.protocols);const nodeIds=numberList(row.node_ids);const allowedNodeIds=nodeIds.filter(id=>allNodeIds.includes(id));
      setDraft({
        name:s(row.name),description:s(row.description),duration_days:n(row.duration_days)||30,traffic_gb:n(row.traffic_gb),device_limit:n(row.device_limit)||1,
        price_toman:n(row.price_toman),is_active:Boolean(row.is_active),protocols:protocols.length?protocols:[...ALL_PROTOCOLS],
        node_ids:allowedNodeIds.length?allowedNodeIds:[...allNodeIds],trial_enabled:Boolean(row.trial_enabled),
        trial_duration_days:n(row.trial_duration_days)||1,trial_traffic_mb:n(row.trial_traffic_mb)||500,
      });
    }else{setEditing(null);setDraft({...EMPTY_DRAFT,protocols:[...ALL_PROTOCOLS],node_ids:[...allNodeIds]});}
    setOpen(true);
  };

  const toggleProtocol=(protocol:string,checked:boolean)=>setDraft(current=>({...current,protocols:checked?Array.from(new Set([...current.protocols,protocol])):current.protocols.filter(value=>value!==protocol)}));
  const toggleNode=(nodeId:number,checked:boolean)=>setDraft(current=>({...current,node_ids:checked?Array.from(new Set([...current.node_ids,nodeId])):current.node_ids.filter(value=>value!==nodeId)}));

  const save=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    if(!draft.protocols.length){setError(pick("حداقل یک پروتکل را انتخاب کنید","Select at least one protocol"));return;}
    if(!draft.node_ids.length){setError(pick("حداقل یک سرور خارج را انتخاب کنید","Select at least one exit server"));return;}
    if(draft.trial_enabled&&(draft.trial_duration_days<1||draft.trial_duration_days>30)){setError(pick("مدت تست باید بین ۱ تا ۳۰ روز باشد","Trial duration must be between 1 and 30 days"));return;}
    if(draft.trial_enabled&&(draft.trial_traffic_mb<1||draft.trial_traffic_mb>10240)){setError(pick("حجم تست باید بین ۱ تا ۱۰۲۴۰ مگابایت باشد","Trial traffic must be between 1 and 10240 MB"));return;}
    setBusy("save");setError("");setOk("");
    try{
      if(editing)await adminApi.updatePlan(n(editing.id),draft as unknown as RuntimeRow);else await adminApi.createPlan(draft as unknown as RuntimeRow);
      setOk(editing?pick("پلن و تنظیمات تست ویرایش شد","Plan and trial settings updated"):pick("پلن با تنظیمات تست ساخته شد","Plan created with trial settings"));
      setOpen(false);await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  return <Shell active="/admin/plans"><div className="page legacy-plans-page">
    <div className="page-head"><div><h1>{pick("پلن‌ها","Plans")}</h1><small>{pick("مدیریت پلن‌های فروش، پروتکل‌ها، سرورها و اکانت تست هر پلن.","Manage sales plans, protocols, servers and per-plan trial accounts.")}</small></div><button className="primary" onClick={()=>start()}>＋ {pick("پلن جدید","New plan")}</button></div>
    <Notice error={error} ok={ok}/>
    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={q} onChange={event=>setQ(event.target.value)} placeholder={pick("جستجوی پلن…","Search plans…")}/></label><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
      <div className="table"><table><thead><tr>
        <th>{pick("پلن","Plan")}</th><th>{pick("مدت","Duration")}</th><th>{pick("حجم","Traffic")}</th><th>{pick("اکانت تست","Trial")}</th><th>{pick("پروتکل‌ها","Protocols")}</th><th>{pick("سرورهای خارج","Exit servers")}</th><th>{pick("قیمت","Price")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th>
      </tr></thead><tbody>{filtered.map(row=>{
        const id=n(row.id);const protocols=stringList(row.protocols);const nodeIds=numberList(row.node_ids);const trialEnabled=Boolean(row.trial_enabled);
        return <tr key={s(row.id)}>
          <td><b>{s(row.name)}</b><small>{s(row.description)}</small></td><td>{n(row.duration_days)} {pick("روز","days")}</td><td>{n(row.traffic_gb)} GB · {n(row.device_limit)} {pick("دستگاه","devices")}</td>
          <td><Badge tone={trialEnabled?"ok":"bad"}>{trialEnabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge>{trialEnabled&&<small>{n(row.trial_duration_days)||1} {pick("روز","days")} · {n(row.trial_traffic_mb)||500} MB</small>}</td>
          <td><b>{protocols.length||15}/15</b><small>{protocols.slice(0,4).join(" · ")}{protocols.length>4?" …":""}</small></td>
          <td><b>{nodeIds.length||allNodeIds.length}</b><small>{nodeIds.slice(0,3).map(nodeId=>nodeNameById.get(nodeId)||`#${nodeId}`).join(" · ")}{nodeIds.length>3?" …":""}</small></td>
          <td>{n(row.price_toman).toLocaleString("fa-IR")} {pick("تومان","Toman")}</td><td><Badge tone={row.is_active?"ok":"bad"}>{row.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td>
          <td><div className="row-actions"><button onClick={()=>start(row)}>{pick("ویرایش","Edit")}</button><button className="danger" onClick={()=>{if(window.confirm(pick("پلن حذف شود؟","Delete plan?")))void adminApi.deletePlan(id).then(load).catch(reason=>setError(reason instanceof Error?reason.message:String(reason)));}}>{pick("حذف","Delete")}</button></div></td>
        </tr>;
      })}</tbody></table></div>
    </Card>

    {open&&<div className="runtime-modal"><button className="runtime-modal-bg" type="button" onClick={()=>setOpen(false)}/><form className="runtime-modal-card wide" onSubmit={save}>
      <div className="card-head"><div><b>{editing?pick("ویرایش پلن","Edit plan"):pick("پلن جدید","New plan")}</b><small>{pick("تنظیمات فروش و اکانت تست مستقیماً روی همین پلن ذخیره می‌شوند.","Sales and trial settings are stored directly for this plan.")}</small></div><button type="button" className="icon-button" onClick={()=>setOpen(false)}>×</button></div>
      <div className="setting-grid">
        <label className="field"><span>{pick("نام","Name")}</span><input required value={draft.name} onChange={event=>setDraft(current=>({...current,name:event.target.value}))}/></label>
        <label className="field"><span>{pick("توضیحات","Description")}</span><input value={draft.description} onChange={event=>setDraft(current=>({...current,description:event.target.value}))}/></label>
        <label className="field"><span>{pick("مدت روز","Duration days")}</span><input type="number" min={1} value={draft.duration_days} onChange={event=>setDraft(current=>({...current,duration_days:Number(event.target.value)}))}/></label>
        <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={0} value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:Number(event.target.value)}))}/></label>
        <label className="field"><span>{pick("تعداد دستگاه","Device limit")}</span><input type="number" min={1} value={draft.device_limit} onChange={event=>setDraft(current=>({...current,device_limit:Number(event.target.value)}))}/></label>
        <label className="field"><span>{pick("قیمت تومان","Price Toman")}</span><input type="number" min={0} value={draft.price_toman} onChange={event=>setDraft(current=>({...current,price_toman:Number(event.target.value)}))}/></label>
      </div>

      <div className="card-head"><div><b>{pick("اکانت تست این پلن","Trial account for this plan")}</b><small>{pick("هر کاربر در کل TwinPanel فقط یک‌بار می‌تواند اکانت تست بگیرد. مقدار پیش‌فرض ۱ روز و ۵۰۰MB است.","Each TwinPanel user can claim a trial only once. Default is 1 day and 500 MB.")}</small></div><Badge tone={draft.trial_enabled?"ok":"bad"}>{draft.trial_enabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></div>
      <div className="protocol-toggle-grid"><Check label={pick("فعال‌سازی اکانت تست برای این پلن","Enable trial for this plan")} checked={draft.trial_enabled} onChange={checked=>setDraft(current=>({...current,trial_enabled:checked}))}/></div>
      <div className="setting-grid">
        <label className="field"><span>{pick("مدت تست (روز)","Trial duration (days)")}</span><input type="number" min={1} max={30} value={draft.trial_duration_days} onChange={event=>setDraft(current=>({...current,trial_duration_days:Number(event.target.value)}))}/></label>
        <label className="field"><span>{pick("حجم تست (MB)","Trial traffic (MB)")}</span><input type="number" min={1} max={10240} value={draft.trial_traffic_mb} onChange={event=>setDraft(current=>({...current,trial_traffic_mb:Number(event.target.value)}))}/></label>
      </div>

      <div className="card-head"><div><b>{pick("پروتکل‌ها · ۱۵ مورد","Protocols · 15")}</b><small>{pick("اکانت تست هم دقیقاً Snapshot پروتکل‌های همین پلن را می‌گیرد.","Trial accounts snapshot the same protocols selected for this plan.")}</small></div><button type="button" className="ghost" onClick={()=>setDraft(current=>({...current,protocols:[...ALL_PROTOCOLS]}))}>{pick("انتخاب همه","Select all")}</button></div>
      <div className="protocol-toggle-grid">{PROTOCOLS.map(([key,label])=><Check key={key} label={label} checked={draft.protocols.includes(key)} onChange={checked=>toggleProtocol(key,checked)}/>)}</div>

      <div className="card-head"><div><b>{pick("سرورهای خارج مجاز","Allowed exit servers")}</b><small>{pick("اکانت تست هم فقط روی سرورهای Snapshot همین پلن ساخته می‌شود.","Trial accounts use only the exit-server snapshot of this plan.")}</small></div><button type="button" className="ghost" onClick={()=>setDraft(current=>({...current,node_ids:[...allNodeIds]}))}>{pick("انتخاب همه","Select all")}</button></div>
      <div className="protocol-toggle-grid">{exitNodes.map(row=>{const nodeId=n(row.id);const label=`${s(row.name)||`#${nodeId}`} · ${s(row.country_code)} · ${s(row.node_type)}`;return <Check key={nodeId} label={label} checked={draft.node_ids.includes(nodeId)} onChange={checked=>toggleNode(nodeId,checked)}/>;})}</div>
      <div className="protocol-toggle-grid"><Check label={pick("فعال / منتشرشده","Active / published")} checked={draft.is_active} onChange={checked=>setDraft(current=>({...current,is_active:checked}))}/></div>
      <div className="runtime-modal-actions"><button type="button" className="ghost" onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={!!busy}>{busy?"…":pick("ذخیره","Save")}</button></div>
    </form></div>}
  </div></Shell>;
}
