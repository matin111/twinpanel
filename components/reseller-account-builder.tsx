"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Stat} from "./ui";
import {PortalShell} from "./portal-shells";
import {resellerApi,ResellerRow} from "../lib/reseller-runtime-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const str=(row:ResellerRow,...keys:string[])=>{for(const key of keys){const value=row?.[key];if(value!==undefined&&value!==null)return String(value);}return "";};
const num=(row:ResellerRow,...keys:string[])=>{const value=Number(str(row,...keys).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;};
const gbText=(bytes:number)=>`${(Number(bytes||0)/GB).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const statusTone=(status:string):"ok"|"warn"|"bad"|"violet"=>status==="active"?"ok":["expired","canceled","failed","suspended"].includes(status)?"bad":"warn";
const idempotency=()=>`create-${Date.now()}-${Math.random().toString(36).slice(2,10)}`;
const rowsOf=(value:ResellerRow,...keys:string[])=>{for(const key of keys){const item=value[key];if(Array.isArray(item))return item.filter(x=>x&&typeof x==="object") as ResellerRow[];}return [] as ResellerRow[];};

export function ResellerAccountBuilderRuntime(){
  const {pick}=useI18n();
  const [subs,setSubs]=useState<ResellerRow[]>([]);
  const [plans,setPlans]=useState<ResellerRow[]>([]);
  const [traffic,setTraffic]=useState<ResellerRow>({});
  const [serverOptions,setServerOptions]=useState<ResellerRow>({});
  const [q,setQ]=useState("");
  const [open,setOpen]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [form,setForm]=useState({plan_id:0,node_ids:[] as number[],username:"",password:""});
  const [connection,setConnection]=useState<ResellerRow|null>(null);
  const [connectionRow,setConnectionRow]=useState<ResellerRow|null>(null);

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([resellerApi.subscriptions(),resellerApi.plans(),resellerApi.traffic(),resellerApi.serverOptions()]);
    if(result[0].status==="fulfilled")setSubs(result[0].value);
    if(result[1].status==="fulfilled")setPlans(result[1].value);
    if(result[2].status==="fulfilled")setTraffic(result[2].value);
    if(result[3].status==="fulfilled")setServerOptions(result[3].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };
  useEffect(()=>{void load();},[]);

  const activePlans=useMemo(()=>plans.filter(row=>Boolean(row.is_active)),[plans]);
  const selectedPlan=useMemo(()=>activePlans.find(row=>Number(row.id||0)===form.plan_id)||null,[activePlans,form.plan_id]);
  const nodes=rowsOf(serverOptions,"nodes","servers","items");
  const ownedTitle=(row:ResellerRow)=>{const backing=Number(row.plan_id||0);const match=plans.find(plan=>Number(plan.backing_plan_id||plan.plan_id||0)===backing);return match?str(match,"title","name"):str(row,"plan_name")||`#${backing}`;};
  const filtered=useMemo(()=>{const needle=q.trim().toLowerCase();if(!needle)return subs;return subs.filter(row=>[row.id,row.account_username,ownedTitle(row),row.status].some(value=>String(value??"").toLowerCase().includes(needle)));},[subs,q,plans]);
  const activeCount=subs.filter(row=>str(row,"status")==="active").length;
  const poolAvailableBytes=(()=>{const direct=num(traffic,"available_traffic_bytes");if(direct)return direct;const gb=num(traffic,"available_traffic_gb");if(gb)return gb*GB;return num(traffic,"traffic_balance_bytes")+num(traffic,"traffic_credit_bytes");})();

  const openCreate=()=>{setForm({plan_id:Number(activePlans[0]?.id||0),node_ids:[],username:"",password:""});setError("");setOk("");setOpen(true);};
  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    if(!form.plan_id){setError(pick("ابتدا یک پلن فعال بسازید یا انتخاب کنید.","Create or select an active plan first."));return;}
    setBusy(true);setError("");setOk("");
    try{
      const result=await resellerApi.createSubscription({plan_id:form.plan_id,node_ids:form.node_ids,username:form.username.trim()||null,password:form.password.trim()||null,idempotency_key:idempotency()});
      const id=Number(result.subscription_id||0);
      if(id)await resellerApi.provisionSubscription(id);
      setOk(pick("اشتراک ساخته و روی سرورها فعال شد.","Subscription created and provisioned."));
      setOpen(false);setForm({plan_id:0,node_ids:[],username:"",password:""});await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const toggleNode=(id:number)=>setForm(value=>({...value,node_ids:value.node_ids.includes(id)?value.node_ids.filter(x=>x!==id):[...value.node_ids,id]}));

  const openConnection=async(row:ResellerRow)=>{
    const id=Number(row.id||row.subscription_id||0);if(!id)return;
    setBusy(true);setError("");setConnectionRow(row);setConnection(null);
    try{setConnection(await resellerApi.connectionInfo(id));}
    catch(reason){setConnectionRow(null);setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const toggle=async(row:ResellerRow)=>{const id=Number(row.id||0);if(!id)return;setBusy(true);setError("");try{await resellerApi.toggleSubscription(id);await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const remove=async(row:ResellerRow)=>{const id=Number(row.id||0);if(!id||!window.confirm(pick("این اشتراک حذف شود؟ دسترسی سرورها هم لغو می‌شود.","Delete this subscription and revoke server access?")))return;setBusy(true);setError("");try{await resellerApi.deleteSubscription(id);await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};

  return <PortalShell type="reseller" active="/reseller/subscriptions"><div className="page reseller-parity-page reseller-subscriptions-parity">
    <div className="page-head"><div><h1>{pick("ساخت اشتراک","Create Subscription")}</h1><small>{pick("تعداد ساخت اکانت نامحدود است. هنگام ساخت هیچ حجمی رزرو نمی‌شود؛ مصرف واقعی همه اکانت‌ها از حجم مشترک نمایندگی کم می‌شود.","Account creation is unlimited. No traffic is reserved at creation; real usage from every account drains the shared reseller pool.")}</small></div><div className="action-row"><button className="ghost" onClick={()=>void load()} disabled={busy}>{pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={openCreate} disabled={!activePlans.length}>＋ {pick("ساخت اشتراک","Create subscription")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats"><Stat label={pick("کل اشتراک‌ها","Total subscriptions")} value={String(subs.length)}/><Stat label={pick("اشتراک فعال","Active subscriptions")} value={String(activeCount)}/><Stat label={pick("حجم قابل استفاده نمایندگی","Available reseller traffic")} value={gbText(poolAvailableBytes)}/><Stat label={pick("محدودیت ساخت","Creation limit")} value={pick("نامحدود","Unlimited")}/></div>

    {poolAvailableBytes<=0&&<div className="runtime-error">{pick("حجم نمایندگی تمام شده است. ساخت اکانت همچنان ممکن است اما همه اشتراک‌های این نمایندگی تا شارژ مجدد حجم قطع می‌مانند.","The reseller traffic pool is exhausted. Accounts can still be created, but all reseller subscriptions stay suspended until the pool is recharged.")}</div>}

    {open&&<Card className="runtime-editor"><div className="card-head"><div><b>{pick("ساخت اشتراک جدید","Create new subscription")}</b><small>{selectedPlan?`${str(selectedPlan,"title","name")} · ${num(selectedPlan,"traffic_gb")} GB · ${num(selectedPlan,"duration_days")} ${pick("روز","days")}`:pick("پلن را انتخاب کنید","Select a plan")}</small></div></div><form onSubmit={submit}>
      <div className="setting-grid">
        <label className="field"><span>{pick("پلن نمایندگی","Reseller plan")}</span><select required value={form.plan_id} onChange={e=>setForm(v=>({...v,plan_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب پلن","Select plan")}</option>{activePlans.map(row=><option key={Number(row.id)} value={Number(row.id)}>{str(row,"title","name")} — {num(row,"traffic_gb")}GB / {num(row,"duration_days")} {pick("روز","days")}</option>)}</select></label>
        <label className="field"><span>{pick("نام کاربری اختیاری","Optional username")}</span><input dir="ltr" value={form.username} onChange={e=>setForm(v=>({...v,username:e.target.value}))} placeholder={pick("خالی = ساخت خودکار","Empty = auto-generate")}/></label>
        <label className="field"><span>{pick("رمز عبور اختیاری","Optional password")}</span><input dir="ltr" value={form.password} onChange={e=>setForm(v=>({...v,password:e.target.value}))} placeholder={pick("خالی = ساخت خودکار","Empty = auto-generate")}/></label>
      </div>
      {!!nodes.length&&<><div className="card-head"><div><b>{pick("سرور خروجی","Exit server")}</b><small>{pick("اگر چیزی انتخاب نکنید سیستم به‌صورت خودکار سرور سالم را انتخاب می‌کند.","Leave empty for automatic healthy server selection.")}</small></div></div><div className="setting-grid">{nodes.map(row=>{const id=Number(row.id||0);return <label className="field" key={id}><span>{str(row,"name")||`#${id}`}</span><input type="checkbox" checked={form.node_ids.includes(id)} onChange={()=>toggleNode(id)}/></label>})}</div></>}
      <div className="action-row"><button type="button" className="ghost" onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy}>{busy?"…":pick("ساخت و فعال‌سازی","Create & activate")}</button></div>
    </form></Card>}

    <Card><div className="runtime-toolbar"><label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("جستجو با نام کاربری، پلن یا شناسه...","Search username, plan or ID...")}/></label><Badge tone="violet">{filtered.length}</Badge></div>
      <div className="table"><table><thead><tr><th>ID</th><th>{pick("اکانت","Account")}</th><th>{pick("پلن","Plan")}</th><th>{pick("مصرف","Usage")}</th><th>{pick("انقضا","Expires")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map((row,index)=>{const id=Number(row.id||row.subscription_id||0);const limit=num(row,"traffic_limit_bytes"),used=num(row,"traffic_used_bytes");return <tr key={id||index}><td>#{id}</td><td><code dir="ltr">{str(row,"account_username")||"—"}</code></td><td><b>{ownedTitle(row)}</b></td><td>{gbText(used)} / {gbText(limit)}</td><td>{dateText(row.expires_at)}</td><td><Badge tone={statusTone(str(row,"status"))}>{str(row,"status")||"—"}</Badge></td><td><div className="row-actions"><button className="mini-btn" disabled={busy} onClick={()=>void openConnection(row)}>{pick("اتصال","Connection")}</button><button className="mini-btn" disabled={busy} onClick={()=>void toggle(row)}>{pick("فعال/تعلیق","Toggle")}</button><button className="mini-btn danger" disabled={busy} onClick={()=>void remove(row)}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>
      {!filtered.length&&<div className="runtime-empty">{pick("اشتراکی ثبت نشده است.","No subscriptions yet.")}</div>}
    </Card>

    {connectionRow&&<div className="modal-backdrop" onClick={()=>setConnectionRow(null)}><div className="modal-card" onClick={event=>event.stopPropagation()}><div className="card-head"><div><b>{pick("اطلاعات اتصال","Connection details")}</b><small>#{String(connectionRow.id||"")}</small></div><button className="ghost" onClick={()=>setConnectionRow(null)}>×</button></div>{!connection?<div className="runtime-loading">{pick("در حال دریافت...","Loading...")}</div>:<div className="setting-grid"><label className="field"><span>{pick("نام کاربری","Username")}</span><code dir="ltr">{String((connection.account as ResellerRow)?.username??connection.account_username??"—")}</code></label><label className="field"><span>{pick("لینک اشتراک","Subscription link")}</span><code dir="ltr">{String(connection.subscription_link??"—")}</code></label></div>}</div></div>}
  </div></PortalShell>;
}
