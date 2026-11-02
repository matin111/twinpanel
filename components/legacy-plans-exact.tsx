"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {adminApi,RuntimeRow} from "../lib/admin-api";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{
  const parsed=Number(value??0);
  return Number.isFinite(parsed)?parsed:0;
};
const stringList=(value:unknown)=>Array.isArray(value)?value.map(item=>String(item)).filter(Boolean):[];
const numberList=(value:unknown)=>Array.isArray(value)?value.map(item=>Number(item)).filter(item=>Number.isFinite(item)&&item>0):[];

const PROTOCOLS=[
  ["cisco","Cisco / OpenConnect"],
  ["openvpn","OpenVPN"],
  ["wireguard","WireGuard"],
  ["l2tp","L2TP / IPsec"],
  ["v2ray","V2Ray / Xray"],
  ["hysteria2","Hysteria2"],
  ["tuic","TUIC"],
  ["anytls","AnyTLS"],
  ["naive","NaiveProxy"],
  ["shadowtls","ShadowTLS"],
  ["snell","Snell"],
  ["mieru","Mieru"],
  ["trusttunnel","TrustTunnel"],
  ["amneziawg","AmneziaWG"],
  ["sudoku","Sudoku"],
] as const;
const ALL_PROTOCOLS=PROTOCOLS.map(([key])=>key);

type PlanDraft={
  name:string;
  description:string;
  duration_days:number;
  traffic_gb:number;
  device_limit:number;
  price_toman:number;
  is_active:boolean;
  protocols:string[];
  node_ids:number[];
};

type TrialSettings={
  enabled:boolean;
  duration_days:number;
  traffic_gb:number;
  device_limit:number;
  scope?:string;
};

const EMPTY_DRAFT:PlanDraft={
  name:"",
  description:"",
  duration_days:30,
  traffic_gb:50,
  device_limit:1,
  price_toman:0,
  is_active:true,
  protocols:[...ALL_PROTOCOLS],
  node_ids:[],
};

const DEFAULT_TRIAL:TrialSettings={
  enabled:false,
  duration_days:1,
  traffic_gb:1,
  device_limit:1,
  scope:"global",
};

