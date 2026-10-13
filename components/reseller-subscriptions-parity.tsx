"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {resellerApi,ResellerRow} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const str=(row:ResellerRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:ResellerRow,...keys:string[])=>{const value=Number(str(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;};
const rowsOf=(value:unknown,...keys:string[])=>{if(Array.isArray(value))return value.filter(x=>x&&typeof x==="object") as ResellerRow[];if(value&&typeof value==="object"){const row=value as ResellerRow;for(const key of keys){const v=row[key];if(Array.isArray(v))return v.filter(x=>x&&typeof x==="object") as ResellerRow[];}}return [] as ResellerRow[];};
const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const gb=(bytes:number)=>Number(bytes||0)/1024/1024/1024;
const gbText=(bytes:number)=>`${gb(bytes).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const statusTone=(status:string):"ok"|"warn"|"bad"|"violet"=>status==="active"?"ok":["expired","canceled","failed"].includes(status)?"bad":"warn";
const idempotency=(prefix:string)=>`${prefix}-${Date.now()}-${Math.random().toString(36).slice(2,10)}`;
const enabledProtocols=(plan:ResellerRow)=>Object.entries({cisco:"enable_cisco",openvpn:"enable_openvpn",wireguard:"enable_wireguard",l2tp:"enable_l2tp",v2ray:"enable_v2ray"}).filter(([,field])=>Boolean(plan[field])).map(([name])=>name);
const absoluteLink=(value:string)=>{if(typeof window==="undefined")return value;try{return new URL(value,window.location.origin).toString();}catch{return value;}};

type ExpiryUnit="days"|"months"|"years";
const expiryPreset=(value:unknown):{value:number;unit:ExpiryUnit}=>{
  const expires=new Date(String(value||""));
  if(Number.isNaN(expires.getTime()))return {value:30,unit:"days"};
  const days=Math.max(1,Math.ceil((expires.getTime()-Date.now())/86_400_000));
  if(days>=365&&days%365===0)return {value:Math.max(1,Math.round(days/365)),unit:"years"};
  if(days>=30&&days%30===0)return {value:Math.max(1,Math.round(days/30)),unit:"months"};
  return {value:days,unit:"days"};
};
const expiryIso=(value:number,unit:ExpiryUnit)=>{
  const amount=Math.max(1,Math.trunc(Number(value)||0));
  const result=new Date();
  if(unit==="years")result.setFullYear(result.getFullYear()+amount);
  else if(unit==="months")result.setMonth(result.getMonth()+amount);
  else result.setDate(result.getDate()+amount);
  return result.toISOString();
};

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Empty({children}:{children:React.ReactNode}){return <div className="runtime-empty">{children}</div>;}

export function ResellerSubscriptionsParityRuntime(){
  const {pick}=useI18n();
  const [subs,setSubs]=useState<ResellerRow[]>([]);
  const [plans,setPlans]=useState<ResellerRow[]>([]);
  const [serverOptions,setServerOptions]=useState<ResellerRow>({});
  const [q,setQ]=useState("");
  const [statusFilter,setStatusFilter]=useState("all");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [sellOpen,setSellOpen]=useState(false);
  const [editRow,setEditRow]=useState<ResellerRow|null>(null);
  const [extendRow,setExtendRow]=useState<ResellerRow|null>(null);
  const [connectionRow,setConnectionRow]=useState<ResellerRow|null>(null);
  const [connection,setConnection]=useState<ResellerRow|null>(null);
  const [copied,setCopied]=useState("");
  const [saleKey,setSaleKey]=useState(()=>idempotency("sale"));
  const [extendKey,setExtendKey]=useState(()=>idempotency("extend"));

  const [sell,setSell]=useState({traffic_gb:50,duration_days:30,node_ids:[] as number[],username:"",password:""});
  const [edit,setEdit]=useState({traffic_gb:0,expiry_value:30,expiry_unit:"days" as ExpiryUnit,sell_price_toman:0,account_username:"",account_password:""});
  const [extend,setExtend]=useState({add_traffic_gb:0,add_days:30,charge_toman:0,reset_usage:false});

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([
      resellerApi.subscriptions(),
      resellerApi.plans(),
      resellerApi.serverOptions()
    ]);
    if(result[0].status==="fulfilled")setSubs(result[0].value);
    if(result[1].status==="fulfilled")setPlans(result[1].value);
    if(result[2].status==="fulfilled")setServerOptions(result[2].value);
    const failed=result.find(x=>x.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  const backingPlan=useMemo(()=>plans.find(plan=>plan.is_active!==false)||plans[0]||null,[plans]);
  const nodes=rowsOf(serverOptions,"nodes","servers","items");
  const statuses=useMemo(()=>Array.from(new Set(subs.map(row=>str(row,"status")).filter(Boolean))),[subs]);
  const filtered=useMemo(()=>subs.filter(row=>{
    if(statusFilter!=="all"&&str(row,"status")!==statusFilter)return false;
    const needle=q.trim().toLowerCase();
    if(!needle)return true;
    return [row.id,row.customer_name,row.customer_email,row.customer_phone,row.account_username,row.plan_name,row.status].some(value=>String(value??"").toLowerCase().includes(needle));
  }),[subs,q,statusFilter]);

  const act=async(label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{await fn();setOk(label);await load();}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));await load();}
    finally{setBusy(false);}
  };

  const copy=async(key:string,value:string)=>{
    try{await navigator.clipboard.writeText(value);setCopied(key);window.setTimeout(()=>setCopied(""),1300);}
    catch{setError(pick("کپی انجام نشد.","Copy failed."));}
  };

  const openSale=()=>{
    setSaleKey(idempotency("sale"));
    setSell({traffic_gb:50,duration_days:30,node_ids:[],username:"",password:""});
    setSellOpen(true);
  };

  const submitSale=(event:FormEvent)=>{
    event.preventDefault();
    if(!backingPlan||sell.traffic_gb<=0||sell.duration_days<=0)return;
    const planId=Number(backingPlan.backing_plan_id||backingPlan.plan_id||backingPlan.id||0);
    if(!planId){setError(pick("مجوز داخلی ساخت اشتراک آماده نیست.","The internal subscription authorization is not ready."));return;}
    const protocols=enabledProtocols(backingPlan);
    void act(pick("اشتراک ساخته و روی سرورها فعال شد","Subscription created and provisioned"),async()=>{
      const result=await resellerApi.sellSubscription({
        user_id:null,
        plan_id:planId,
        traffic_gb:Math.max(1,Number(backingPlan.traffic_gb||1)),
        duration_days:Math.max(1,Number(backingPlan.duration_days||1)),
        node_ids:sell.node_ids,
        protocols,
        sell_price_toman:Number(backingPlan.sell_price_toman||0),
        username:sell.username.trim()||null,
        password:sell.password.trim()||null,
        idempotency_key:saleKey
      });
      const subscriptionId=Number(result.subscription_id||0);
      if(!subscriptionId)throw new Error(pick("شناسه اشتراک ساخته‌شده دریافت نشد.","Created subscription id was not returned."));
      await resellerApi.extendSubscription(subscriptionId,{
        add_traffic_gb:Number(sell.traffic_gb),
        add_days:Number(sell.duration_days),
        charge_toman:0,
        reset_usage:true,
        idempotency_key:idempotency(`manual-${subscriptionId}`)
      });
      await resellerApi.provisionSubscription(subscriptionId);
      setSellOpen(false);
      setSell({traffic_gb:50,duration_days:30,node_ids:[],username:"",password:""});
      setSaleKey(idempotency("sale"));
    });
  };

  const openEdit=(row:ResellerRow)=>{
    const expiry=expiryPreset(row.expires_at);
    setEditRow(row);
    setEdit({
      traffic_gb:Number(gb(num(row,"traffic_limit_bytes")).toFixed(2)),
      expiry_value:expiry.value,
      expiry_unit:expiry.unit,
      sell_price_toman:num(row,"sell_price_toman"),
      account_username:str(row,"account_username"),
      account_password:""
    });
  };

  const submitEdit=(event:FormEvent)=>{
    event.preventDefault();
    if(!editRow)return;
    const id=Number(editRow.id||editRow.subscription_id||0);
    if(!id||edit.expiry_value<1)return;
    void act(pick("اشتراک ویرایش شد","Subscription updated"),async()=>{
      await resellerApi.editSubscription(id,{
        traffic_gb:edit.traffic_gb,
        expires_at:expiryIso(edit.expiry_value,edit.expiry_unit),
        sell_price_toman:edit.sell_price_toman,
        account_username:edit.account_username.trim()||null,
        account_password:edit.account_password.trim()||null
      });
      setEditRow(null);
    });
  };

  const openExtend=(row:ResellerRow)=>{
    setExtendRow(row);
    setExtend({add_traffic_gb:0,add_days:30,charge_toman:0,reset_usage:false});
    setExtendKey(idempotency(`extend-${Number(row.id||row.subscription_id||0)}`));
  };

  const submitExtend=(event:FormEvent)=>{
    event.preventDefault();
    if(!extendRow)return;
    const id=Number(extendRow.id||extendRow.subscription_id||0);
    if(!id)return;
    if(extend.reset_usage&&(!extend.add_days||!extend.add_traffic_gb)){
      setError(pick("برای شروع دوره جدید، حجم و مدت را هر دو وارد کنید.","Enter both traffic and duration for a new billing cycle."));
      return;
    }
    if(!extend.reset_usage&&!extend.add_days&&!extend.add_traffic_gb)return;
    void act(extend.reset_usage?pick("دوره جدید اشتراک شروع شد","New subscription cycle started"):pick("اشتراک تمدید شد","Subscription extended"),async()=>{
      await resellerApi.extendSubscription(id,{...extend,idempotency_key:extendKey});
      setExtendRow(null);
      setExtendKey(idempotency("extend"));
    });
  };

  const openConnection=async(row:ResellerRow)=>{
    const id=Number(row.id||row.subscription_id||0);if(!id)return;
    setConnectionRow(row);setConnection(null);setBusy(true);setError("");
    try{setConnection(await resellerApi.connectionInfo(id));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));setConnectionRow(null);}
    finally{setBusy(false);}
  };

  const activeCount=subs.filter(row=>str(row,"status")==="active").length;
  const totalTraffic=subs.reduce((sum,row)=>sum+num(row,"traffic_limit_bytes"),0);
  const totalUsed=subs.reduce((sum,row)=>sum+num(row,"traffic_used_bytes"),0);

  return <PortalShell type="reseller" active="/reseller/subscriptions">
    <div className="page reseller-parity-page reseller-subscriptions-parity">
      <div className="page-head">
        <div><h1>{pick("اشتراک‌ها","Subscriptions")}</h1><small>{pick("فروش و مدیریت کامل سرویس‌های مشتریان نمایندگی","Sell and fully manage reseller customer services")}</small></div>
        <div className="action-row"><button className="ghost" onClick={()=>void load()} disabled={busy}>{pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={openSale}>＋ {pick("ساخت اشتراک","Create subscription")}</button></div>
      </div>
      <Notice error={error} ok={ok}/>

      <div className="stats">
        <Stat label={pick("کل اشتراک‌ها","Total subscriptions")} value={String(subs.length)}/>
        <Stat label={pick("فعال","Active")} value={String(activeCount)}/>
        <Stat label={pick("حجم کل","Total traffic")} value={gbText(totalTraffic)}/>
        <Stat label={pick("مصرف کل","Total usage")} value={gbText(totalUsed)}/>
      </div>

      <Card>
        <div className="runtime-toolbar reseller-order-toolbar">
          <label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("جستجو با نام، موبایل، نام کاربری یا شناسه...","Search name, phone, username or ID...")}/></label>
          <select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="all">{pick("همه وضعیت‌ها","All statuses")}</option>{statuses.map(status=><option key={status} value={status}>{status}</option>)}</select>
          <Badge tone="violet">{filtered.length}</Badge>
        </div>
        <div className="table reseller-sub-table"><table><thead><tr><th>ID</th><th>{pick("مشتری","Customer")}</th><th>{pick("اکانت","Account")}</th><th>{pick("پلن","Plan")}</th><th>{pick("مصرف","Usage")}</th><th>{pick("انقضا","Expires")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map((row,index)=>{const id=Number(row.id||row.subscription_id||0),status=str(row,"status"),limit=num(row,"traffic_limit_bytes"),used=num(row,"traffic_used_bytes"),usage=limit?Math.min(100,Math.round(used/limit*100)):0;return <tr key={id||index}><td>#{id}</td><td><b>{str(row,"customer_name")||`#${str(row,"customer_user_id")}`}</b><small dir="ltr">{str(row,"customer_phone")||str(row,"customer_email")||"—"}</small></td><td><code dir="ltr">{str(row,"account_username")||"—"}</code></td><td><b>{str(row,"plan_name")||`#${str(row,"plan_id")}`}</b><small>{money(num(row,"sell_price_toman"))}</small></td><td><div className="reseller-usage-cell"><span>{gbText(used)} / {gbText(limit)}</span><div className="progress"><i style={{width:`${usage}%`}}/></div></div></td><td>{dateText(row.expires_at)}</td><td><Badge tone={statusTone(status)}>{status||"—"}</Badge></td><td><div className="row-actions"><button className="mini-btn" onClick={()=>void openConnection(row)} disabled={busy}>{pick("اتصال","Connection")}</button><button className="mini-btn" onClick={()=>openEdit(row)}>{pick("ویرایش","Edit")}</button><button className="mini-btn" onClick={()=>openExtend(row)}>{pick("تمدید","Extend")}</button><button className="mini-btn" disabled={busy} onClick={()=>void act(status==="active"?pick("اشتراک تعلیق شد","Subscription suspended"):pick("اشتراک فعال شد","Subscription activated"),()=>resellerApi.toggleSubscription(id))}>{status==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button className="mini-btn danger" disabled={busy} onClick={()=>{if(window.confirm(pick("این اشتراک حذف شود؟ دسترسی آن از سرورها نیز لغو می‌شود.","Delete this subscription and revoke server access?")))void act(pick("اشتراک حذف شد","Subscription deleted"),()=>resellerApi.deleteSubscription(id));}}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>
        {!filtered.length&&<Empty>{pick("اشتراکی با این فیلتر پیدا نشد.","No subscription matches this filter.")}</Empty>}
      </Card>

      {sellOpen&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setSellOpen(false)}/><form className="runtime-modal-card reseller-sub-modal" onSubmit={submitSale}><div className="card-head"><div><b>{pick("ساخت اشتراک جدید","Create new subscription")}</b><small>{pick("برای ساخت دستی مشتری و پلن لازم نیست؛ حجم و مدت را مشخص کنید و سرویس مستقیم ساخته می‌شود.","Manual creation does not require a customer or plan selection; set traffic and duration and the service will be created directly.")}</small></div><button className="icon-button" type="button" onClick={()=>setSellOpen(false)}>×</button></div><div className="setting-grid"><label className="field"><span>{pick("حجم اشتراک GB","Subscription traffic GB")}</span><input type="number" min={0.01} step="0.01" required value={sell.traffic_gb} onChange={e=>setSell(s=>({...s,traffic_gb:Number(e.target.value)}))}/></label><label className="field"><span>{pick("مدت اعتبار (روز)","Validity (days)")}</span><input type="number" min={1} max={3650} step={1} required value={sell.duration_days} onChange={e=>setSell(s=>({...s,duration_days:Number(e.target.value)}))}/></label><label className="field"><span>{pick("نام کاربری دلخواه (اختیاری)","Custom username (optional)")}</span><input dir="ltr" value={sell.username} onChange={e=>setSell(s=>({...s,username:e.target.value}))}/></label><label className="field"><span>{pick("رمز دلخواه (اختیاری)","Custom password (optional)")}</span><input dir="ltr" value={sell.password} onChange={e=>setSell(s=>({...s,password:e.target.value}))}/></label></div>{!backingPlan&&<div className="runtime-error">{pick("برای ساخت اشتراک، حداقل یک مجوز فعال نمایندگی باید وجود داشته باشد.","At least one active reseller authorization is required to create a subscription.")}</div>}<div className="reseller-volume-note"><b>{pick("ساخت دستی نماینده","Manual reseller creation")}</b><small>{pick("تعداد ساخت نامحدود است و هیچ حجمی هنگام ساخت رزرو نمی‌شود؛ فقط مصرف واقعی کاربران از حجم نماینده کم می‌شود.","Creation count is unlimited and no traffic is reserved at creation; only real customer usage drains the reseller pool.")}</small></div>{nodes.length>0&&<div className="runtime-choice-section"><b>{pick("سرور خروجی مقصد","Exit destination")}</b><small>{pick("اگر سروری انتخاب نشود، بهترین سرور خروجی سالم به‌صورت خودکار انتخاب می‌شود.","Leave empty to select the best healthy exit automatically.")}</small><div className="protocol-toggle-grid">{nodes.map((node,index)=>{const id=Number(node.id||0),checked=sell.node_ids.includes(id);return <label className="toggle module-toggle" key={id||index}><span>{str(node,"name")||`#${id}`}{Boolean(node.is_mother)?` · ${pick("مادر","Mother")}`:""}</span><input type="checkbox" checked={checked} onChange={e=>setSell(s=>({...s,node_ids:e.target.checked?[...s.node_ids,id]:s.node_ids.filter(x=>x!==id)}))}/><i/></label>})}</div></div>}<div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setSellOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||!backingPlan||sell.traffic_gb<=0||sell.duration_days<=0}>{busy?"…":pick("ساخت و فعال‌سازی","Create & provision")}</button></div></form></div>}

      {editRow&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setEditRow(null)}/><form className="runtime-modal-card reseller-sub-modal" onSubmit={submitEdit}><div className="card-head"><div><b>{pick("ویرایش اشتراک","Edit subscription")} #{str(editRow,"id")}</b><small>{str(editRow,"customer_name")}</small></div><button className="icon-button" type="button" onClick={()=>setEditRow(null)}>×</button></div><div className="setting-grid"><label className="field"><span>{pick("حجم کل GB","Total traffic GB")}</span><input type="number" min={0.01} step="0.01" value={edit.traffic_gb} onChange={e=>setEdit(v=>({...v,traffic_gb:Number(e.target.value)}))}/></label><label className="field"><span>{pick("مدت اعتبار از امروز","Validity from today")}</span><div className="reseller-expiry-duration"><input type="number" min={1} step={1} required value={edit.expiry_value} onChange={e=>setEdit(v=>({...v,expiry_value:Number(e.target.value)}))}/><select value={edit.expiry_unit} onChange={e=>setEdit(v=>({...v,expiry_unit:e.target.value as ExpiryUnit}))}><option value="days">{pick("روز","Days")}</option><option value="months">{pick("ماه","Months")}</option><option value="years">{pick("سال","Years")}</option></select></div></label><label className="field"><span>{pick("قیمت فروش","Sell price")}</span><input type="number" min={0} value={edit.sell_price_toman} onChange={e=>setEdit(v=>({...v,sell_price_toman:Number(e.target.value)}))}/></label><label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={edit.account_username} onChange={e=>setEdit(v=>({...v,account_username:e.target.value}))}/></label><label className="field"><span>{pick("رمز جدید (اختیاری)","New password (optional)")}</span><input dir="ltr" value={edit.account_password} onChange={e=>setEdit(v=>({...v,account_password:e.target.value}))} placeholder={pick("خالی = بدون تغییر","Empty = keep current")}/></label></div><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setEditRow(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||edit.expiry_value<1}>{pick("ذخیره تغییرات","Save changes")}</button></div></form></div>}

      {extendRow&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setExtendRow(null)}/><form className="runtime-modal-card reseller-sub-modal" onSubmit={submitExtend}><div className="card-head"><div><b>{pick("تمدید اشتراک","Extend subscription")} #{str(extendRow,"id")}</b><small>{extend.reset_usage?pick("دوره جدید: مصرف فعلی صفر و سهمیه/تاریخ دوره جایگزین می‌شود.","New cycle: current usage resets and the cycle quota/date are replaced."):pick("تمدید افزایشی: حجم یا روز به اشتراک فعلی اضافه می‌شود.","Additive extension: traffic or days are added to the existing subscription.")}</small></div><button className="icon-button" type="button" onClick={()=>setExtendRow(null)}>×</button></div><label className="toggle module-toggle reseller-cycle-toggle"><span>{pick("شروع دوره جدید و صفر شدن مصرف","Start a new cycle and reset usage")}</span><input type="checkbox" checked={extend.reset_usage} onChange={e=>setExtend(v=>({...v,reset_usage:e.target.checked}))}/><i/></label><div className="setting-grid"><label className="field"><span>{extend.reset_usage?pick("حجم دوره جدید GB","New-cycle traffic GB"):pick("حجم اضافه GB","Additional traffic GB")}</span><input type="number" min={0} step="0.01" value={extend.add_traffic_gb} onChange={e=>setExtend(v=>({...v,add_traffic_gb:Number(e.target.value)}))}/></label><label className="field"><span>{extend.reset_usage?pick("مدت دوره جدید","New-cycle days"):pick("روز اضافه","Additional days")}</span><input type="number" min={0} value={extend.add_days} onChange={e=>setExtend(v=>({...v,add_days:Number(e.target.value)}))}/></label></div><div className="reseller-volume-note"><b>{pick("مدل حجمی نمایندگی","Volume-only reseller model")}</b><small>{pick("ساخت یا تمدید اشتراک از موجودی حجم نماینده رزرو نمی‌کند؛ موجودی فقط با مصرف واقعی کاربران کم می‌شود.","Creating or extending a subscription does not reserve reseller traffic; the pool is reduced only by real customer usage.")}</small></div><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setExtendRow(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||(extend.reset_usage?(!extend.add_days||!extend.add_traffic_gb):(!extend.add_days&&!extend.add_traffic_gb))}>{extend.reset_usage?pick("شروع دوره جدید","Start new cycle"):pick("ثبت تمدید","Apply extension")}</button></div></form></div>}

      {connectionRow&&<div className="runtime-modal reseller-connection-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>setConnectionRow(null)}/><div className="runtime-modal-card reseller-connection-card"><div className="card-head"><div><b>{pick("تحویل اتصال","Connection delivery")} #{str(connectionRow,"id")}</b><small>{pick("برای مشتری فقط لینک اشتراک یا QR را ارسال کنید.","Send only the subscription link or QR to the customer.")}</small></div><button className="icon-button" type="button" onClick={()=>setConnectionRow(null)}>×</button></div>{!connection?<div className="runtime-loading">{pick("در حال دریافت لینک اشتراک...","Loading subscription link...")}</div>:<ConnectionDetails info={connection} copied={copied} copy={copy} pick={pick}/>}<div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setConnectionRow(null)}>{pick("بستن","Close")}</button></div></div></div>}
    </div>
  </PortalShell>;
}

