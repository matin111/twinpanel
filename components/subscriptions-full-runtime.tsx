"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,AdminUser,RuntimeRow} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const protocolLabels:Record<string,string>={cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray"};
const protocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"];
const s=(v:unknown)=>String(v??"");
const n=(v:unknown)=>{const x=Number(v??0);return Number.isFinite(x)?x:0;};
const arr=(v:unknown):RuntimeRow[]=>Array.isArray(v)?v.filter(x=>x&&typeof x==="object") as RuntimeRow[]:v&&typeof v==="object"?[v as RuntimeRow]:[];
const strArr=(v:unknown)=>Array.isArray(v)?v.map(String):[];
const numArr=(v:unknown)=>Array.isArray(v)?v.map(Number).filter(Number.isFinite):[];
const date=(v:unknown)=>{if(!v)return "—";const d=new Date(String(v));return Number.isNaN(d.getTime())?String(v):d.toLocaleString("fa-IR");};
const statusTone=(v:unknown):"ok"|"warn"|"bad"|"violet"=>{const x=s(v).toLowerCase();return ["active","online","ok","healthy"].includes(x)?"ok":["expired","canceled","offline","failed","error"].includes(x)?"bad":"warn";};

function copy(value:string){if(value)void navigator.clipboard.writeText(value);}
function downloadText(filename:string,content:string){
  const blob=new Blob([content],{type:"text/plain;charset=utf-8"});
  const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=filename||"config.txt";a.click();URL.revokeObjectURL(url);
}

