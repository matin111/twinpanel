"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {QRCodeSVG} from "qrcode.react";
import {Badge,Card,Shell,Stat} from "./ui";
import {SubscriptionLinkDeliveryModal} from "./subscription-link-delivery-modal";
import {adminApi,AdminNode,AdminUser,RuntimeRow} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const classicProtocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"] as const;
const modernProtocolKeys=["hysteria2","tuic","anytls","naive","shadowtls","snell","mieru","trusttunnel","amneziawg","sudoku"] as const;
const protocolKeys=[...classicProtocolKeys,...modernProtocolKeys] as const;
const classicProtocolSet=new Set<string>(classicProtocolKeys);
const protocolLabels:Record<string,string>={
  cisco:"Cisco / OpenConnect",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP / IPsec",
  v2ray:"V2Ray / Xray",
  hysteria2:"Hysteria2",
  tuic:"TUIC",
  anytls:"AnyTLS",
  naive:"NaiveProxy",
  shadowtls:"ShadowTLS",
  snell:"Snell",
  mieru:"Mieru",
  trusttunnel:"TrustTunnel",
  amneziawg:"AmneziaWG",
  sudoku:"Sudoku"
};

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const list=(value:unknown):RuntimeRow[]=>Array.isArray(value)?value.filter(item=>item&&typeof item==="object") as RuntimeRow[]:value&&typeof value==="object"?[value as RuntimeRow]:[];
const strings=(value:unknown)=>Array.isArray(value)?value.map(String):[];
const formatDate=(value:unknown)=>{if(!value)return "—";const date=new Date(String(value));return Number.isNaN(date.getTime())?String(value):date.toLocaleDateString("fa-IR",{year:"numeric",month:"short",day:"numeric"});};
const formatBytes=(value:unknown)=>`${(n(value)/GB).toLocaleString("fa-IR",{maximumFractionDigits:1})} GB`;
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{const key=s(value).toLowerCase();return key==="active"?"ok":["expired","canceled"].includes(key)?"bad":"warn";};
const statusLabel=(value:unknown)=>{const key=s(value).toLowerCase();return key==="active"?"فعال":key==="pending"?"در انتظار":key==="expired"?"منقضی":key==="suspended"?"معلق":key==="canceled"?"لغوشده":s(value)||"نامشخص";};
const optionalPositive=(value:string)=>{const clean=value.trim();if(!clean)return undefined;const out=Number(clean);return Number.isFinite(out)&&out>0?out:undefined;};
const planProtocols=(plan:RuntimeRow|undefined)=>{
  if(!plan)return [];
  const explicit=strings(plan.protocols).filter(key=>protocolKeys.includes(key as typeof protocolKeys[number]));
  return explicit.length?explicit:classicProtocolKeys.filter(key=>Boolean(plan[`enable_${key}`]));
};
const planTraffic=(plan:RuntimeRow|undefined)=>n(plan?.traffic_gb)>0?String(n(plan?.traffic_gb)):"";
const planDuration=(plan:RuntimeRow|undefined)=>n(plan?.duration_days)>0?String(Math.trunc(n(plan?.duration_days))):"";

