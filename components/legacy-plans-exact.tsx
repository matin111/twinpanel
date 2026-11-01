"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {adminApi,RuntimeRow} from "../lib/admin-api";
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
      setRows(planRows);
      setNodes(nodeRows as unknown as RuntimeRow[]);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }
  };

  useEffect(()=>{void load();},[]);

  const allNodeIds=useMemo(()=>nodes.map(row=>n(row.id)).filter(Boolean),[nodes]);
  const nodeNameById=useMemo(()=>new Map(nodes.map(row=>[n(row.id),s(row.name)||`#${n(row.id)}`])),[nodes]);

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
      setDraft({
        name:s(row.name),
        description:s(row.description),
        duration_days:n(row.duration_days)||30,
        traffic_gb:n(row.traffic_gb),
        device_limit:n(row.device_limit)||1,
        price_toman:n(row.price_toman),
        is_active:Boolean(row.is_active),
        protocols:protocols.length?protocols:[...ALL_PROTOCOLS],
        node_ids:nodeIds.length?nodeIds:[...allNodeIds],
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

  const save=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;
    if(!draft.protocols.length){setError(pick("حداقل یک پروتکل را انتخاب کنید","Select at least one protocol"));return;}
    if(!draft.node_ids.length){setError(pick("حداقل یک سرور را انتخاب کنید","Select at least one server"));return;}

    setBusy("save");
    setError("");
    setOk("");

    try{
      if(editing){
        await adminApi.updatePlan(n(editing.id),draft as unknown as RuntimeRow);
      }else{
        await adminApi.createPlan(draft as unknown as RuntimeRow);
      }

      setOk(editing?pick("پلن ویرایش شد","Plan updated"):pick("پلن با پروتکل‌ها و سرورهای انتخابی ساخته شد","Plan created with selected protocols and servers"));
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
            <small>{pick("هر پلن می‌تواند هر ۱۵ پروتکل و سرورهای مجاز خودش را داشته باشد. هنگام ساخت اکانت، این انتخاب‌ها روی خود اشتراک ثبت می‌شوند.","Each plan can define all 15 protocols and its allowed servers. The selection is snapshotted onto each subscription at creation time.")}</small>
          </div>
          <button className="primary" onClick={()=>start()}>＋ {pick("پلن جدید","New plan")}</button>
        </div>

        <Notice error={error} ok={ok}/>

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
                  <th>{pick("سرورها","Servers")}</th>
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
                  <small>{pick("پروتکل‌ها و سرورهای مجاز این پلن را انتخاب کنید. اکانت‌های قبلی با ویرایش پلن تغییر نمی‌کنند.","Choose the protocols and allowed servers for this plan. Existing accounts are not changed by later plan edits.")}</small>
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

              <div className="card-head"><div><b>{pick("سرورهای مجاز","Allowed servers")}</b><small>{pick("فقط سرورهای انتخاب‌شده هنگام ساخت اشتراک روی آن اکانت ثبت می‌شوند.","Only selected servers are snapshotted onto subscriptions created from this plan.")}</small></div><button type="button" className="ghost" onClick={()=>setDraft(current=>({...current,node_ids:[...allNodeIds]}))}>{pick("انتخاب همه","Select all")}</button></div>
              <div className="protocol-toggle-grid">
                {nodes.map(row=>{const nodeId=n(row.id);const label=`${s(row.name)||`#${nodeId}`} · ${s(row.country_code)} · ${s(row.node_type)}`;return <Check key={nodeId} label={label} checked={draft.node_ids.includes(nodeId)} onChange={checked=>toggleNode(nodeId,checked)}/>;})}
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
