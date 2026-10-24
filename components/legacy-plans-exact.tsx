"use client";

import Link from "next/link";
import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {adminApi,RuntimeRow} from "../lib/admin-api";
import {planProtocolApi,PlanProtocolDefinition} from "../lib/plan-protocol-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{
  const parsed=Number(value??0);
  return Number.isFinite(parsed)?parsed:0;
};

const CLASSIC_KEYS=["cisco","openvpn","wireguard","l2tp","v2ray"] as const;
const CLASSIC_FLAG:Record<string,string>={
  cisco:"enable_cisco",
  openvpn:"enable_openvpn",
  wireguard:"enable_wireguard",
  l2tp:"enable_l2tp",
  v2ray:"enable_v2ray",
};

const EMPTY_DRAFT={
  name:"",
  description:"",
  duration_days:30,
  traffic_gb:50,
  device_limit:1,
  price_toman:0,
  is_active:true,
};

type PlanDraft=typeof EMPTY_DRAFT;
type PlanProtocolMap=Record<number,string[]>;

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

function legacyClassicSelection(row:RuntimeRow){
  return CLASSIC_KEYS.filter(key=>Boolean(row[CLASSIC_FLAG[key]]));
}

export function LegacyPlansRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);
  const [catalog,setCatalog]=useState<PlanProtocolDefinition[]>([]);
  const [planProtocols,setPlanProtocols]=useState<PlanProtocolMap>({});
  const [q,setQ]=useState("");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [editing,setEditing]=useState<RuntimeRow|null>(null);
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState<PlanDraft>({...EMPTY_DRAFT});
  const [selectedProtocols,setSelectedProtocols]=useState<string[]>([...CLASSIC_KEYS]);

  const labels=useMemo(()=>Object.fromEntries(catalog.map(item=>[item.key,item.title])),[catalog]);
  const classicCatalog=useMemo(()=>catalog.filter(item=>item.family==="classic"),[catalog]);
  const modernCatalog=useMemo(()=>catalog.filter(item=>item.family==="modern"),[catalog]);

  const load=async()=>{
    setError("");
    try{
      const [planRows,catalogPayload]=await Promise.all([
        adminApi.plans(),
        planProtocolApi.catalog(),
      ]);

      const selections=await Promise.all(
        planRows.map(async row=>{
          const id=n(row.id);
          if(!id)return [id,legacyClassicSelection(row)] as const;
          try{
            const response=await planProtocolApi.get(id);
            return [id,response.protocols] as const;
          }catch{
            return [id,legacyClassicSelection(row)] as const;
          }
        }),
      );

      setRows(planRows);
      setCatalog(catalogPayload.protocols);
      setPlanProtocols(Object.fromEntries(selections));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }
  };

  useEffect(()=>{void load();},[]);

  const filtered=useMemo(()=>{
    const value=q.trim().toLowerCase();
    if(!value)return rows;
    return rows.filter(row=>`${row.id??""} ${row.name??""} ${row.description??""}`.toLowerCase().includes(value));
  },[rows,q]);

  const start=(row?:RuntimeRow)=>{
    if(row){
      const id=n(row.id);
      setEditing(row);
      setDraft({
        name:s(row.name),
        description:s(row.description),
        duration_days:n(row.duration_days)||30,
        traffic_gb:n(row.traffic_gb),
        device_limit:n(row.device_limit)||1,
        price_toman:n(row.price_toman),
        is_active:Boolean(row.is_active),
      });
      setSelectedProtocols(planProtocols[id]??legacyClassicSelection(row));
    }else{
      setEditing(null);
      setDraft({...EMPTY_DRAFT});
      setSelectedProtocols([...CLASSIC_KEYS]);
    }
    setOpen(true);
  };

  const toggleProtocol=(key:string,checked:boolean)=>{
    setSelectedProtocols(current=>{
      if(checked)return current.includes(key)?current:[...current,key];
      return current.filter(item=>item!==key);
    });
  };

  const save=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;
    if(selectedProtocols.length===0){
      setError(pick("حداقل یک پروتکل برای پلن انتخاب کنید","Select at least one protocol for the plan"));
      return;
    }

    setBusy("save");
    setError("");
    setOk("");

    const payload:RuntimeRow={...draft};
    for(const key of CLASSIC_KEYS){
      payload[CLASSIC_FLAG[key]]=selectedProtocols.includes(key);
    }

    try{
      let planId=editing?n(editing.id):0;
      if(editing){
        await adminApi.updatePlan(planId,payload);
      }else{
        const created=await adminApi.createPlan(payload);
        planId=n(created.id);
      }

      if(!planId)throw new Error(pick("شناسه پلن دریافت نشد","Plan id was not returned"));

      await planProtocolApi.set(planId,selectedProtocols);
      setOk(editing?pick("پلن و پروتکل‌ها ویرایش شد","Plan and protocols updated"):pick("پلن با پروتکل‌های انتخابی ساخته شد","Plan created with selected protocols"));
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
            <small>{pick("مدیریت پلن و دسترسی هر ۱۵ پروتکل","Manage plans and all 15 protocol entitlements")}</small>
          </div>
          <div className="row-actions">
            <Link className="ghost" href="/admin/modern-protocols">{pick("وضعیت پروتکل‌های جدید","Modern protocol runtime")}</Link>
            <button className="primary" onClick={()=>start()}>＋ {pick("پلن جدید","New plan")}</button>
          </div>
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
                  <th>{pick("دستگاه","Devices")}</th>
                  <th>{pick("قیمت","Price")}</th>
                  <th>{pick("پروتکل‌ها","Protocols")}</th>
                  <th>{pick("وضعیت","Status")}</th>
                  <th>{pick("عملیات","Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(row=>{
                  const id=n(row.id);
                  const selected=planProtocols[id]??legacyClassicSelection(row);
                  return (
                    <tr key={s(row.id)}>
                      <td><b>{s(row.name)}</b><small>{s(row.description)}</small></td>
                      <td>{n(row.duration_days)} {pick("روز","days")}</td>
                      <td>{n(row.traffic_gb)} GB</td>
                      <td>{n(row.device_limit)}</td>
                      <td>{n(row.price_toman).toLocaleString("fa-IR")} {pick("تومان","Toman")}</td>
                      <td>
                        <div className="protocol-mini-list">
                          {selected.map(key=><span key={key}>{labels[key]??key}</span>)}
                        </div>
                      </td>
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
                <b>{editing?pick("ویرایش پلن","Edit plan"):pick("پلن جدید","New plan")}</b>
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

              <div className="card-head">
                <b>{pick("پروتکل‌های کلاسیک","Classic protocols")}</b>
                <small>{classicCatalog.length}/5</small>
              </div>
              <div className="protocol-toggle-grid">
                {classicCatalog.map(item=><Check key={item.key} label={item.title} checked={selectedProtocols.includes(item.key)} onChange={checked=>toggleProtocol(item.key,checked)}/>) }
              </div>

              <div className="card-head">
                <b>{pick("پروتکل‌های جدید","Modern protocols")}</b>
                <small>{modernCatalog.length}/10</small>
              </div>
              <div className="protocol-toggle-grid">
                {modernCatalog.map(item=><Check key={item.key} label={item.title} checked={selectedProtocols.includes(item.key)} onChange={checked=>toggleProtocol(item.key,checked)}/>) }
              </div>

              <div className="protocol-toggle-grid">
                <Check label={pick("فعال / منتشرشده","Active / published")} checked={draft.is_active} onChange={checked=>setDraft(current=>({...current,is_active:checked}))}/>
              </div>

              <div className="runtime-modal-actions">
                <button type="button" className="ghost" onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button>
                <button className="primary" disabled={!!busy||catalog.length!==15}>{busy?"…":pick("ذخیره","Save")}</button>
              </div>
            </form>
          </div>
        )}
      </div>
    </Shell>
  );
}