function ConnectionDetails({info,copied,copy,pick}:{info:ResellerRow;copied:string;copy:(key:string,value:string)=>Promise<void>;pick:(fa:string,en:string)=>string}){
  const link=str(info,"subscription_link");
  const publicLink=link?absoluteLink(link):"";
  const qrLink=publicLink?`${publicLink.replace(/\/$/,"")}/qr`:"";

  if(!publicLink)return <Empty>{pick("لینک اشتراک برای این سرویس آماده نیست.","The subscription link is not ready for this service.")}</Empty>;

  return <div className="reseller-connection-content">
    <div className="reseller-secret-grid">
      <div className="wide"><span>{pick("لینک ساب‌لینک","Subscription link")}</span><code dir="ltr">{publicLink}</code><button type="button" className="mini-btn" onClick={()=>void copy("link",publicLink)}>{copied==="link"?"✓":pick("کپی","Copy")}</button><button type="button" className="mini-btn" onClick={()=>window.open(publicLink,"_blank","noopener,noreferrer")}>{pick("باز کردن","Open")}</button></div>
    </div>

    {qrLink&&<div className="reseller-public-delivery"><div><b>{pick("QR Code اشتراک","Subscription QR Code")}</b><small>{pick("مشتری می‌تواند این QR را اسکن کند و صفحه اتصال را باز کند.","The customer can scan this QR to open the connection page.")}</small></div><img src={qrLink} alt={pick("QR لینک اشتراک","Subscription link QR")}/></div>}
  </div>;
}
