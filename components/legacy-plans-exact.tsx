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
      setRows(await adminApi.plans());
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
    }else{
      setEditing(null);
      setDraft({...EMPTY_DRAFT});
    }
    setOpen(true);
  };

  const save=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;

    setBusy("save");
    setError("");
    setOk("");

    try{
      if(editing){
        await adminApi.updatePlan(n(editing.id),draft as unknown as RuntimeRow);
      }else{
        await adminApi.createPlan(draft as unknown as RuntimeRow);
      }

      setOk(editing?pick("پلن ویرایش شد","Plan updated"):pick("پلن ساخته شد","Plan created"));
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
            <small>{pick("پلن فقط قیمت، حجم، مدت و محدودیت دستگاه را تعیین می‌کند. پروتکل‌ها هنگام ساخت هر اشتراک انتخاب می‌شوند.","Plans define only price, traffic, duration and device limit. Protocols are selected per subscription at creation time.")}</small>
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
                  <th>{pick("دستگاه","Devices")}</th>
                  <th>{pick("قیمت","Price")}</th>
                  <th>{pick("وضعیت","Status")}</th>
                  <th>{pick("عملیات","Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(row=>{
                  const id=n(row.id);
                  return (
                    <tr key={s(row.id)}>
                      <td><b>{s(row.name)}</b><small>{s(row.description)}</small></td>
                      <td>{n(row.duration_days)} {pick("روز","days")}</td>
                      <td>{n(row.traffic_gb)} GB</td>
                      <td>{n(row.device_limit)}</td>
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
                  <small>{pick("پروتکل در پلن تعریف نمی‌شود؛ هنگام ساخت اشتراک انتخابش کنید.","Protocols are not defined on plans; choose them when creating a subscription.")}</small>
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