export function SubscriptionsFullRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);const [plans,setPlans]=useState<RuntimeRow[]>([]);const [users,setUsers]=useState<AdminUser[]>([]);const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [selectedId,setSelectedId]=useState(0);const [info,setInfo]=useState<RuntimeRow|null>(null);const [q,setQ]=useState("");
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState("");const [error,setError]=useState("");const [ok,setOk]=useState("");
  const [createOpen,setCreateOpen]=useState(false);const [editOpen,setEditOpen]=useState(false);const [showPassword,setShowPassword]=useState(false);
  const [planId,setPlanId]=useState(0);const [trafficGb,setTrafficGb]=useState(0);const [durationDays,setDurationDays]=useState(30);const [protocols,setProtocols]=useState<string[]>([]);const [accountUsername,setAccountUsername]=useState("");const [accountPassword,setAccountPassword]=useState("");
  const [create,setCreate]=useState({user_id:0,plan_id:0,traffic_gb:"",duration_days:"",username:"",password:"",protocols:["cisco","openvpn","wireguard","l2tp","v2ray"] as string[]});

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [subs,p,u,ns]=await Promise.all([adminApi.subscriptions(),adminApi.plans(),adminApi.users(),adminApi.nodes()]);
      setRows(subs);setPlans(p);setUsers(u);setNodes(ns);
      setSelectedId(current=>current&&subs.some(x=>n(x.id)===current)?current:(subs[0]?n(subs[0].id):0));
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const selected=useMemo(()=>rows.find(x=>n(x.id)===selectedId)||null,[rows,selectedId]);
  const userMap=useMemo(()=>new Map(users.map(x=>[x.id,x])),[users]);
  const planMap=useMemo(()=>new Map(plans.map(x=>[n(x.id),x])),[plans]);
  const nodeMap=useMemo(()=>new Map(nodes.map(x=>[x.id,x])),[nodes]);
  const filtered=useMemo(()=>{const needle=q.trim().toLowerCase();if(!needle)return rows;return rows.filter(row=>{const user=userMap.get(n(row.user_id));const plan=planMap.get(n(row.plan_id));return `${row.id??""} ${user?.full_name??""} ${user?.email??""} ${row.customer_name??""} ${row.customer_email??""} ${row.account_username??""} ${plan?.name??row.plan_name??""} ${row.status??""}`.toLowerCase().includes(needle);});},[rows,q,userMap,planMap]);

  const loadConnection=async(id:number)=>{
    if(!id){setInfo(null);return;}
    setBusy("connection");setError("");
    try{const out=await adminApi.subscriptionConnectionInfo(id);setInfo(out);}catch(e){setInfo(null);setError(e instanceof Error?e.message:String(e));}finally{setBusy("");}
  };
  useEffect(()=>{if(selectedId)void loadConnection(selectedId);},[selectedId]);

  useEffect(()=>{
    if(!selected)return;
    const account=info&&typeof info.account==="object"&&info.account?info.account as RuntimeRow:{};
    setPlanId(n(selected.plan_id));
    setTrafficGb(n(selected.traffic_limit_gb)||(n(selected.traffic_limit_bytes)/GB));
    const start=selected.starts_at?new Date(String(selected.starts_at)):null;const end=selected.expires_at?new Date(String(selected.expires_at)):null;
    setDurationDays(start&&end&&!Number.isNaN(start.getTime())&&!Number.isNaN(end.getTime())?Math.max(1,Math.ceil((end.getTime()-start.getTime())/86400000)):30);
    setProtocols(strArr(selected.protocols));
    setAccountUsername(s(account.username||selected.account_username));
    setAccountPassword(s(account.password));
  },[selected,info]);

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,refresh=true)=>{
    if(busy)return;setBusy(key);setError("");setOk("");
    try{await fn();setOk(label);if(refresh)await load();if(selectedId)await loadConnection(selectedId);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy("");}
  };

  const saveEdit=(e:FormEvent)=>{e.preventDefault();if(!selectedId)return;void act("edit",pick("اشتراک ذخیره شد","Subscription saved"),()=>adminApi.editSubscription(selectedId,{plan_id:planId,traffic_gb:trafficGb,node_ids:numArr(selected?.node_ids),protocols,account_username:accountUsername||undefined,account_password:accountPassword||undefined}));};
  const saveLimits=()=>{if(!selectedId)return;void act("limits",pick("حجم و مدت ذخیره شد","Limits saved"),()=>adminApi.setSubscriptionManualLimits(selectedId,{traffic_gb:trafficGb,duration_days:durationDays}));};
  const createSub=(e:FormEvent)=>{e.preventDefault();void act("create",pick("اشتراک ساخته شد","Subscription created"),async()=>{await adminApi.createSubscription({user_id:create.user_id,plan_id:create.plan_id,node_ids:[],protocols:create.protocols,...(create.traffic_gb?{traffic_gb:Number(create.traffic_gb)}:{}),...(create.duration_days?{duration_days:Number(create.duration_days)}:{}),...(create.username?{username:create.username}:{}),...(create.password?{password:create.password}:{})});setCreateOpen(false);setCreate(v=>({...v,user_id:0,plan_id:0,traffic_gb:"",duration_days:"",username:"",password:""}));});};
  const toggleProtocol=(key:string,checked:boolean,setter:(x:string[])=>void,current:string[])=>setter(checked?[...new Set([...current,key])]:current.filter(x=>x!==key));

  const credentials=info&&Array.isArray(info.credentials)?info.credentials as RuntimeRow[]:[];
  const account=info&&typeof info.account==="object"&&info.account?info.account as RuntimeRow:null;
  const subscriptionLink=s(info?.subscription_link);
  const active=rows.filter(x=>s(x.status).toLowerCase()==="active").length;
  const totalLimit=rows.reduce((sum,x)=>sum+n(x.traffic_limit_bytes),0)/GB;

  return <Shell active="/admin/subscriptions"><div className="page subs-full">
    <div className="page-head"><div><h1>{pick("اشتراک‌ها","Subscriptions")}</h1><small>{pick("مدیریت کامل اشتراک و اطلاعات اتصال در یک صفحه","Full subscription management and connection information in one place")}</small></div><div className="action-row"><button className="primary" onClick={()=>setCreateOpen(v=>!v)}>＋ {pick("اشتراک جدید","New subscription")}</button><button className="ghost" disabled={loading} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}
    <div className="stats dashboard-stats"><Stat label={pick("کل اشتراک‌ها","Total")} value={String(rows.length)}/><Stat label={pick("فعال","Active")} value={String(active)}/><Stat label={pick("حجم تخصیص‌یافته","Allocated traffic")} value={`${totalLimit.toLocaleString("fa-IR",{maximumFractionDigits:1})} GB`}/></div>

    {createOpen&&<Card className="runtime-editor"><form onSubmit={createSub}><div className="card-head"><div><b>{pick("ساخت اشتراک جدید","Create subscription")}</b><small>{pick("همان اطلاعات پایه پنل قدیمی","Same core account fields as the legacy panel")}</small></div><button type="button" className="mini-btn" onClick={()=>setCreateOpen(false)}>×</button></div><div className="setting-grid"><label className="field"><span>{pick("کاربر","User")}</span><select required value={create.user_id} onChange={e=>setCreate(v=>({...v,user_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب کاربر","Select user")}</option>{users.filter(x=>x.role!=="admin").map(x=><option key={x.id} value={x.id}>{x.full_name||x.email||`#${x.id}`}</option>)}</select></label><label className="field"><span>{pick("پلن","Plan")}</span><select required value={create.plan_id} onChange={e=>setCreate(v=>({...v,plan_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب پلن","Select plan")}</option>{plans.map(x=><option key={String(x.id)} value={n(x.id)}>{s(x.name)||`#${x.id}`}</option>)}</select></label><label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={create.username} onChange={e=>setCreate(v=>({...v,username:e.target.value}))}/></label><label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" value={create.password} onChange={e=>setCreate(v=>({...v,password:e.target.value}))}/></label><label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={0} step="0.1" value={create.traffic_gb} onChange={e=>setCreate(v=>({...v,traffic_gb:e.target.value}))}/></label><label className="field"><span>{pick("مدت روز","Duration days")}</span><input type="number" min={1} value={create.duration_days} onChange={e=>setCreate(v=>({...v,duration_days:e.target.value}))}/></label></div><div className="protocol-toggle-grid">{protocolKeys.map(key=><label className="toggle module-toggle" key={key}><span>{protocolLabels[key]}</span><input type="checkbox" checked={create.protocols.includes(key)} onChange={e=>toggleProtocol(key,e.target.checked,p=>setCreate(v=>({...v,protocols:p})),create.protocols)}/><i/></label>)}</div><button className="primary" disabled={busy==="create"||!create.user_id||!create.plan_id||!create.protocols.length}>{busy==="create"?"…":pick("ساخت اشتراک","Create")}</button></form></Card>}

    <div className="subs-master-detail">
      <Card className="subs-sidebar"><div className="card-head"><div><b>{pick("لیست اشتراک‌ها","Subscription list")}</b><small>{filtered.length.toLocaleString("fa-IR")}</small></div></div><label className="field"><span>{pick("جستجو","Search")}</span><input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("نام، ایمیل، نام کاربری، شناسه…","Name, email, username, ID…")}/></label><div className="subs-list">{filtered.map(row=>{const id=n(row.id),user=userMap.get(n(row.user_id)),plan=planMap.get(n(row.plan_id));return <button key={id} type="button" className={`subs-list-item ${selectedId===id?"active":""}`} onClick={()=>{setSelectedId(id);setEditOpen(false);}}><div><b>{s(row.account_username)||user?.full_name||user?.email||`#${id}`}</b><small>#{id} · {s(row.plan_name)||s(plan?.name)||`Plan #${row.plan_id}`}</small></div><Badge tone={statusTone(row.status)}>{s(row.status)||"—"}</Badge></button>})}{!filtered.length&&!loading&&<div className="runtime-empty">{pick("اشتراکی پیدا نشد","No subscriptions")}</div>}</div></Card>

      <div className="subs-detail">{selected?<>
        <Card><div className="card-head"><div><b>{pick("جزئیات اشتراک","Subscription details")}</b><small>#{selectedId}</small></div><Badge tone={statusTone(selected.status)}>{s(selected.status)||"—"}</Badge></div><div className="subs-summary-grid"><div><span>{pick("کاربر","User")}</span><b>{userMap.get(n(selected.user_id))?.full_name||s(selected.customer_name)||userMap.get(n(selected.user_id))?.email||s(selected.customer_email)||`#${selected.user_id}`}</b></div><div><span>{pick("پلن","Plan")}</span><b>{s(selected.plan_name)||s(planMap.get(n(selected.plan_id))?.name)||`#${selected.plan_id}`}</b></div><div><span>{pick("نام کاربری","Username")}</span><b dir="ltr">{s(account?.username||selected.account_username)||"—"}</b></div><div><span>{pick("رمز عبور","Password")}</span><div className="secret-row"><b dir="ltr">{showPassword?s(account?.password)||"—":"••••••••"}</b><button className="mini-btn" onClick={()=>setShowPassword(v=>!v)}>{showPassword?"◉":"◎"}</button>{s(account?.password)&&<button className="mini-btn" onClick={()=>copy(s(account?.password))}>⧉</button>}</div></div><div><span>{pick("حجم کل","Traffic")}</span><b>{(n(selected.traffic_limit_bytes)/GB).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB</b></div><div><span>{pick("مصرف","Used")}</span><b>{(n(selected.traffic_used_bytes)/GB).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB</b></div><div><span>{pick("شروع","Starts")}</span><b>{date(selected.starts_at)}</b></div><div><span>{pick("انقضا","Expires")}</span><b>{date(selected.expires_at)}</b></div><div><span>{pick("پروتکل‌ها","Protocols")}</span><b>{strArr(selected.protocols).map(x=>protocolLabels[x]||x).join("، ")||"—"}</b></div><div><span>{pick("نودها","Nodes")}</span><b>{numArr(selected.node_ids).map(x=>nodeMap.get(x)?.name||`#${x}`).join("، ")||pick("سراسری","Global")}</b></div></div>
        <div className="action-row subs-actions"><button className="primary" onClick={()=>setEditOpen(v=>!v)}>{pick("ویرایش اشتراک","Edit subscription")}</button><button className="ghost" disabled={Boolean(busy)} onClick={()=>void act("status",s(selected.status).toLowerCase()==="active"?pick("اشتراک تعلیق شد","Suspended"):pick("اشتراک فعال شد","Activated"),()=>adminApi.setSubscriptionActive(selectedId,s(selected.status).toLowerCase()!=="active"))}>{s(selected.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button className="ghost" disabled={Boolean(busy)} onClick={()=>void act("provision",pick("Provision انجام شد","Provision complete"),()=>adminApi.provisionSubscription(selectedId))}>Provision</button><button className="ghost" disabled={Boolean(busy)} onClick={()=>void act("refresh",pick("Credentialها تازه شدند","Credentials refreshed"),()=>adminApi.refreshSubscriptionPasswords(selectedId))}>{pick("رمز جدید","Refresh credentials")}</button><button className="ghost danger" disabled={Boolean(busy)} onClick={()=>{if(window.confirm(pick("این اشتراک حذف شود؟","Delete this subscription?")))void act("delete",pick("اشتراک حذف شد","Subscription deleted"),()=>adminApi.deleteSubscription(selectedId));}}>{pick("حذف","Delete")}</button></div></Card>

        {editOpen&&<Card className="runtime-editor"><form onSubmit={saveEdit}><div className="card-head"><div><b>{pick("ویرایش کامل","Full edit")}</b><small>{pick("پلن، حجم، مدت، پروتکل‌ها، نام کاربری و رمز عبور","Plan, traffic, duration, protocols, username and password")}</small></div><button type="button" className="mini-btn" onClick={()=>setEditOpen(false)}>×</button></div><div className="setting-grid"><label className="field"><span>{pick("پلن","Plan")}</span><select value={planId} onChange={e=>setPlanId(Number(e.target.value))}>{plans.map(x=><option key={String(x.id)} value={n(x.id)}>{s(x.name)||`#${x.id}`}</option>)}</select></label><label className="field"><span>{pick("حجم نهایی GB","Final traffic GB")}</span><input type="number" min={0.01} step="0.01" value={trafficGb} onChange={e=>setTrafficGb(Number(e.target.value))}/></label><label className="field"><span>{pick("مدت نهایی روز","Final duration days")}</span><input type="number" min={1} value={durationDays} onChange={e=>setDurationDays(Number(e.target.value))}/></label><label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={accountUsername} onChange={e=>setAccountUsername(e.target.value)}/></label><label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" value={accountPassword} onChange={e=>setAccountPassword(e.target.value)}/></label></div><div className="runtime-choice-section"><b>{pick("پروتکل‌ها","Protocols")}</b><div className="protocol-toggle-grid">{protocolKeys.map(key=><label className="toggle module-toggle" key={key}><span>{protocolLabels[key]}</span><input type="checkbox" checked={protocols.includes(key)} onChange={e=>toggleProtocol(key,e.target.checked,setProtocols,protocols)}/><i/></label>)}</div></div><div className="action-row"><button className="primary" disabled={busy==="edit"||!planId||!protocols.length}>{pick("ذخیره مشخصات و Credential","Save account & credentials")}</button><button type="button" className="ghost" disabled={busy==="limits"} onClick={saveLimits}>{pick("ذخیره حجم و مدت","Save traffic & duration")}</button></div></form></Card>}

        <Card className="subs-connection"><div className="card-head"><div><b>{pick("اطلاعات اتصال","Connection information")}</b><small>{pick("همان اطلاعات اتصال پنل قدیمی، بدون JSON خام","Legacy connection details, rendered as fields instead of raw JSON")}</small></div><button className="ghost" disabled={busy==="connection"} onClick={()=>void loadConnection(selectedId)}>{busy==="connection"?"…":pick("بروزرسانی","Refresh")}</button></div>
          {subscriptionLink&&<div className="sub-link-row"><div><span>{pick("لینک سابسکریپشن","Subscription link")}</span><code dir="ltr">{subscriptionLink}</code></div><button className="ghost" onClick={()=>copy(subscriptionLink)}>{pick("کپی","Copy")}</button><a className="ghost button-link" href={subscriptionLink} target="_blank" rel="noreferrer">{pick("باز کردن","Open")}</a></div>}
          {credentials.length?<div className="protocol-sections">{credentials.map((cred,ci)=>{const protocol=s(cred.protocol).toLowerCase();const items=arr(cred.items);return <section className="protocol-section" key={`${protocol}-${ci}`}><div className="protocol-section-head"><div><b>{protocolLabels[protocol]||protocol||pick("پروتکل","Protocol")}</b><small>{items.length.toLocaleString("fa-IR")} {pick("سرور","server")}</small></div><Badge tone="ok">{pick("فعال","Active")}</Badge></div><div className="credential-grid">{items.map((item,ii)=>{const config=s(item.config);const uri=s(item.uri);const username=s(item.username||cred.username||account?.username);const password=s(item.password||account?.password);const filename=s(item.filename)||`${protocol}-${ii+1}.txt`;return <article className="credential-card" key={`${ci}-${ii}`}><div className="credential-title"><div><b>{s(item.node)||`${pick("سرور","Server")} ${ii+1}`}</b><small>{s(item.country_code||item.country)||""}</small></div><span className="status-dot online"/></div><div className="credential-fields">{s(item.server||item.server_ip)&&<div><span>{pick("آدرس سرور","Server")}</span><code dir="ltr">{s(item.server||item.server_ip)}</code><button onClick={()=>copy(s(item.server||item.server_ip))}>⧉</button></div>}{item.port!=null&&<div><span>{pick("پورت","Port")}</span><code dir="ltr">{s(item.port)}</code><button onClick={()=>copy(s(item.port))}>⧉</button></div>}{s(item.transport)&&<div><span>Transport</span><code dir="ltr">{s(item.transport)}</code></div>}{username&&<div><span>{pick("نام کاربری","Username")}</span><code dir="ltr">{username}</code><button onClick={()=>copy(username)}>⧉</button></div>}{password&&<div><span>{pick("رمز عبور","Password")}</span><code dir="ltr">{showPassword?password:"••••••••"}</code><button onClick={()=>copy(password)}>⧉</button></div>}{s(item.psk)&&<div><span>IPsec PSK</span><code dir="ltr">{s(item.psk)}</code><button onClick={()=>copy(s(item.psk))}>⧉</button></div>}{s(item.address)&&<div><span>Address</span><code dir="ltr">{s(item.address)}</code><button onClick={()=>copy(s(item.address))}>⧉</button></div>}</div>{uri&&<div className="credential-config"><span>URI</span><code dir="ltr">{uri}</code><div className="action-row"><button className="ghost" onClick={()=>copy(uri)}>{pick("کپی","Copy")}</button></div></div>}{config&&<div className="credential-config"><span>{pick("کانفیگ","Config")}</span><pre dir="ltr">{config}</pre><div className="action-row"><button className="ghost" onClick={()=>copy(config)}>{pick("کپی","Copy")}</button><button className="ghost" onClick={()=>downloadText(filename,config)}>{pick("دانلود","Download")}</button></div></div>}</article>})}</div></section>})}</div>:busy!=="connection"&&<div className="runtime-empty">{pick("برای این اشتراک Credential فعالی ثبت نشده است. در صورت نیاز Provision را اجرا کنید.","No active credentials are stored for this subscription. Provision the account if needed.")}</div>}
        </Card>
      </>:<Card><div className="runtime-empty">{pick("یک اشتراک انتخاب کنید","Select a subscription")}</div></Card>}</div>
    </div>
  </div></Shell>;
}