function copy(value:string){if(value)void navigator.clipboard.writeText(value);}
function absoluteLink(value:string){if(!value)return "";if(/^https?:\/\//i.test(value))return value;if(typeof window!=="undefined")return new URL(value,window.location.origin).toString();return value;}
function downloadText(filename:string,content:string){const blob=new Blob([content],{type:"text/plain;charset=utf-8"});const url=URL.createObjectURL(blob);const anchor=document.createElement("a");anchor.href=url;anchor.download=filename||"config.txt";anchor.click();URL.revokeObjectURL(url);}

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}

function Modal({title,sub,onClose,children,wide=false}:{title:string;sub?:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){
  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className={`runtime-modal-card ${wide?"manage-card":""}`}>
      <div className="card-head"><div><b>{title}</b>{sub&&<small>{sub}</small>}</div><button type="button" className="icon-button" onClick={onClose}>×</button></div>
      {children}
    </div>
  </div>;
}

type ModalKind="create"|"edit"|"extend"|"connect"|null;
type Draft={user_id:number;plan_id:number;traffic_gb:string;duration_days:string;device_limit:string;username:string;password:string;protocols:string[]};

export function LegacySubscriptionsRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [plans,setPlans]=useState<RuntimeRow[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");
  const [page,setPage]=useState(0);
  const [matchedTotal,setMatchedTotal]=useState(0);
  const [globalStats,setGlobalStats]=useState({total:0,active:0,expired:0,suspended:0,online:0});
  const pageSize=40;
  const listRequestId=useRef(0);
  const [status,setStatus]=useState<"all"|"active"|"expired"|"suspended"|"pending"|"online">("all");
  const [modal,setModal]=useState<ModalKind>(null);
  const [selected,setSelected]=useState<RuntimeRow|null>(null);
  const [connection,setConnection]=useState<RuntimeRow|null>(null);
  const [activeProtocol,setActiveProtocol]=useState("cisco");
  const [showPassword,setShowPassword]=useState(false);
  const [userSearch,setUserSearch]=useState("");
  const [extendDays,setExtendDays]=useState(30);
  const [extendTraffic,setExtendTraffic]=useState(10);
  const [linkModalId,setLinkModalId]=useState<number|null>(null);
  const [linkModalLink,setLinkModalLink]=useState("");
  const [linkModalLoading,setLinkModalLoading]=useState(false);
  const [linkModalError,setLinkModalError] = useState("");
  const [transferOpen,setTransferOpen]=useState(false);
  const [transferResellers,setTransferResellers]=useState<RuntimeRow[]>([]);
  const [transferCustomers,setTransferCustomers]=useState<Array<{id:number;name:string;email?:string|null;is_owner:boolean}>>([]);
  const [transferResellerId,setTransferResellerId]=useState(0);
  const [transferCustomerId,setTransferCustomerId]=useState(0);
  const [transferLoading,setTransferLoading]=useState(false);
  // Share URLs are stable for a subscription; cache and dedupe requests so
  // opening the modal does not wait for heavyweight connection-info/provisioning.
  const linkCache=useRef(new Map<number,string>());
  const linkPending=useRef(new Map<number,Promise<string>>());
  const linkRequestGeneration=useRef(0);

  const [draft,setDraft]=useState<Draft>({user_id:0,plan_id:0,traffic_gb:"",duration_days:"",device_limit:"1",username:"",password:"",protocols:[]});

  const load=async(silent=false)=>{
    const requestId=++listRequestId.current;
    if(!silent)setLoading(true);
    setError("");
    try{
      const data=await adminApi.subscriptionsPageV3({limit:pageSize,offset:page*pageSize,q:query.trim(),status});
      if(requestId!==listRequestId.current)return;
      setRows(data.items);
      setMatchedTotal(data.total);
      setGlobalStats(data.stats);
      setSelected(current=>current?(data.items.find(item=>n(item.id)===n(current.id))||current):null);
    }catch(reason){
      if(requestId===listRequestId.current)setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      if(requestId===listRequestId.current&&!silent)setLoading(false);
    }
  };

  useEffect(()=>{
    const timer=window.setTimeout(()=>void load(),query.trim()?250:0);
    const interval=window.setInterval(()=>{
      if(document.visibilityState==="visible")void load(true);
    },45000);
    return()=>{window.clearTimeout(timer);window.clearInterval(interval);listRequestId.current+=1;};
  },[page,query,status]);

  useEffect(()=>{
    // Metadata is supplementary for create/edit forms and never blocks the list.
    let live=true;
    void adminApi.users().then(value=>{if(live)setUsers(value);}).catch(()=>{});
    void adminApi.plans().then(value=>{if(live)setPlans(value);}).catch(()=>{});
    void adminApi.nodes().then(value=>{if(live)setNodes(value);}).catch(()=>{});
    return()=>{live=false;};
  },[]);

  const userMap=useMemo(()=>new Map(users.map(user=>[user.id,user])),[users]);
  const planMap=useMemo(()=>new Map(plans.map(plan=>[n(plan.id),plan])),[plans]);
  const activePlan=planMap.get(draft.plan_id);
  // Search and status are applied by the database before pagination.
  const filtered=rows;
  const stats=globalStats;
  const pageCount=Math.max(1,Math.ceil(matchedTotal/pageSize));

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,close=false)=>{
    if(busy)return;setBusy(key);setError("");setOk("");
    try{await fn();setOk(label);await load(true);if(close)setModal(null);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  const planDraft=(plan:RuntimeRow|undefined)=>({
    plan_id:n(plan?.id),
    traffic_gb:planTraffic(plan),
    duration_days:planDuration(plan),
    device_limit:String(Math.max(1,n(plan?.device_limit)||1)),
    protocols:planProtocols(plan)
  });

  const openCreate=()=>{
    const plan=plans.find(item=>item.is_active!==false)||plans[0];
    const user=users.find(item=>item.role!=="admin"&&item.is_active!==false)||users.find(item=>item.role!=="admin");
    setDraft({user_id:user?.id||0,...planDraft(plan),username:"",password:""});
    setUserSearch("");setSelected(null);setConnection(null);setModal("create");
  };

  const choosePlan=(id:number)=>{
    const plan=plans.find(item=>n(item.id)===id);
    setDraft(current=>({...current,...planDraft(plan),plan_id:id}));
  };

  const createSubscription=(event:FormEvent)=>{
    event.preventDefault();
    if(!draft.user_id||!draft.plan_id){setError(pick("کاربر و پلن را انتخاب کنید","Select user and plan"));return;}
    const traffic=optionalPositive(draft.traffic_gb);const duration=optionalPositive(draft.duration_days);const device=Math.max(1,Math.trunc(optionalPositive(draft.device_limit)||1));
    void act("create",pick("اشتراک ساخته و اکانت صادر شد","Subscription created and account provisioned"),async()=>{
      await adminApi.createSubscriptionV2({user_id:draft.user_id,plan_id:draft.plan_id,node_ids:[],protocols:draft.protocols,...(traffic!==undefined?{traffic_gb:traffic}:{}),...(duration!==undefined?{duration_days:Math.trunc(duration)}:{}),device_limit:device,...(draft.username.trim()?{username:draft.username.trim()}:{}),...(draft.password.trim()?{password:draft.password.trim()}:{})});
    },true);
  };

  const openEdit=(item:RuntimeRow)=>{
    setSelected(item);setConnection(null);const limit=n(item.traffic_limit_gb)||(n(item.traffic_limit_bytes)/GB);
    setDraft({user_id:n(item.user_id),plan_id:n(item.plan_id),traffic_gb:limit>0?String(limit):"",duration_days:n(item.activation_duration_days)>0?String(n(item.activation_duration_days)):"",device_limit:String(Math.max(1,n(item.device_limit)||n(planMap.get(n(item.plan_id))?.device_limit)||1)),username:s(item.account_username),password:"",protocols:strings(item.protocols)});
    setModal("edit");
  };

  const saveEdit=(event:FormEvent)=>{
    event.preventDefault();if(!selected)return;
    const traffic=optionalPositive(draft.traffic_gb);
    void act("edit",pick("تنظیمات ذخیره شد؛ همگام‌سازی کانفیگ‌ها در صف است","Settings saved; config sync queued"),()=>adminApi.editSubscription(n(selected.id),{
      plan_id:draft.plan_id||null,
      traffic_gb:traffic??0,
      node_ids:[],
      protocols:draft.protocols,
      account_username:draft.username.trim()||undefined,
      account_password:draft.password.trim()||undefined,
    }),true);
  };
  const openTransfer=async(item:RuntimeRow)=>{
    setSelected(item);setTransferOpen(true);setTransferLoading(true);
    setTransferResellerId(0);setTransferCustomerId(0);setTransferCustomers([]);setError("");
    try{
      const resellers=await adminApi.resellersForTransfer();
      setTransferResellers(resellers.filter(row=>row.is_active===true));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setTransferLoading(false);}
  };
  const selectTransferReseller=async(id:number)=>{
    setTransferResellerId(id);setTransferCustomerId(0);setTransferCustomers([]);
    if(!id)return;
    setTransferLoading(true);setError("");
    try{
      const customers=await adminApi.resellerTransferCustomers(id);
      setTransferCustomers(customers);
      const own=customers.find(customer=>!customer.is_owner&&customer.id===n(selected?.user_id));
      if(own)setTransferCustomerId(own.id);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setTransferLoading(false);}
  };
  const submitTransfer=()=>{
    if(!selected||!transferResellerId||!transferCustomerId)return;
    const reseller=transferResellers.find(row=>n(row.id)===transferResellerId);
    if(!window.confirm(pick(`اشتراک MV-${n(selected.id)} به نمایندگی «${s(reseller?.name)}» منتقل شود؟ کانفیگ و شناسه اشتراک تغییر نمی‌کنند.`,`Transfer subscription MV-${n(selected.id)} to reseller ${s(reseller?.name)} without changing its VPN configuration?`)))return;
    void act("transfer",pick("اشتراک در پنل نماینده ثبت شد","Subscription transferred to reseller"),async()=>{await adminApi.transferSubscriptionToReseller(n(selected.id),transferResellerId,transferCustomerId);setTransferOpen(false);});
  };
  const openExtend=(item:RuntimeRow)=>{setSelected(item);setExtendDays(30);setExtendTraffic(10);setModal("extend");};
  const saveExtend=()=>{if(!selected)return;void act("extend",pick("اشتراک تمدید شد","Subscription extended"),()=>legacyAdminApi.extendSubscription(n(selected.id),{add_days:extendDays,add_traffic_gb:extendTraffic}),true);};
  const toggleStatus=async(item:RuntimeRow)=>{const activate=s(item.status).toLowerCase()!=="active";await act(`status-${item.id}`,activate?pick("اشتراک فعال شد","Subscription activated"):pick("اشتراک معلق شد","Subscription suspended"),()=>adminApi.setSubscriptionActive(n(item.id),activate));};
  const remove=async(item:RuntimeRow)=>{
    const id=n(item.id);if(id<=0)return;
    const user=userMap.get(n(item.user_id));
    if(!window.confirm(pick(`اشتراک ${user?.full_name||user?.email||`#${item.id}`} حذف شود؟ این عملیات قابل بازگشت نیست.`,`Delete subscription #${item.id}? This cannot be undone.`)))return;
    const snapshot=rows;
    setError("");setOk("");
    setRows(current=>current.filter(row=>n(row.id)!==id));
    setSelected(current=>n(current?.id)===id?null:current);
    try{
      await adminApi.deleteSubscription(id);
      setOk(pick("اشتراک حذف شد","Subscription deleted"));
    }catch(reason){
      setRows(snapshot);
      setError(reason instanceof Error?reason.message:String(reason));
      void load(true);
    }
  };

  const loadConnection=async(item:RuntimeRow)=>{setSelected(item);setConnection(null);setModal("connect");setBusy("connection");setError("");try{const data=await adminApi.subscriptionConnectionInfo(n(item.id));setConnection(data);const first=(Array.isArray(data.credentials)?data.credentials:[])[0] as RuntimeRow|undefined;setActiveProtocol(s(first?.protocol)||"cisco");}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};
  const getSubscriptionShareLink=(id:number):Promise<string>=>{
    const cached=linkCache.current.get(id);
    if(cached)return Promise.resolve(cached);
    const inFlight=linkPending.current.get(id);
    if(inFlight)return inFlight;
    const request=adminApi.subscriptionShareLink(id).catch(async(reason)=>{
      // Only old installations with a missing route use the legacy endpoint.
      // Never turn a transient error into an expensive provisioning request.
      const message=reason instanceof Error?reason.message:String(reason);
      if(!/(not found|api error 404)/i.test(message))throw reason;
      const fallback=await adminApi.subscriptionConnectionInfo(id);
      return {subscription_link:s(fallback.subscription_link)};
    }).then(data=>{
      const url=s(data.subscription_link);
      if(!url)throw new Error("Subscription link is not available");
      linkCache.current.set(id,url);
      return url;
    }).finally(()=>{linkPending.current.delete(id);});
    linkPending.current.set(id,request);
    return request;
  };
  const prefetchSubscriptionLink=(item:RuntimeRow)=>{
    const id=n(item.id);
    if(id&&!linkCache.current.has(id))void getSubscriptionShareLink(id).catch(()=>{});
  };
  const openSubscriptionLink=async(item:RuntimeRow)=>{
    const id=n(item.id);if(!id)return;
    const generation=++linkRequestGeneration.current;
    const cached=linkCache.current.get(id)||s(item.subscription_link);
    setLinkModalId(id);
    setLinkModalLink(cached);
    setLinkModalLoading(!cached);
    setLinkModalError("");
    if(cached)return;
    try{
      const url=await getSubscriptionShareLink(id);
      if(linkRequestGeneration.current===generation)setLinkModalLink(url);
    }catch(reason){
      if(linkRequestGeneration.current===generation)setLinkModalError(reason instanceof Error?reason.message:String(reason));
    }finally{
      if(linkRequestGeneration.current===generation)setLinkModalLoading(false);
    }
  };
  const closeSubscriptionLink=()=>{linkRequestGeneration.current+=1;setLinkModalId(null);setLinkModalLink("");setLinkModalLoading(false);setLinkModalError("");};
  const provision=async()=>{if(!selected)return;setBusy("provision");setError("");try{await adminApi.provisionSubscription(n(selected.id));setConnection(await adminApi.subscriptionConnectionInfo(n(selected.id)));setOk(pick("اطلاعات اتصال ساخته شد","Connection info provisioned"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};
  const refreshPasswords=async()=>{if(!selected)return;setBusy("passwords");setError("");try{await adminApi.refreshSubscriptionPasswords(n(selected.id));setConnection(await adminApi.subscriptionConnectionInfo(n(selected.id)));setOk(pick("رمز Cisco/L2TP بازسازی شد","Cisco/L2TP password refreshed"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};

  const userMatches=users.filter(user=>user.role!=="admin"&&(!userSearch.trim()||`${user.full_name||""} ${user.email||""} ${user.phone||""}`.toLowerCase().includes(userSearch.trim().toLowerCase()))).slice(0,30);
  const credentials=connection&&Array.isArray(connection.credentials)?connection.credentials as RuntimeRow[]:[];
  const account=connection&&connection.account&&typeof connection.account==="object"?connection.account as RuntimeRow:null;
  const shareLink=absoluteLink(s(connection?.subscription_link));
  const selectedCredential=credentials.find(item=>s(item.protocol)===activeProtocol)||credentials[0]||null;
  const selectedItems=selectedCredential?list(selectedCredential.items):[];

  const trafficCell=(item:RuntimeRow)=>{const limit=n(item.traffic_limit_bytes);const used=n(item.traffic_used_bytes);if(limit<=0)return <div className="user-cell"><b dir="ltr">{formatBytes(used)} / {pick("نامحدود","Unlimited")}</b><small>∞</small></div>;const percent=Math.min(100,Math.round(used/limit*100));return <div className="user-cell"><b dir="ltr">{formatBytes(used)} / {formatBytes(limit)}</b><small>{percent.toLocaleString("fa-IR")}٪</small></div>;};
  const expiryCell=(item:RuntimeRow)=>{if(item.duration_unlimited===true)return pick("نامحدود","Unlimited");if(item.expires_at)return formatDate(item.expires_at);const days=n(item.activation_duration_days);if(days>0)return pick(`${days.toLocaleString("fa-IR")} روز از اولین اتصال`,`${days} days from first connection`);return "—";};

  return <Shell active="/admin/subscriptions"><div className="page legacy-subscriptions-page">
    <div className="page-head"><div><h1>{pick("اشتراک‌ها","Subscriptions")}</h1><small>{pick("مدیریت اشتراک، تمدید، وضعیت و سابلینک","Subscriptions, renewals, status and public links")}</small></div><button className="primary" onClick={openCreate}>＋ {pick("اشتراک جدید","New subscription")}</button></div>
    <Notice error={error} ok={ok}/>

    <div className="stats dashboard-stats subscription-stat-filters" aria-label={pick("فیلتر اشتراک‌ها بر اساس وضعیت","Filter subscriptions by status")}>
      {([
        ["all",pick("کل اشتراک‌ها","Total subscriptions"),stats.total],
        ["active",pick("اشتراک‌های فعال","Active subscriptions"),stats.active],
        ["expired",pick("منقضی","Expired"),stats.expired],
        ["suspended",pick("معلق","Suspended"),stats.suspended],
        ["online",pick("آنلاین‌ها","Online now"),stats.online??0],
      ] as const).map(([key,label,count])=>(
        <button
          key={key}
          type="button"
          className={`subscription-stat-filter ${status===key?"is-selected":""}`}
          aria-pressed={status===key}
          title={pick(`نمایش ${label}`,`Show ${label.toLowerCase()}`)}
          onClick={()=>{setStatus(key);setPage(0);}}
        >
          <Stat label={label} value={count.toLocaleString("fa-IR")}/>
        </button>
      ))}
    </div>
    <style>{`
      .subscription-stat-filters{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}
      .subscription-stat-filter{border:2px solid transparent;border-radius:18px;background:transparent;padding:0;color:inherit;text-align:inherit;cursor:pointer;min-width:0;transition:border-color .2s,transform .2s}
      .subscription-stat-filter:hover{transform:translateY(-2px);border-color:rgba(59,130,246,.45)}
      .subscription-stat-filter.is-selected{border-color:#3b82f6}
      .subscription-stat-filter:focus-visible{outline:3px solid #60a5fa;outline-offset:2px}
      .subscription-stat-filter .stat{height:100%;margin:0}
      @media(max-width:850px){.subscription-stat-filters{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:420px){.subscription-stat-filters{grid-template-columns:1fr}}
    `}</style>

    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={query} onChange={event=>{setQuery(event.target.value);setPage(0);}} placeholder={pick("نام، ایمیل، نام کاربری یا کد اشتراک…","Name, email, username or subscription code…")}/></label><select value={status} onChange={event=>{setStatus(event.target.value as typeof status);setPage(0);}}><option value="all">{pick("همه","All")}</option><option value="active">{pick("فعال","Active")}</option><option value="expired">{pick("منقضی","Expired")}</option><option value="suspended">{pick("معلق","Suspended")}</option><option value="online">{pick("آنلاین‌ها","Online now")}</option><option value="pending">{pick("در انتظار","Pending")}</option></select><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button></div>
      {loading&&rows.length===0?<div className="runtime-loading">…</div>:<div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>{pick("پلن","Plan")}</th><th>{pick("نام کاربری","Username")}</th><th>{pick("ترافیک","Traffic")}</th><th>{pick("ساخت","Created")}</th><th>{pick("انقضا","Expires")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(item=>{const user=userMap.get(n(item.user_id));const plan=planMap.get(n(item.plan_id));return <tr key={n(item.id)}><td><div className="user-cell"><b>{user?.full_name||s(item.customer_name)||`#${item.user_id}`}</b><small dir="ltr">{user?.email||s(item.customer_email)||"—"}</small></div></td><td><div className="user-cell"><b>{s(item.plan_name)||s(plan?.name)||`#${item.plan_id}`}</b><small dir="ltr">MV-{n(item.id)}</small></div></td><td><div className="secret-row"><b dir="ltr">{s(item.account_username)||"—"}</b>{s(item.account_username)&&<button className="mini-btn" onClick={()=>copy(s(item.account_username))}>{pick("کپی","Copy")}</button>}</div></td><td>{trafficCell(item)}</td><td>{formatDate(item.created_at)}</td><td>{expiryCell(item)}</td><td><Badge tone={tone(item.status)}>{statusLabel(item.status)}</Badge></td><td><div className="row-actions"><button className="danger" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button><button disabled={!!busy} onClick={()=>void toggleStatus(item)}>{s(item.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button onClick={()=>openEdit(item)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openExtend(item)}>{pick("تمدید","Renew")}</button><button className="ghost" disabled={!!busy} onClick={()=>void openTransfer(item)}>{pick("انتقال به نماینده","Transfer to reseller")}</button><button className="primary-soft" onMouseEnter={()=>prefetchSubscriptionLink(item)} onFocus={()=>prefetchSubscriptionLink(item)} onClick={()=>void openSubscriptionLink(item)}>{pick("سابلینک","Sub-link")}</button></div></td></tr>;})}</tbody></table>{filtered.length===0&&<div className="runtime-empty">{pick("اشتراکی پیدا نشد","No subscriptions found")}</div>}</div>}
    </Card>
    <div className="runtime-toolbar" style={{justifyContent:"space-between",marginTop:12}}>
      <span>{matchedTotal.toLocaleString("fa-IR")} {pick("نتیجه","results")} · {pick("صفحه","Page")} {(page+1).toLocaleString("fa-IR")} / {pageCount.toLocaleString("fa-IR")}</span>
      <div className="row-actions">
        <button type="button" className="ghost" disabled={loading||page===0} onClick={()=>setPage(v=>Math.max(0,v-1))}>{pick("قبلی","Previous")}</button>
        <button type="button" className="ghost" disabled={loading||page+1>=pageCount} onClick={()=>setPage(v=>v+1)}>{pick("بعدی","Next")}</button>
      </div>
    </div>

    {modal==="create"&&<Modal title={pick("ساخت اشتراک","Create subscription")} onClose={()=>!busy&&setModal(null)} wide>
      <form className="subscription-create-form" onSubmit={createSubscription}>
        <div className="setting-grid compact-create-grid">
          <label className="field"><span>{pick("جستجوی کاربر","User search")}</span><input value={userSearch} onChange={event=>setUserSearch(event.target.value)} placeholder={pick("نام، ایمیل یا موبایل…","Name, email or mobile…")}/></label>
          <label className="field"><span>{pick("کاربر","User")}</span><select value={draft.user_id} onChange={event=>setDraft(current=>({...current,user_id:Number(event.target.value)}))}><option value={0}>{pick("انتخاب کاربر","Select user")}</option>{userMatches.map(user=><option key={user.id} value={user.id}>{user.full_name||user.email||`#${user.id}`} · {user.phone||user.email||"—"}</option>)}</select></label>
          <label className="field"><span>{pick("پلن","Plan")}</span><select value={draft.plan_id} onChange={event=>choosePlan(Number(event.target.value))}><option value={0}>{pick("انتخاب پلن","Select plan")}</option>{plans.filter(plan=>plan.is_active!==false).map(plan=><option key={n(plan.id)} value={n(plan.id)}>{s(plan.name)||`#${plan.id}`}</option>)}</select></label>
        </div>

        {activePlan&&<div className="subscription-plan-summary"><b>{s(activePlan.name)}</b><span>{n(activePlan.traffic_gb)>0?`${n(activePlan.traffic_gb).toLocaleString("fa-IR")} GB`:pick("حجم نامحدود","Unlimited traffic")}</span><span>{n(activePlan.duration_days)>0?pick(`${n(activePlan.duration_days).toLocaleString("fa-IR")} روز`,`${n(activePlan.duration_days)} days`):pick("زمان نامحدود","Unlimited duration")}</span><span>{pick(`${Math.max(1,n(activePlan.device_limit)||1).toLocaleString("fa-IR")} اتصال`,`${Math.max(1,n(activePlan.device_limit)||1)} devices`)}</span><span>{planProtocols(activePlan).map(key=>protocolLabels[key]).join(" · ")||"—"}</span></div>}

        <div className="setting-grid compact-create-grid">
          <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input inputMode="decimal" type="number" min={0.1} step="0.1" value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:event.target.value}))} placeholder={pick("خالی = نامحدود","empty = unlimited")}/><small>{pick("از پلن پر می‌شود؛ برای نامحدود پاکش کنید","Filled from plan; clear for unlimited")}</small></label>
          <label className="field"><span>{pick("مدت روز","Duration days")}</span><input inputMode="numeric" type="number" min={1} step={1} value={draft.duration_days} onChange={event=>setDraft(current=>({...current,duration_days:event.target.value}))} placeholder={pick("خالی = نامحدود","empty = unlimited")}/><small>{pick("از پلن پر می‌شود؛ برای نامحدود پاکش کنید","Filled from plan; clear for unlimited")}</small></label>
          <label className="field"><span>{pick("اتصال همزمان","Concurrent devices")}</span><input inputMode="numeric" type="number" min={1} step={1} value={draft.device_limit} onChange={event=>setDraft(current=>({...current,device_limit:event.target.value}))}/></label>
          <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" autoComplete="off" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
          <label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
        </div>
        <div className="modalActions"><button type="button" className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="create"||!draft.user_id||!draft.plan_id}>{busy==="create"?pick("در حال ساخت…","Creating…"):pick("ساخت و صدور اکانت","Create & provision")}</button></div>
      </form>
    </Modal>}

    {modal==="edit"&&selected&&<Modal title={pick("ویرایش اشتراک","Edit subscription")} sub={`MV-${n(selected.id)}`} onClose={()=>!busy&&setModal(null)} wide>
      <Notice error={error} ok={ok}/>
      <form onSubmit={saveEdit}><div className="setting-grid"><label className="field"><span>{pick("پلن","Plan")}</span><select value={draft.plan_id} onChange={event=>setDraft(current=>({...current,plan_id:Number(event.target.value)}))}><option value={0} disabled={n(selected.plan_id)>0}>{pick("اشتراک دستی (بدون پلن)","Manual subscription (no plan)")}</option>{plans.map(plan=><option key={n(plan.id)} value={n(plan.id)}>{s(plan.name)||`#${plan.id}`}</option>)}</select></label><label className="field"><span>{pick("حجم کل GB","Total traffic GB")}</span><input type="number" min={0} step="0.1" value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:event.target.value}))} placeholder={pick("خالی = نامحدود","empty = unlimited")}/></label><label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))}/></label><label className="field"><span>{pick("رمز جدید","New password")}</span><input dir="ltr" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))} placeholder={pick("خالی = بدون تغییر","empty = unchanged")}/></label></div><div className="manage-section-head"><div><b>{pick("پروتکل‌ها","Protocols")}</b><small>{draft.protocols.length.toLocaleString("fa-IR")} {pick("انتخاب","selected")}</small></div></div><div className="protocol-toggle-grid">{protocolKeys.map(key=>{const modern=!classicProtocolSet.has(key);const supported=modern||nodes.some(node=>node.status==="online"&&Boolean((node as unknown as RuntimeRow)[`enable_${key}`]));const checked=draft.protocols.includes(key);return <label key={key} className="toggle module-toggle compact-toggle"><span>{protocolLabels[key]}<small>{modern?pick("وضعیت Runtime هنگام ذخیره بررسی می‌شود","Runtime readiness is checked on save"):supported?pick("قابل استفاده","Available"):pick("روی سرور آنلاین فعال نیست","Not enabled on an online server")}</small></span><input type="checkbox" disabled={!supported} checked={checked} onChange={event=>setDraft(current=>({...current,protocols:event.target.checked?[...new Set([...current.protocols,key])]:current.protocols.filter(item=>item!==key)}))}/><i/></label>;})}</div><div className="modalActions"><button type="button" className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="edit"||(!draft.plan_id&&n(selected.plan_id)>0)||!draft.protocols.length}>{busy==="edit"?"…":pick("ذخیره تغییرات","Save changes")}</button></div></form>
    </Modal>}

    {transferOpen&&selected&&<Modal title={pick("انتقال اشتراک به نماینده","Transfer subscription to reseller")} sub={`MV-${n(selected.id)} · ${s(selected.account_username)}`} onClose={()=>!busy&&setTransferOpen(false)}>
      <p className="muted">{pick("این انتقال فقط مدیریت اشتراک را به نماینده واگذار می‌کند؛ شناسه، حجم مصرف‌شده، تاریخ انقضا و کانفیگ‌ها تغییر نمی‌کنند. برای اشتراک‌های ساخته‌شده زیر حساب ادمین، یک مشتری از نمایندگی انتخاب کنید؛ حساب ادمین نباید به نماینده اضافه شود.","This transfers management only. Account ID, usage, expiry and configs remain unchanged. For admin-owned accounts, select an existing reseller customer; do not expose the admin identity.")}</p>
      <div className="setting-grid">
        <label className="field"><span>{pick("نماینده مقصد","Destination reseller")}</span>
          <select value={transferResellerId} disabled={transferLoading||!!busy} onChange={event=>void selectTransferReseller(Number(event.target.value))}>
            <option value={0}>{pick("انتخاب نماینده","Select reseller")}</option>
            {transferResellers.map(row=><option key={n(row.id)} value={n(row.id)}>{s(row.name)||s(row.brand_name)||`#${row.id}`} · {s(row.code)}</option>)}
          </select>
        </label>
        <label className="field"><span>{pick("مشتری ثبت‌شده در نمایندگی","Reseller customer")}</span>
          <select value={transferCustomerId} disabled={!transferResellerId||transferLoading||!!busy} onChange={event=>setTransferCustomerId(Number(event.target.value))}>
            <option value={0}>{pick("انتخاب مشتری","Select customer")}</option>
            {transferCustomers.map(customer=><option key={customer.id} value={customer.id}>{customer.name}{customer.is_owner?` · ${pick("حساب نماینده","Reseller owner")}`:""}</option>)}
          </select>
        </label>
      </div>
      {transferResellerId&&!transferLoading&&!transferCustomers.length?<p className="runtime-error">{pick("مشتری فعالی در این نمایندگی وجود ندارد. ابتدا از بخش مشتریان نماینده یک مشتری ایجاد کنید.","No active customer found for this reseller. Create a customer first.")}</p>:null}
      <div className="modalActions"><button className="ghost" disabled={!!busy} onClick={()=>setTransferOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={!!busy||transferLoading||!transferResellerId||!transferCustomerId} onClick={submitTransfer}>{busy==="transfer"?pick("در حال انتقال…","Transferring…"):pick("تأیید انتقال","Confirm transfer")}</button></div>
    </Modal>}
    {modal==="extend"&&selected&&<Modal title={pick("تمدید اشتراک","Renew subscription")} sub={`MV-${n(selected.id)} · ${expiryCell(selected)}`} onClose={()=>!busy&&setModal(null)}><div className="setting-grid"><label className="field"><span>{pick("روز اضافه","Add days")}</span><input type="number" min={0} value={extendDays} onChange={event=>setExtendDays(Math.max(0,Number(event.target.value)||0))}/></label><label className="field"><span>{pick("حجم اضافه GB","Add traffic GB")}</span><input type="number" min={0} step="0.1" value={extendTraffic} onChange={event=>setExtendTraffic(Math.max(0,Number(event.target.value)||0))}/></label></div><div className="modalActions"><button className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="extend"||(!extendDays&&!extendTraffic)} onClick={saveExtend}>{busy==="extend"?"…":pick("اعمال تمدید","Apply renewal")}</button></div></Modal>}

    {modal==="connect"&&selected&&<Modal title={pick("اطلاعات اتصال","Connection information")} sub={`MV-${n(selected.id)}`} onClose={()=>setModal(null)} wide>
      <Notice error={error} ok={ok}/>
      {busy==="connection"?<div className="runtime-loading">…</div>:<>
        <div className="stats dashboard-stats modal-stats"><Stat label={pick("نام کاربری","Username")} value={s(account?.username||selected.account_username)||"—"}/><Stat label={pick("پروتکل‌ها","Protocols")} value={String(credentials.length)}/><Stat label={pick("سرورها","Servers")} value={String(credentials.reduce((sum,item)=>sum+list(item.items).length,0))}/></div>
        <div className="manage-actions"><button className="primary" disabled={!!busy} onClick={()=>void provision()}>{busy==="provision"?"…":pick("ساخت/بازسازی اتصال","Provision connection")}</button><button className="ghost" disabled={!!busy} onClick={()=>void refreshPasswords()}>{busy==="passwords"?"…":pick("رمز جدید Cisco/L2TP","Refresh Cisco/L2TP password")}</button>{shareLink&&<><button className="ghost" onClick={()=>copy(shareLink)}>{pick("کپی سابلینک","Copy sub-link")}</button><a className="ghost" href={shareLink} target="_blank" rel="noreferrer">{pick("صفحه اتصال","Connection page")}</a></>}</div>
        <div className="setting-grid"><div className="setting-box"><small>{pick("نام کاربری اکانت","Account username")}</small><div className="secret-row"><b dir="ltr">{s(account?.username||selected.account_username)||"—"}</b>{s(account?.username||selected.account_username)&&<button className="mini-btn" onClick={()=>copy(s(account?.username||selected.account_username))}>{pick("کپی","Copy")}</button>}</div></div><div className="setting-box"><small>{pick("رمز عبور اکانت","Account password")}</small><div className="secret-row"><b dir="ltr">{showPassword?s(account?.password)||"—":"••••••••"}</b><button className="mini-btn" onClick={()=>setShowPassword(value=>!value)}>{showPassword?pick("مخفی","Hide"):pick("نمایش","Show")}</button>{s(account?.password)&&<button className="mini-btn" onClick={()=>copy(s(account?.password))}>{pick("کپی","Copy")}</button>}</div></div></div>
        {credentials.length===0?<div className="runtime-empty">{pick("هنوز اطلاعات اتصال ساخته نشده است. «ساخت/بازسازی اتصال» را بزنید.","Connection data has not been provisioned yet.")}</div>:<><div className="runtime-tabs">{credentials.map(item=><button type="button" key={s(item.protocol)} className={activeProtocol===s(item.protocol)?"active":""} onClick={()=>setActiveProtocol(s(item.protocol))}>{protocolLabels[s(item.protocol)]||s(item.protocol)}</button>)}</div><div className="manage-card-section"><div className="manage-section-head"><div><b>{protocolLabels[s(selectedCredential?.protocol)]||s(selectedCredential?.protocol)}</b><small>{selectedItems.length.toLocaleString("fa-IR")} {pick("سرور قابل استفاده","available servers")}</small></div></div><div className="protocol-toggle-grid">{selectedItems.map((item,index)=>{const protocol=s(selectedCredential?.protocol);const server=s(item.server||item.server_ip);const port=s(item.port||item.ports);const username=s(item.username||selectedCredential?.username||account?.username);const password=s(item.password||account?.password);const config=s(item.config);const uri=s(item.uri);const psk=s(item.psk);const filename=s(item.filename)||`${protocol}-${n(selected.id)}-${index+1}.${protocol==="openvpn"?"ovpn":protocol==="wireguard"?"conf":"txt"}`;return <div className="setting-box" key={`${protocol}-${n(item.node_id)}-${index}`}><div className="card-head"><div><b>{s(item.node)||`${pick("سرور","Server")} ${index+1}`}</b><small dir="ltr">{server}{port?`:${port}`:""}</small></div><Badge tone="ok">{pick("آماده","Ready")}</Badge></div><div className="setting-grid">{server&&<div><small>{pick("سرور","Server")}</small><div className="secret-row"><code dir="ltr">{server}</code><button className="mini-btn" onClick={()=>copy(server)}>{pick("کپی","Copy")}</button></div></div>}{port&&<div><small>{pick("پورت / Transport","Port / Transport")}</small><b dir="ltr">{port}{s(item.transport)?` · ${s(item.transport)}`:""}</b></div>}{username&&<div><small>{pick("نام کاربری","Username")}</small><div className="secret-row"><code dir="ltr">{username}</code><button className="mini-btn" onClick={()=>copy(username)}>{pick("کپی","Copy")}</button></div></div>}{password&&<div><small>{pick("رمز عبور","Password")}</small><div className="secret-row"><code dir="ltr">{showPassword?password:"••••••••"}</code><button className="mini-btn" onClick={()=>copy(password)}>{pick("کپی","Copy")}</button></div></div>}{psk&&<div><small>PSK</small><div className="secret-row"><code dir="ltr">{psk}</code><button className="mini-btn" onClick={()=>copy(psk)}>{pick("کپی","Copy")}</button></div></div>}{s(item.address)&&<div><small>{pick("آدرس WireGuard","WireGuard address")}</small><code dir="ltr">{s(item.address)}</code></div>}{s(item.uuid)&&<div><small>UUID</small><div className="secret-row"><code dir="ltr">{s(item.uuid)}</code><button className="mini-btn" onClick={()=>copy(s(item.uuid))}>{pick("کپی","Copy")}</button></div></div>}</div>{(config||uri)&&<div className="manage-actions">{config&&<><button className="primary-soft" onClick={()=>copy(config)}>{pick("کپی کانفیگ","Copy config")}</button><button className="ghost" onClick={()=>downloadText(filename,config)}>{pick("دانلود فایل","Download file")}</button></>}{uri&&<button className="primary-soft" onClick={()=>copy(uri)}>{pick("کپی لینک V2Ray","Copy V2Ray URI")}</button>}</div>}{(protocol==="wireguard"&&config||protocol==="v2ray"&&uri)&&<div style={{display:"grid",placeItems:"center",marginTop:12}}><div style={{background:"white",padding:12,borderRadius:14}}><QRCodeSVG value={protocol==="wireguard"?config:uri} size={160}/></div></div>}</div>;})}</div></div></>}
      </>}
    </Modal>}

    <SubscriptionLinkDeliveryModal
      open={linkModalId!==null}
      link={linkModalLink}
      reference={linkModalId?`MV-${linkModalId}`:""}
      loading={linkModalLoading}
      error={linkModalError}
      onClose={closeSubscriptionLink}
    />
  </div></Shell>;
}