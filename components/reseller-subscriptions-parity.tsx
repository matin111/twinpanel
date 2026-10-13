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
const dateInput=(value:unknown)=>{if(!value)return "";const d=new Date(String(value));if(Number.isNaN(d.getTime()))return "";const pad=(n:number)=>String(n).padStart(2,"0");return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;};
const statusTone=(status:string):"ok"|"warn"|"bad"|"violet"=>status==="active"?"ok":["expired","canceled","failed"].includes(status)?"bad":"warn";
const protocolLabels:Record<string,string>={cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray",xray:"V2Ray / Xray"};
const idempotency=(prefix:string)=>`${prefix}-${Date.now()}-${Math.random().toString(36).slice(2,10)}`;
const enabledProtocols=(plan:ResellerRow)=>Object.entries({cisco:"enable_cisco",openvpn:"enable_openvpn",wireguard:"enable_wireguard",l2tp:"enable_l2tp",v2ray:"enable_v2ray"}).filter(([,field])=>Boolean(plan[field])).map(([name])=>name);
const absoluteLink=(value:string)=>{if(typeof window==="undefined")return value;try{return new URL(value,window.location.origin).toString();}catch{return value;}};

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Empty({children}:{children:React.ReactNode}){return <div className="runtime-empty">{children}</div>;}

export function ResellerSubscriptionsParityRuntime(){
  const {pick}=useI18n();
  const [subs,setSubs]=useState<ResellerRow[]>([]);
  const [customers,setCustomers]=useState<ResellerRow[]>([]);
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
  const [showPassword,setShowPassword]=useState(false);

  const [sell,setSell]=useState({user_id:0,plan_id:0,node_ids:[] as number[],username:"",password:""});
  const [edit,setEdit]=useState({traffic_gb:0,expires_at:"",sell_price_toman:0,account_username:"",account_password:""});
  const [extend,setExtend]=useState({add_traffic_gb:0,add_days:30,charge_toman:0});

  const load=async()=>{
    setError("");
    const result=await Promise.allSettled([
      resellerApi.subscriptions(),
      resellerApi.customers(),
      resellerApi.plans(),
      resellerApi.serverOptions()
    ]);
    if(result[0].status==="fulfilled")setSubs(result[0].value);
    if(result[1].status==="fulfilled")setCustomers(result[1].value);
    if(result[2].status==="fulfilled")setPlans(result[2].value);
    if(result[3].status==="fulfilled")setServerOptions(result[3].value);
    const failed=result.find(x=>x.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
  };

  useEffect(()=>{void load();},[]);

  const selectedPlan=useMemo(()=>plans.find(plan=>Number(plan.plan_id||plan.id)===sell.plan_id)||null,[plans,sell.plan_id]);
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
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const copy=async(key:string,value:string)=>{
    try{await navigator.clipboard.writeText(value);setCopied(key);window.setTimeout(()=>setCopied(""),1300);}
    catch{setError(pick("کپی انجام نشد.","Copy failed."));}
  };

  const submitSale=(event:FormEvent)=>{
    event.preventDefault();
    if(!selectedPlan||!sell.user_id)return;
    const planId=Number(selectedPlan.plan_id||selectedPlan.id||0);
    const protocols=enabledProtocols(selectedPlan);
    void act(pick("اشتراک با موفقیت ساخته شد","Subscription created"),async()=>{
      await resellerApi.sellSubscription({
        user_id:sell.user_id,
        traffic_gb:Number(selectedPlan.traffic_gb||0),
        duration_days:Number(selectedPlan.duration_days||0),
        node_ids:sell.node_ids,
        protocols,
        sell_price_toman:Number(selectedPlan.sell_price_toman||0),
        username:sell.username.trim()||null,
        password:sell.password.trim()||null,
        idempotency_key:idempotency(`sale-${planId}`)
      });
      setSellOpen(false);
      setSell({user_id:0,plan_id:0,node_ids:[],username:"",password:""});
    });
  };

  const openEdit=(row:ResellerRow)=>{
    setEditRow(row);
    setEdit({
      traffic_gb:Number(gb(num(row,"traffic_limit_bytes")).toFixed(2)),
      expires_at:dateInput(row.expires_at),
      sell_price_toman:num(row,"sell_price_toman"),
      account_username:str(row,"account_username"),
      account_password:""
    });
  };

  const submitEdit=(event:FormEvent)=>{
    event.preventDefault();
    if(!editRow)return;
    const id=Number(editRow.id||editRow.subscription_id||0);
    if(!id||!edit.expires_at)return;
    void act(pick("اشتراک ویرایش شد","Subscription updated"),async()=>{
      await resellerApi.editSubscription(id,{
        traffic_gb:edit.traffic_gb,
        expires_at:new Date(edit.expires_at).toISOString(),
        sell_price_toman:edit.sell_price_toman,
        account_username:edit.account_username.trim()||null,
        account_password:edit.account_password.trim()||null
      });
      setEditRow(null);
    });
  };

  const openExtend=(row:ResellerRow)=>{
    setExtendRow(row);
    setExtend({add_traffic_gb:0,add_days:30,charge_toman:0});
  };

  const submitExtend=(event:FormEvent)=>{
    event.preventDefault();
    if(!extendRow)return;
    const id=Number(extendRow.id||extendRow.subscription_id||0);
    if(!id||(!extend.add_days&&!extend.add_traffic_gb))return;
    void act(pick("اشتراک تمدید شد","Subscription extended"),async()=>{
      await resellerApi.extendSubscription(id,{...extend,idempotency_key:idempotency(`extend-${id}`)});
      setExtendRow(null);
    });
  };

  const openConnection=async(row:ResellerRow)=>{
    const id=Number(row.id||row.subscription_id||0);if(!id)return;
    setConnectionRow(row);setConnection(null);setShowPassword(false);setBusy(true);setError("");
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
        <div className="action-row"><button className="ghost" onClick={()=>void load()} disabled={busy}>{pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={()=>setSellOpen(true)}>＋ {pick("فروش اشتراک","Sell subscription")}</button></div>
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

      {sellOpen&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setSellOpen(false)}/><form className="runtime-modal-card reseller-sub-modal" onSubmit={submitSale}><div className="card-head"><div><b>{pick("فروش اشتراک جدید","Sell new subscription")}</b><small>{pick("حجم، مدت و پروتکل‌ها از پلن مجاز مدیر خوانده می‌شوند.","Traffic, duration and protocols come from the admin-authorized plan.")}</small></div><button className="icon-button" type="button" onClick={()=>setSellOpen(false)}>×</button></div><div className="setting-grid"><label className="field"><span>{pick("مشتری","Customer")}</span><select required value={sell.user_id} onChange={e=>setSell(s=>({...s,user_id:Number(e.target.value)}))}><option value={0}>—</option>{customers.map((row,index)=>{const id=Number(row.id||row.user_id||0);return <option key={id||index} value={id}>{str(row,"full_name","name")||`#${id}`} {str(row,"phone")?`· ${str(row,"phone")}`:""}</option>})}</select></label><label className="field"><span>{pick("پلن مجاز","Authorized plan")}</span><select required value={sell.plan_id} onChange={e=>setSell(s=>({...s,plan_id:Number(e.target.value)}))}><option value={0}>—</option>{plans.map((plan,index)=>{const id=Number(plan.plan_id||plan.id||0);return <option key={id||index} value={id}>{str(plan,"name")||`#${id}`} · {String(plan.traffic_gb||0)}GB · {String(plan.duration_days||0)} {pick("روز","days")} · {money(num(plan,"sell_price_toman"))}</option>})}</select></label><label className="field"><span>{pick("نام کاربری دلخواه (اختیاری)","Custom username (optional)")}</span><input dir="ltr" value={sell.username} onChange={e=>setSell(s=>({...s,username:e.target.value}))}/></label><label className="field"><span>{pick("رمز دلخواه (اختیاری)","Custom password (optional)")}</span><input dir="ltr" value={sell.password} onChange={e=>setSell(s=>({...s,password:e.target.value}))}/></label></div>{selectedPlan&&<div className="reseller-plan-preview"><div><span>{pick("حجم","Traffic")}</span><b>{String(selectedPlan.traffic_gb||0)} GB</b></div><div><span>{pick("مدت","Duration")}</span><b>{String(selectedPlan.duration_days||0)} {pick("روز","days")}</b></div><div><span>{pick("قیمت فروش","Sell price")}</span><b>{money(num(selectedPlan,"sell_price_toman"))}</b></div><div><span>{pick("پروتکل‌ها","Protocols")}</span><b>{enabledProtocols(selectedPlan).map(p=>protocolLabels[p]).join(" · ")||"—"}</b></div></div>}{nodes.length>0&&<div className="runtime-choice-section"><b>{pick("سرور مقصد","Destination server")}</b><small>{pick("اگر انتخاب نشود، تخصیص خودکار انجام می‌شود.","Leave empty for automatic assignment.")}</small><div className="protocol-toggle-grid">{nodes.map((node,index)=>{const id=Number(node.id||0),checked=sell.node_ids.includes(id);return <label className="toggle module-toggle" key={id||index}><span>{str(node,"name")||`#${id}`}{Boolean(node.is_mother)?` · ${pick("مادر","Mother")}`:""}</span><input type="checkbox" checked={checked} onChange={e=>setSell(s=>({...s,node_ids:e.target.checked?[...s.node_ids,id]:s.node_ids.filter(x=>x!==id)}))}/><i/></label>})}</div></div>}<div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setSellOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||!sell.user_id||!selectedPlan}>{busy?"…":pick("ساخت اشتراک","Create subscription")}</button></div></form></div>}

      {editRow&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setEditRow(null)}/><form className="runtime-modal-card reseller-sub-modal" onSubmit={submitEdit}><div className="card-head"><div><b>{pick("ویرایش اشتراک","Edit subscription")} #{str(editRow,"id")}</b><small>{str(editRow,"customer_name")}</small></div><button className="icon-button" type="button" onClick={()=>setEditRow(null)}>×</button></div><div className="setting-grid"><label className="field"><span>{pick("حجم کل GB","Total traffic GB")}</span><input type="number" min={0.01} step="0.01" value={edit.traffic_gb} onChange={e=>setEdit(v=>({...v,traffic_gb:Number(e.target.value)}))}/></label><label className="field"><span>{pick("تاریخ انقضا","Expiration")}</span><input type="datetime-local" required value={edit.expires_at} onChange={e=>setEdit(v=>({...v,expires_at:e.target.value}))}/></label><label className="field"><span>{pick("قیمت فروش","Sell price")}</span><input type="number" min={0} value={edit.sell_price_toman} onChange={e=>setEdit(v=>({...v,sell_price_toman:Number(e.target.value)}))}/></label><label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={edit.account_username} onChange={e=>setEdit(v=>({...v,account_username:e.target.value}))}/></label><label className="field"><span>{pick("رمز جدید (اختیاری)","New password (optional)")}</span><input dir="ltr" value={edit.account_password} onChange={e=>setEdit(v=>({...v,account_password:e.target.value}))} placeholder={pick("خالی = بدون تغییر","Empty = keep current")}/></label></div><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setEditRow(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy}>{pick("ذخیره تغییرات","Save changes")}</button></div></form></div>}

      {extendRow&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>!busy&&setExtendRow(null)}/><form className="runtime-modal-card reseller-sub-modal" onSubmit={submitExtend}><div className="card-head"><div><b>{pick("تمدید اشتراک","Extend subscription")} #{str(extendRow,"id")}</b><small>{pick("فقط مقدار افزایشی را وارد کنید.","Enter only the additional amount.")}</small></div><button className="icon-button" type="button" onClick={()=>setExtendRow(null)}>×</button></div><div className="setting-grid"><label className="field"><span>{pick("حجم اضافه GB","Additional traffic GB")}</span><input type="number" min={0} step="0.01" value={extend.add_traffic_gb} onChange={e=>setExtend(v=>({...v,add_traffic_gb:Number(e.target.value)}))}/></label><label className="field"><span>{pick("روز اضافه","Additional days")}</span><input type="number" min={0} value={extend.add_days} onChange={e=>setExtend(v=>({...v,add_days:Number(e.target.value)}))}/></label><label className="field"><span>{pick("مبلغ ثبت فروش (اختیاری)","Recorded charge (optional)")}</span><input type="number" min={0} value={extend.charge_toman} onChange={e=>setExtend(v=>({...v,charge_toman:Number(e.target.value)}))}/></label></div><div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setExtendRow(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||(!extend.add_days&&!extend.add_traffic_gb)}>{pick("ثبت تمدید","Apply extension")}</button></div></form></div>}

      {connectionRow&&<div className="runtime-modal reseller-connection-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" type="button" onClick={()=>setConnectionRow(null)}/><div className="runtime-modal-card reseller-connection-card"><div className="card-head"><div><b>{pick("اطلاعات اتصال","Connection information")} #{str(connectionRow,"id")}</b><small>{str(connectionRow,"customer_name")}</small></div><button className="icon-button" type="button" onClick={()=>setConnectionRow(null)}>×</button></div>{!connection?<div className="runtime-loading">{pick("در حال دریافت اطلاعات اتصال...","Loading connection information...")}</div>:<ConnectionDetails info={connection} copied={copied} showPassword={showPassword} setShowPassword={setShowPassword} copy={copy} pick={pick}/>}<div className="runtime-modal-actions"><button className="ghost" type="button" onClick={()=>setConnectionRow(null)}>{pick("بستن","Close")}</button></div></div></div>}
    </div>
  </PortalShell>;
}

function ConnectionDetails({info,copied,showPassword,setShowPassword,copy,pick}:{info:ResellerRow;copied:string;showPassword:boolean;setShowPassword:(v:boolean)=>void;copy:(key:string,value:string)=>Promise<void>;pick:(fa:string,en:string)=>string}){
  const account=(info.account&&typeof info.account==="object"?info.account:{}) as ResellerRow;
  const username=str(account,"username");
  const password=str(account,"password");
  const link=str(info,"subscription_link");
  const credentials=rowsOf(info.credentials);
  return <div className="reseller-connection-content">
    <div className="reseller-secret-grid">
      <div><span>{pick("نام کاربری","Username")}</span><code dir="ltr">{username||"—"}</code>{username&&<button type="button" className="mini-btn" onClick={()=>void copy("username",username)}>{copied==="username"?"✓":pick("کپی","Copy")}</button>}</div>
      <div><span>{pick("رمز عبور","Password")}</span><code dir="ltr">{password?(showPassword?password:"••••••••••"):"—"}</code>{password&&<><button type="button" className="mini-btn" onClick={()=>setShowPassword(!showPassword)}>{showPassword?pick("مخفی","Hide"):pick("نمایش","Show")}</button><button type="button" className="mini-btn" onClick={()=>void copy("password",password)}>{copied==="password"?"✓":pick("کپی","Copy")}</button></>}</div>
      <div className="wide"><span>{pick("لینک اتصال","Connection link")}</span><code dir="ltr">{link?absoluteLink(link):"—"}</code>{link&&<><button type="button" className="mini-btn" onClick={()=>void copy("link",absoluteLink(link))}>{copied==="link"?"✓":pick("کپی","Copy")}</button><button type="button" className="mini-btn" onClick={()=>window.open(absoluteLink(link),"_blank","noopener,noreferrer")}>{pick("باز کردن","Open")}</button></>}</div>
    </div>
    <div className="reseller-protocol-list">{credentials.map((cred,index)=>{const protocol=str(cred,"protocol");const items=rowsOf(cred.items,"items");return <section key={`${protocol}-${index}`}><div className="card-head"><b>{protocolLabels[protocol]||protocol}</b><Badge tone="violet">{items.length||1}</Badge></div>{items.length?items.map((item,itemIndex)=><CredentialItem key={itemIndex} protocol={protocol} item={item} copied={copied} copy={copy} pick={pick}/>):<small>{pick("اطلاعات این پروتکل از لینک اتصال قابل دریافت است.","Use the connection link for this protocol.")}</small>}</section>})}{!credentials.length&&<Empty>{pick("اطلاعات پروتکل جداگانه‌ای ثبت نشده است؛ از لینک اتصال استفاده کنید.","No separate protocol credentials are stored; use the connection link.")}</Empty>}</div>
  </div>;
}

function CredentialItem({protocol,item,copied,copy,pick}:{protocol:string;item:ResellerRow;copied:string;copy:(key:string,value:string)=>Promise<void>;pick:(fa:string,en:string)=>string}){
  const pairs=[
    ["host",pick("سرور","Server")],
    ["server",pick("سرور","Server")],
    ["port",pick("پورت","Port")],
    ["username",pick("نام کاربری","Username")],
    ["password",pick("رمز","Password")],
    ["psk","PSK"],
    ["uri",pick("لینک","URI")],
    ["config",pick("کانفیگ","Config")]
  ] as const;
  const shown=pairs.filter(([key])=>item[key]!==undefined&&item[key]!==null&&String(item[key]).trim()!=="");
  return <div className="reseller-credential-item">{shown.map(([key,label],index)=>{const value=String(item[key]);const copyKey=`${protocol}-${key}-${index}`;return <div key={`${key}-${index}`} className={key==="config"||key==="uri"?"wide":""}><span>{label}</span><code dir="ltr">{key==="config"&&value.length>180?`${value.slice(0,180)}…`:value}</code><button className="mini-btn" type="button" onClick={()=>void copy(copyKey,value)}>{copied===copyKey?"✓":pick("کپی","Copy")}</button></div>})}{!shown.length&&<small>{pick("اطلاعات تکمیلی از لینک اتصال قابل دریافت است.","Additional details are available through the connection link.")}</small>}</div>;
}