async function trialSettingsRequest(init?:RequestInit):Promise<TrialSettings>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init?.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init?.body)headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}/v1/settings/general/trial-account`,{...init,headers,cache:"no-store"});
  const payload=await response.json().catch(()=>({})) as TrialSettings&{detail?:string};
  if(!response.ok)throw new Error(payload.detail||`API error ${response.status}`);
  return payload;
}

function Notice({error,ok}:{error:string;ok:string}){
  return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;
}

function Check({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}){
  return (
    <label className="toggle module-toggle compact-toggle">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={event=>onChange(event.target.checked)}/>
      <i/>
    </label>
  );
}

export function LegacyPlansRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);
  const [nodes,setNodes]=useState<RuntimeRow[]>([]);
  const [trial,setTrial]=useState<TrialSettings>({...DEFAULT_TRIAL});
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
      const [planRows,nodeRows,trialSettings]=await Promise.all([
        adminApi.plans(),
        adminApi.nodes(),
        trialSettingsRequest(),
      ]);
      setRows(planRows);
      setNodes(nodeRows as unknown as RuntimeRow[]);
      setTrial({...DEFAULT_TRIAL,...trialSettings});
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }
  };

  useEffect(()=>{void load();},[]);

  const exitNodes=useMemo(()=>nodes.filter(row=>s(row.node_type).trim().toLowerCase()==="exit"),[nodes]);
  const allNodeIds=useMemo(()=>exitNodes.map(row=>n(row.id)).filter(Boolean),[exitNodes]);
  const nodeNameById=useMemo(()=>new Map(exitNodes.map(row=>[n(row.id),s(row.name)||`#${n(row.id)}`])),[exitNodes]);

  const filtered=useMemo(()=>{
    const value=q.trim().toLowerCase();
    if(!value)return rows;
    return rows.filter(row=>`${row.id??""} ${row.name??""} ${row.description??""}`.toLowerCase().includes(value));
  },[rows,q]);

  const start=(row?:RuntimeRow)=>{
    if(row){
      setEditing(row);
      const protocols=stringList(row.protocols);
      const nodeIds=numberList(row.node_ids);
      const allowedNodeIds=nodeIds.filter(nodeId=>allNodeIds.includes(nodeId));
      setDraft({
        name:s(row.name),
        description:s(row.description),
        duration_days:n(row.duration_days)||30,
        traffic_gb:n(row.traffic_gb),
        device_limit:n(row.device_limit)||1,
        price_toman:n(row.price_toman),
        is_active:Boolean(row.is_active),
        protocols:protocols.length?protocols:[...ALL_PROTOCOLS],
        node_ids:allowedNodeIds.length?allowedNodeIds:[...allNodeIds],
      });
    }else{
      setEditing(null);
      setDraft({...EMPTY_DRAFT,protocols:[...ALL_PROTOCOLS],node_ids:[...allNodeIds]});
    }
    setOpen(true);
  };

  const toggleProtocol=(protocol:string,checked:boolean)=>setDraft(current=>({
    ...current,
    protocols:checked
      ? Array.from(new Set([...current.protocols,protocol]))
      : current.protocols.filter(value=>value!==protocol),
  }));

  const toggleNode=(nodeId:number,checked:boolean)=>setDraft(current=>({
    ...current,
    node_ids:checked
      ? Array.from(new Set([...current.node_ids,nodeId]))
      : current.node_ids.filter(value=>value!==nodeId),
  }));

  const saveTrial=async()=>{
    if(busy)return;
    setBusy("trial");
    setError("");
    setOk("");
    try{
      const saved=await trialSettingsRequest({
        method:"PUT",
        body:JSON.stringify({
          enabled:trial.enabled,
          duration_days:Math.max(1,Math.min(30,n(trial.duration_days)||1)),
          traffic_gb:Math.max(1,Math.min(100,n(trial.traffic_gb)||1)),
          device_limit:Math.max(1,Math.min(10,n(trial.device_limit)||1)),
        }),
      });
      setTrial(saved);
      setOk(pick("تنظیمات عمومی اکانت تست ذخیره شد","Global trial account settings saved"));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  const save=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;
    if(!draft.protocols.length){setError(pick("حداقل یک پروتکل را انتخاب کنید","Select at least one protocol"));return;}
    if(!draft.node_ids.length){setError(pick("حداقل یک سرور خارج را انتخاب کنید","Select at least one exit server"));return;}

    setBusy("save");
    setError("");
    setOk("");

    try{
      if(editing){
        await adminApi.updatePlan(n(editing.id),draft as unknown as RuntimeRow);
      }else{
        await adminApi.createPlan(draft as unknown as RuntimeRow);
      }

      setOk(editing?pick("پلن ویرایش شد","Plan updated"):pick("پلن با پروتکل‌ها و سرورهای خارج انتخابی ساخته شد","Plan created with selected protocols and exit servers"));
      setOpen(false);
      await load();
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  return (
    <Shell active="/admin/plans">
      <div className="page legacy-plans-page">
        <div className="page-head">
          <div>
            <h1>{pick("پلن‌ها","Plans")}</h1>
            <small>{pick("مدیریت پلن‌های فروش و تنظیم عمومی اکانت تست.","Manage sales plans and the global trial account policy.")}</small>
          </div>
          <button className="primary" onClick={()=>start()}>＋ {pick("پلن جدید","New plan")}</button>
        </div>

        <Notice error={error} ok={ok}/>

        <Card>
          <div className="card-head">
            <div>
              <b>{pick("اکانت تست عمومی","Global trial account")}</b>
              <small>{pick("این تنظیم برای کل پنل است و به هیچ پلن خاصی وابسته نیست.","This policy is global and is not attached to any individual plan.")}</small>
            </div>
            <Badge tone={trial.enabled?"ok":"bad"}>{trial.enabled?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge>
          </div>

          <div className="protocol-toggle-grid">
            <Check label={pick("فعال‌سازی اکانت تست","Enable trial accounts")} checked={trial.enabled} onChange={enabled=>setTrial(current=>({...current,enabled}))}/>
          </div>

          <div className="setting-grid">
            <label className="field"><span>{pick("مدت تست (روز)","Trial duration (days)")}</span><input type="number" min={1} max={30} value={trial.duration_days} onChange={event=>setTrial(current=>({...current,duration_days:Number(event.target.value)}))}/></label>
            <label className="field"><span>{pick("حجم تست (GB)","Trial traffic (GB)")}</span><input type="number" min={1} max={100} value={trial.traffic_gb} onChange={event=>setTrial(current=>({...current,traffic_gb:Number(event.target.value)}))}/></label>
            <label className="field"><span>{pick("تعداد دستگاه","Device limit")}</span><input type="number" min={1} max={10} value={trial.device_limit} onChange={event=>setTrial(current=>({...current,device_limit:Number(event.target.value)}))}/></label>
          </div>

          <div className="runtime-modal-actions">
            <button className="primary" type="button" disabled={!!busy} onClick={()=>void saveTrial()}>{busy==="trial"?"…":pick("ذخیره تنظیمات تست","Save trial settings")}</button>
          </div>
        </Card>

        <Card>
          <div className="runtime-toolbar">
            <label>⌕ <input value={q} onChange={event=>setQ(event.target.value)} placeholder={pick("جستجوی پلن…","Search plans…")}/></label>
            <button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
          </div>

          <div className="table">
            <table>
              <thead>
                <tr>
                  <th>{pick("پلن","Plan")}</th>
                  <th>{pick("مدت","Duration")}</th>
                  <th>{pick("حجم","Traffic")}</th>
                  <th>{pick("پروتکل‌ها","Protocols")}</th>
                  <th>{pick("سرورهای خارج","Exit servers")}</th>
                  <th>{pick("قیمت","Price")}</th>
                  <th>{pick("وضعیت","Status")}</th>
                  <th>{pick("عملیات","Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(row=>{
                  const id=n(row.id);
                  const protocols=stringList(row.protocols);
                  const nodeIds=numberList(row.node_ids);
                  return (
                    <tr key={s(row.id)}>
                      <td><b>{s(row.name)}</b><small>{s(row.description)}</small></td>
                      <td>{n(row.duration_days)} {pick("روز","days")}</td>
                      <td>{n(row.traffic_gb)} GB · {n(row.device_limit)} {pick("دستگاه","devices")}</td>
                      <td><b>{protocols.length||15}/15</b><small>{protocols.slice(0,4).join(" · ")}{protocols.length>4?" …":""}</small></td>
                      <td><b>{nodeIds.length||allNodeIds.length}</b><small>{nodeIds.slice(0,3).map(nodeId=>nodeNameById.get(nodeId)||`#${nodeId}`).join(" · ")}{nodeIds.length>3?" …":""}</small></td>
                      <td>{n(row.price_toman).toLocaleString("fa-IR")} {pick("تومان","Toman")}</td>
                      <td><Badge tone={row.is_active?"ok":"bad"}>{row.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td>
                      <td>
                        <div className="row-actions">
                          <button onClick={()=>start(row)}>{pick("ویرایش","Edit")}</button>
                          <button className="danger" onClick={()=>{
                            if(window.confirm(pick("پلن حذف شود؟","Delete plan?"))){
                              void adminApi.deletePlan(id).then(load).catch(reason=>setError(reason instanceof Error?reason.message:String(reason)));
                            }
                          }}>{pick("حذف","Delete")}</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        {open&&(
          <div className="runtime-modal">
            <button className="runtime-modal-bg" type="button" onClick={()=>setOpen(false)}/>
            <form className="runtime-modal-card wide" onSubmit={save}>
              <div className="card-head">
                <div>
                  <b>{editing?pick("ویرایش پلن","Edit plan"):pick("پلن جدید","New plan")}</b>
                  <small>{pick("پروتکل‌ها و سرورهای خارج مجاز این پلن را انتخاب کنید. سرورهای ایران فقط برای تانل هستند.","Choose the protocols and allowed exit servers for this plan. Iran nodes are reserved for tunnels.")}</small>
                </div>
                <button type="button" className="icon-button" onClick={()=>setOpen(false)}>×</button>
              </div>

              <div className="setting-grid">
                <label className="field"><span>{pick("نام","Name")}</span><input required value={draft.name} onChange={event=>setDraft(current=>({...current,name:event.target.value}))}/></label>
                <label className="field"><span>{pick("توضیحات","Description")}</span><input value={draft.description} onChange={event=>setDraft(current=>({...current,description:event.target.value}))}/></label>
                <label className="field"><span>{pick("مدت روز","Duration days")}</span><input type="number" min={1} value={draft.duration_days} onChange={event=>setDraft(current=>({...current,duration_days:Number(event.target.value)}))}/></label>
                <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={0} value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:Number(event.target.value)}))}/></label>
                <label className="field"><span>{pick("تعداد دستگاه","Device limit")}</span><input type="number" min={1} value={draft.device_limit} onChange={event=>setDraft(current=>({...current,device_limit:Number(event.target.value)}))}/></label>
                <label className="field"><span>{pick("قیمت تومان","Price Toman")}</span><input type="number" min={0} value={draft.price_toman} onChange={event=>setDraft(current=>({...current,price_toman:Number(event.target.value)}))}/></label>
              </div>

              <div className="card-head"><div><b>{pick("پروتکل‌ها · ۱۵ مورد","Protocols · 15")}</b><small>{pick("همه انتخاب شده‌اند؛ در صورت نیاز هر مورد را جدا خاموش کنید.","All are selected by default; disable individual protocols when needed.")}</small></div><button type="button" className="ghost" onClick={()=>setDraft(current=>({...current,protocols:[...ALL_PROTOCOLS]}))}>{pick("انتخاب همه","Select all")}</button></div>
              <div className="protocol-toggle-grid">
                {PROTOCOLS.map(([key,label])=><Check key={key} label={label} checked={draft.protocols.includes(key)} onChange={checked=>toggleProtocol(key,checked)}/>)}
              </div>

              <div className="card-head"><div><b>{pick("سرورهای خارج مجاز","Allowed exit servers")}</b><small>{pick("فقط سرورهای خارج انتخاب‌شده هنگام ساخت اشتراک روی اکانت ثبت می‌شوند.","Only selected exit servers are snapshotted onto subscriptions created from this plan.")}</small></div><button type="button" className="ghost" onClick={()=>setDraft(current=>({...current,node_ids:[...allNodeIds]}))}>{pick("انتخاب همه","Select all")}</button></div>
              <div className="protocol-toggle-grid">
                {exitNodes.map(row=>{const nodeId=n(row.id);const label=`${s(row.name)||`#${nodeId}`} · ${s(row.country_code)} · ${s(row.node_type)}`;return <Check key={nodeId} label={label} checked={draft.node_ids.includes(nodeId)} onChange={checked=>toggleNode(nodeId,checked)}/>;})}
              </div>

              <div className="protocol-toggle-grid">
                <Check label={pick("فعال / منتشرشده","Active / published")} checked={draft.is_active} onChange={checked=>setDraft(current=>({...current,is_active:checked}))}/>
              </div>

              <div className="runtime-modal-actions">
                <button type="button" className="ghost" onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button>
                <button className="primary" disabled={!!busy}>{busy?"…":pick("ذخیره","Save")}</button>
              </div>
            </form>
          </div>
        )}
      </div>
    </Shell>
  );
}
