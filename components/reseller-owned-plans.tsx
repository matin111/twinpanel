"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {resellerApi,ResellerOwnedPlanPayload,ResellerRow} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const num=(row:ResellerRow,key:string)=>{const value=Number(row?.[key]??0);return Number.isFinite(value)?value:0;};
const str=(row:ResellerRow,key:string)=>String(row?.[key]??"");
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const defaults:ResellerOwnedPlanPayload={title:"",traffic_gb:50,duration_days:30,device_limit:1,sell_price_toman:0,enable_cisco:true,enable_openvpn:true,enable_wireguard:true,enable_l2tp:true,enable_v2ray:true,sort_order:100,is_active:true};
const protocolRows:[keyof ResellerOwnedPlanPayload,string][]=[["enable_cisco","Cisco / OpenConnect"],["enable_openvpn","OpenVPN"],["enable_wireguard","WireGuard"],["enable_l2tp","L2TP / IPsec"],["enable_v2ray","V2Ray / Xray"]];

function planForm(row:ResellerRow):ResellerOwnedPlanPayload{
  return {
    title:str(row,"title")||str(row,"name"),
    traffic_gb:num(row,"traffic_gb"),
    duration_days:num(row,"duration_days"),
    device_limit:num(row,"device_limit")||1,
    sell_price_toman:num(row,"sell_price_toman"),
    enable_cisco:Boolean(row.enable_cisco),
    enable_openvpn:Boolean(row.enable_openvpn),
    enable_wireguard:Boolean(row.enable_wireguard),
    enable_l2tp:Boolean(row.enable_l2tp),
    enable_v2ray:Boolean(row.enable_v2ray),
    sort_order:row.sort_order==null?100:num(row,"sort_order"),
    is_active:Boolean(row.is_active)
  };
}

export function ResellerOwnedPlansRuntime(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<ResellerRow[]>([]);
  const [form,setForm]=useState<ResellerOwnedPlanPayload>(defaults);
  const [editing,setEditing]=useState<number|null>(null);
  const [open,setOpen]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const editorRef=useRef<HTMLDivElement|null>(null);
  const titleRef=useRef<HTMLInputElement|null>(null);

  const load=async()=>{setError("");try{setRows(await resellerApi.plans());}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  useEffect(()=>{void load();},[]);

  useEffect(()=>{
    if(!open)return;
    const frame=requestAnimationFrame(()=>{
      editorRef.current?.scrollIntoView({behavior:"smooth",block:"start"});
      window.setTimeout(()=>titleRef.current?.focus({preventScroll:true}),180);
    });
    return()=>cancelAnimationFrame(frame);
  },[open,editing]);

  const active=useMemo(()=>rows.filter(row=>Boolean(row.is_active)).length,[rows]);
  const avg=useMemo(()=>rows.length?Math.round(rows.reduce((sum,row)=>sum+num(row,"sell_price_toman"),0)/rows.length):0,[rows]);

  const closeEditor=()=>{setOpen(false);setEditing(null);setForm(defaults);};
  const startCreate=()=>{setEditing(null);setForm(defaults);setError("");setOk("");setOpen(true);};
  const startEdit=(row:ResellerRow)=>{
    const id=Number(row.id||0);
    if(!id){setError(pick("شناسه پلن معتبر نیست.","Invalid plan id."));return;}
    setEditing(id);
    setForm(planForm(row));
    setError("");setOk("");setOpen(true);
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    if(!form.title.trim()){setError(pick("عنوان پلن را وارد کنید.","Enter a plan title."));return;}
    if(!protocolRows.some(([key])=>Boolean(form[key]))){setError(pick("حداقل یک پروتکل را فعال کنید.","Enable at least one protocol."));return;}
    const editingId=editing;
    setBusy(true);setError("");setOk("");
    try{
      const payload={...form,title:form.title.trim()};
      if(editingId)await resellerApi.updatePlan(editingId,payload);else await resellerApi.createPlan(payload);
      await load();
      closeEditor();
      setOk(editingId?pick(`پلن #${editingId} با موفقیت بروزرسانی شد.`,`Plan #${editingId} updated successfully.`):pick("پلن ربات ساخته شد.","Bot plan created."));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
      editorRef.current?.scrollIntoView({behavior:"smooth",block:"start"});
    }finally{setBusy(false);}
  };

  const disable=async(row:ResellerRow)=>{
    const id=Number(row.id||0);if(!id)return;
    if(!window.confirm(pick("این پلن غیرفعال شود؟ سفارش‌های قبلی حفظ می‌شوند.","Disable this plan? Existing orders remain intact.")))return;
    setBusy(true);setError("");setOk("");
    try{await resellerApi.deletePlan(id);setOk(pick("پلن غیرفعال شد.","Plan disabled."));await load();}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  return <PortalShell type="reseller" active="/reseller/sales"><div className="page reseller-parity-page">
    <div className="page-head"><div><h1>{pick("پلن‌های ربات","Bot Plans")}</h1><small>{pick("این پلن‌ها مستقل از پلن‌های پنل اصلی هستند. تعداد فروش نامحدود است و فقط مصرف واقعی کاربران از حجم نمایندگی کم می‌شود.","These plans are owned by this reseller. Sales are unlimited; only real usage drains the reseller traffic pool.")}</small></div><div className="action-row"><button type="button" className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button><button type="button" className="primary" onClick={startCreate}>＋ {pick("پلن جدید","New plan")}</button></div></div>
    {error&&<div className="runtime-error" role="alert">{error}</div>}{ok&&<div className="runtime-success" role="status">{ok}</div>}
    <div className="stats"><Stat label={pick("کل پلن‌ها","Total plans")} value={String(rows.length)}/><Stat label={pick("پلن فعال","Active plans")} value={String(active)}/><Stat label={pick("مدل فروش","Sales model")} value={pick("نامحدود","Unlimited")}/><Stat label={pick("میانگین قیمت","Average price")} value={money(avg)}/></div>

    {open&&<div ref={editorRef} className="owned-plan-editor-anchor"><Card className="runtime-editor owned-plan-editor"><div className="card-head"><div><b>{editing?pick("ویرایش پلن","Edit plan"):pick("ساخت پلن ربات","Create bot plan")}</b><small>{editing?pick(`در حال ویرایش پلن #${editing}. پس از ذخیره، همان پلن بروزرسانی می‌شود.`,`Editing plan #${editing}. Saving updates this exact plan.`):pick("حجم اینجا سقف هر اکانت است؛ هنگام فروش از حجم نماینده رزرو نمی‌شود.","This traffic is the account quota; it is not reserved from the reseller pool at sale time.")}</small></div>{editing&&<Badge tone="violet">#{editing}</Badge>}</div><form onSubmit={submit}>
      <div className="setting-grid">
        <label className="field"><span>{pick("عنوان پلن","Plan title")}</span><input ref={titleRef} required minLength={2} maxLength={120} value={form.title} onChange={e=>setForm(v=>({...v,title:e.target.value}))}/></label>
        <label className="field"><span>{pick("حجم هر اکانت (GB)","Account traffic (GB)")}</span><input type="number" min={1} max={100000} value={form.traffic_gb} onChange={e=>setForm(v=>({...v,traffic_gb:Number(e.target.value)}))}/></label>
        <label className="field"><span>{pick("مدت (روز)","Duration (days)")}</span><input type="number" min={1} max={3650} value={form.duration_days} onChange={e=>setForm(v=>({...v,duration_days:Number(e.target.value)}))}/></label>
        <label className="field"><span>{pick("محدودیت دستگاه","Device limit")}</span><input type="number" min={1} max={100} value={form.device_limit} onChange={e=>setForm(v=>({...v,device_limit:Number(e.target.value)}))}/></label>
        <label className="field"><span>{pick("قیمت فروش ربات (تومان)","Bot sale price")}</span><input type="number" min={0} step={1} value={form.sell_price_toman} onChange={e=>setForm(v=>({...v,sell_price_toman:Number(e.target.value)}))}/></label>
        <label className="field"><span>{pick("ترتیب نمایش","Sort order")}</span><input type="number" min={0} value={form.sort_order} onChange={e=>setForm(v=>({...v,sort_order:Number(e.target.value)}))}/></label>
      </div>
      <div className="card-head"><b>{pick("پروتکل‌ها","Protocols")}</b></div><div className="setting-grid">{protocolRows.map(([key,label])=><label className="field" key={String(key)}><span>{label}</span><input type="checkbox" checked={Boolean(form[key])} onChange={e=>setForm(v=>({...v,[key]:e.target.checked}))}/></label>)}<label className="field"><span>{pick("فعال","Active")}</span><input type="checkbox" checked={form.is_active} onChange={e=>setForm(v=>({...v,is_active:e.target.checked}))}/></label></div>
      <div className="action-row"><button type="button" className="ghost" onClick={closeEditor}>{pick("انصراف","Cancel")}</button><button type="submit" className="primary" disabled={busy}>{busy?"…":editing?pick("ذخیره تغییرات","Save changes"):pick("ذخیره پلن","Save plan")}</button></div>
    </form></Card></div>}

    <Card><div className="card-head"><div><b>{pick("پلن‌های اختصاصی نمایندگی","Reseller-owned plans")}</b><small>{pick("ربات فقط پلن‌های فعال همین لیست را به مشتری نمایش می‌دهد.","The bot only shows active plans from this list.")}</small></div><Badge tone="violet">{rows.length}</Badge></div>
      <div className="table"><table><thead><tr><th>{pick("پلن","Plan")}</th><th>{pick("حجم / مدت","Traffic / Duration")}</th><th>{pick("پروتکل‌ها","Protocols")}</th><th>{pick("قیمت","Price")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{rows.map((row,index)=>{const id=Number(row.id||0);const protocols=protocolRows.filter(([key])=>Boolean(row[String(key)])).map(([,label])=>label);return <tr key={id||index}><td><b>{str(row,"title")||str(row,"name")||`#${id}`}</b><small>#{id}</small></td><td>{num(row,"traffic_gb")} GB · {num(row,"duration_days")} {pick("روز","days")}</td><td>{protocols.join(" · ")||"—"}</td><td>{money(num(row,"sell_price_toman"))}</td><td><Badge tone={Boolean(row.is_active)?"ok":"bad"}>{Boolean(row.is_active)?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td><td><div className="row-actions"><button type="button" className="mini-btn" onClick={()=>startEdit(row)}>{pick("ویرایش","Edit")}</button>{Boolean(row.is_active)&&<button type="button" className="mini-btn danger" disabled={busy} onClick={()=>void disable(row)}>{pick("غیرفعال","Disable")}</button>}</div></td></tr>})}</tbody></table></div>
      {!rows.length&&<div className="runtime-empty">{pick("هنوز پلنی نساخته‌اید. اولین پلن ربات را ایجاد کنید.","No plans yet. Create your first bot plan.")}</div>}
    </Card>
  </div></PortalShell>;
}
