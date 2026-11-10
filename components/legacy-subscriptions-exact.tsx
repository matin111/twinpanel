"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {QRCodeSVG} from "qrcode.react";
import {Badge,Card,Shell,Stat} from "./ui";
import {SubscriptionLinkDeliveryModal} from "./subscription-link-delivery-modal";
import {AppCredentialDeliveryCard} from "./app-credential-delivery-card";
import {adminApi,AdminNode,AdminUser,RuntimeRow} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const classicProtocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"] as const;
const modernProtocolKeys=["hysteria2","tuic","anytls","naive","shadowtls","snell","mieru","trusttunnel","amneziawg","sudoku","socks5"] as const;
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
  sudoku:"Sudoku",
  socks5:"SOCKS5 Proxy"
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
  const [editResetUsage,setEditResetUsage]=useState(false);
  const [resetTarget,setResetTarget]=useState<RuntimeRow|null>(null);
  const [extendResetUsage,setExtendResetUsage]=useState(false);
  const [extendResetDate,setExtendResetDate]=useState(false);
  const [linkModalId,setLinkModalId]=useState<number|null>(null);
  const [appDeliverySubscriptionId,setAppDeliverySubscriptionId]=useState<number|null>(null);
  const [linkModalLink,setLinkModalLink]=useState("");
  const [linkModalLoading,setLinkModalLoading]=useState(false);
  const [linkModalError,setLinkModalError] = useState("");
  const [transferOpen,setTransferOpen]=useState(false);
  const [transferMode,setTransferMode]=useState<"user"|"reseller">("reseller");
  const [transferUserId,setTransferUserId]=useState(0);
  const [transferUserSearch,setTransferUserSearch]=useState("");
  const [transferUserMatches,setTransferUserMatches]=useState<AdminUser[]>([]);
  const [resellerFilterId,setResellerFilterId]=useState(0);
  const [transferResellers,setTransferResellers]=useState<RuntimeRow[]>([]);
  const [transferCustomers,setTransferCustomers]=useState<Array<{id:number;name:string;email?:string|null;is_owner:boolean}>>([]);
  const [transferResellerId,setTransferResellerId]=useState(0);
  const [transferCustomerId,setTransferCustomerId]=useState(0);
  const [transferCustomerSearch,setTransferCustomerSearch]=useState("");
  const [transferLoading,setTransferLoading]=useState(false);
  // Share URLs are stable for a subscription; cache and dedupe requests so
  // opening the modal does not wait for heavyweight connection-info/provisioning.
  const linkCache=useRef(new Map<number,string>());
  const linkPending=useRef(new Map<number,Promise<string>>());
  const linkRequestGeneration=useRef(0);

  const [draft,setDraft]=useState<Draft>({user_id:0,plan_id:0,traffic_gb:"",duration_days:"",device_limit:"1",username:"",password:"",protocols:[]});
  const [editExpiry,setEditExpiry]=useState("");

  const load=async(silent=false)=>{
    const requestId=++listRequestId.current;
    if(!silent)setLoading(true);
    setError("");
    try{
      const data=await adminApi.subscriptionsPageV3({limit:pageSize,offset:page*pageSize,q:query.trim(),status,reseller_id:resellerFilterId});
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
  },[page,query,status,resellerFilterId]);

  useEffect(()=>{
    // Metadata is supplementary for create/edit forms and never blocks the list.
    let live=true;
    void adminApi.users().then(value=>{if(live)setUsers(value);}).catch(()=>{});
    void adminApi.plans().then(value=>{if(live)setPlans(value);}).catch(()=>{});
    void adminApi.nodes().then(value=>{if(live)setNodes(value);}).catch(()=>{});
    void adminApi.resellersForTransfer().then(value=>{if(live)setTransferResellers(value);}).catch(()=>{});
    return()=>{live=false;};
  },[]);

  const userMap=useMemo(()=>new Map(users.map(user=>[user.id,user])),[users]);
  const planMap=useMemo(()=>new Map(plans.map(plan=>[n(plan.id),plan])),[plans]);
  const activePlan=planMap.get(draft.plan_id);
  // Search and status are applied by the database before pagination.
  const filtered=rows;
  const stats=globalStats;
  const pageCount=Math.max(1,Math.ceil(matchedTotal/pageSize));
  // Up to ten visible pages, sliding around the current page and clamped to bounds.
  const pageWindowStart=Math.max(0,Math.min(page-4,pageCount-10));
  const visiblePages=Array.from({length:Math.min(10,pageCount)},(_,index)=>pageWindowStart+index);
  const changePage=(next:number)=>{
    if(loading||next<0||next>=pageCount||next===page)return;
    setPage(next);
  };

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,close=false)=>{
    if(busy)return;setBusy(key);setError("");setOk("");
    try{await fn();setOk(label);if(close&&key==="edit"){setModal(null);void load(true);}else{await load(true);if(close)setModal(null);}}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
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
      await adminApi.createSubscriptionV2({user_id:draft.user_id,plan_id:draft.plan_id,node_ids:[],protocols:draft.protocols,...(traffic!==undefined?{traffic_gb:traffic}:{}),duration_days:Math.trunc(duration??0),device_limit:device,...(draft.username.trim()?{username:draft.username.trim()}:{}),...(draft.password.trim()?{password:draft.password.trim()}:{})});
    },true);
  };

  const openEdit=(item:RuntimeRow)=>{
    setSelected(item);setConnection(null);const limit=n(item.traffic_limit_gb)||(n(item.traffic_limit_bytes)/GB);
    setDraft({user_id:n(item.user_id),plan_id:n(item.plan_id),traffic_gb:limit>0?String(limit):"",duration_days:n(item.activation_duration_days)>0?String(n(item.activation_duration_days)):"",device_limit:String(item.device_limit!==undefined&&item.device_limit!==null?n(item.device_limit):n(planMap.get(n(item.plan_id))?.device_limit)||1),username:s(item.account_username),password:"",protocols:strings(item.protocols)});
    setEditExpiry(item.expires_at?String(item.expires_at).slice(0,10):"");
    setEditResetUsage(false);
    setModal("edit");
  };

  const confirmUsageReset=()=>{
    if(!resetTarget||busy)return;
    const subscriptionId=n(resetTarget.id);
    if(!subscriptionId)return;
    void act(
      "reset-usage",
      pick("حجم مصرفی اشتراک صفر شد؛ حجم کل و تاریخ انقضا تغییر نکردند","Subscription usage was reset; total quota and expiry were unchanged"),
      async()=>{
        await legacyAdminApi.extendSubscription(subscriptionId,{
          add_traffic_gb:0,add_days:0,reset_usage:true,reset_date:false,
        });
        setResetTarget(null);
      },
    );
  };

  const saveEdit=(event:FormEvent)=>{
    event.preventDefault();if(!selected)return;
    if(editResetUsage&&!window.confirm(pick("مصرف ثبت‌شده اشتراک صفر شود؟ سوابق حسابداری برای جلوگیری از ثبت دوباره مصرف حفظ می‌شوند.","Reset this subscription's billed usage to zero? Historical accounting remains for replay protection.")))return;
    const traffic=optionalPositive(draft.traffic_gb);
    const originalDays=n(selected.activation_duration_days)>0?String(Math.trunc(n(selected.activation_duration_days))):"";
    const durationChanged=draft.duration_days.trim()!==originalDays;
    void act("edit",pick("تنظیمات ذخیره شد؛ همگام‌سازی کانفیگ‌ها در صف است","Settings saved; config sync queued"),()=>adminApi.editSubscription(n(selected.id),{
      plan_id:draft.plan_id||null,
      traffic_gb:traffic??0,
      reset_usage:editResetUsage,
      device_limit:Math.max(0,Math.min(1000,Math.trunc(Number(draft.device_limit)||0))),
      ...(durationChanged?{duration_days:Math.max(0,Math.min(3650,Math.trunc(Number(draft.duration_days)||0)))}:{}),
      ...(editExpiry&&editExpiry!==String(selected.expires_at||"").slice(0,10)?{expires_at:new Date(editExpiry+"T23:59:59").toISOString()}:{}),
      node_ids:[],
      protocols:draft.protocols,
      account_username:draft.username.trim()||undefined,
      account_password:draft.password.trim()||undefined,
    }),true);
  };
  const openTransfer=async(item:RuntimeRow)=>{
    setSelected(item);setTransferOpen(true);setTransferLoading(true);
    setTransferMode("reseller");setTransferUserId(0);setTransferUserSearch("");
    setTransferResellerId(0);setTransferCustomerId(0);setTransferCustomerSearch("");setTransferCustomers([]);setError("");
    try{
      const resellers=await adminApi.resellersForTransfer();
      setTransferResellers(resellers);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setTransferLoading(false);}
  };

  useEffect(()=>{
    if(!transferOpen||transferMode!=="user")return;
    let live=true;
    const timer=window.setTimeout(()=>{
      void adminApi.usersFastPage({limit:50,offset:0,q:transferUserSearch.trim()})
        .then(result=>{if(live)setTransferUserMatches(result.items.filter(user=>user.role!=="admin"&&user.is_active!==false));})
        .catch(reason=>{if(live)setError(reason instanceof Error?reason.message:String(reason));});
    },transferUserSearch.trim()?300:0);
    return()=>{live=false;window.clearTimeout(timer);};
  },[transferOpen,transferMode,transferUserSearch]);
  const selectTransferReseller=async(id:number)=>{
    setTransferResellerId(id);setTransferCustomerId(0);setTransferCustomerSearch("");setTransferCustomers([]);
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
  useEffect(()=>{
    if(!transferOpen||transferMode!=="reseller"||!transferResellerId)return;
    let live=true;
    const timer=window.setTimeout(()=>{
      void adminApi.resellerTransferCustomers(transferResellerId,transferCustomerSearch.trim())
        .then(customers=>{if(live)setTransferCustomers(customers);})
        .catch(reason=>{if(live)setError(reason instanceof Error?reason.message:String(reason));});
    },transferCustomerSearch.trim()?300:0);
    return()=>{live=false;window.clearTimeout(timer);};
  },[transferOpen,transferMode,transferResellerId,transferCustomerSearch]);
  const submitTransfer=()=>{
    if(!selected)return;
    if(transferMode==="user"){
      if(!transferUserId)return;
      const user=transferUserMatches.find(item=>item.id===transferUserId);
      if(!window.confirm(pick(`مالکیت اشتراک MV-${n(selected.id)} به «${user?.full_name||user?.email||transferUserId}» منتقل شود؟ دسترسی نماینده قبلی قطع می‌شود ولی کانفیگ تغییر نمی‌کند.`,`Transfer ownership of MV-${n(selected.id)} to ${user?.full_name||user?.email||transferUserId}? Previous reseller management is detached; VPN configs stay unchanged.`)))return;
      void act("transfer",pick("مالکیت اکانت به کاربر منتقل شد","Subscription ownership transferred"),async()=>{
        await adminApi.transferSubscriptionToUser(n(selected.id),transferUserId);
        setTransferOpen(false);
      });
      return;
    }
    if(!transferResellerId||!transferCustomerId)return;
    const reseller=transferResellers.find(row=>n(row.id)===transferResellerId);
    if(!window.confirm(pick(`مالکیت اشتراک MV-${n(selected.id)} به مشتری انتخاب‌شده و مدیریت آن به نمایندگی «${s(reseller?.name)}» منتقل شود؟ کانفیگ و شناسه اشتراک تغییر نمی‌کنند.`,`Transfer ownership and management of MV-${n(selected.id)} to reseller ${s(reseller?.name)} and its selected customer? VPN configuration stays unchanged.`)))return;
    void act("transfer",pick("مالکیت و مدیریت اشتراک منتقل شد","Subscription ownership and management transferred"),async()=>{
      await adminApi.transferSubscriptionToReseller(n(selected.id),transferResellerId,transferCustomerId);
      setTransferOpen(false);
    });
  };
  const openExtend=(item:RuntimeRow)=>{setSelected(item);setExtendDays(30);setExtendTraffic(10);setExtendResetUsage(false);setExtendResetDate(false);setModal("extend");};
  const saveExtend=()=>{
    if(!selected)return;
    if(extendResetDate&&extendDays<=0){setError(pick("برای ریست تاریخ، مدت دوره جدید را وارد کنید.","Enter a new duration to reset the expiry date."));return;}
    if((extendResetUsage||extendResetDate)&&!window.confirm(pick("ریست‌های انتخاب‌شده روی اشتراک اعمال شوند؟ ریست تاریخ، اعتبار را از همین لحظه و برای روزهای واردشده شروع می‌کند.","Apply selected resets? Date reset starts a fresh period now for the entered days.")))return;
    void act("extend",pick("تمدید و تنظیمات ریست اعمال شد","Renewal and reset options applied"),()=>legacyAdminApi.extendSubscription(n(selected.id),{add_days:extendDays,add_traffic_gb:extendTraffic,reset_usage:extendResetUsage,reset_date:extendResetDate}),true);
  };
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
  const expiryCell=(item:RuntimeRow)=>{
    if(item.expires_at){
      const expires=new Date(String(item.expires_at));
      const remaining=Number.isFinite(expires.getTime())?Math.max(0,Math.ceil((expires.getTime()-Date.now())/86400000)):null;
      return <div className="user-cell"><b>{formatDate(item.expires_at)}</b>{remaining!==null&&<small>{remaining>0?pick(`${remaining.toLocaleString("fa-IR")} روز باقی‌مانده`,`${remaining} days remaining`):pick("منقضی شده","Expired")}</small>}</div>;
    }
    const days=n(item.activation_duration_days)||n(planMap.get(n(item.plan_id))?.duration_days);
    if(item.duration_unlimited===true||days<=0)return pick("نامحدود","Unlimited");
    return <div className="user-cell"><b>{pick(`${days.toLocaleString("fa-IR")} روز`,`${days} days`)}</b><small>{pick("از اولین اتصال","From first connection")}</small></div>;
  };

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
      <div className="runtime-toolbar"><label>⌕ <input value={query} onChange={event=>{setQuery(event.target.value);setPage(0);}} placeholder={pick("نام، ایمیل، نام کاربری یا کد اشتراک…","Name, email, username or subscription code…")}/></label><select value={status} onChange={event=>{setStatus(event.target.value as typeof status);setPage(0);}}><option value="all">{pick("همه","All")}</option><option value="active">{pick("فعال","Active")}</option><option value="expired">{pick("منقضی","Expired")}</option><option value="suspended">{pick("معلق","Suspended")}</option><option value="online">{pick("آنلاین‌ها","Online now")}</option><option value="pending">{pick("در انتظار","Pending")}</option></select><select aria-label={pick("فیلتر نماینده","Filter by reseller")} value={resellerFilterId} onChange={event=>{setResellerFilterId(Number(event.target.value));setPage(0);}}><option value={0}>{pick("همه نمایندگی‌ها","All resellers")}</option><option value={-1}>{pick("بدون نماینده","No reseller")}</option>{transferResellers.map(reseller=><option key={n(reseller.id)} value={n(reseller.id)}>{s(reseller.name)||s(reseller.brand_name)||`#${reseller.id}`}</option>)}</select><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button></div>
      {loading&&rows.length===0?<div className="runtime-loading">…</div>:<div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>{pick("نماینده","Reseller")}</th><th>{pick("پلن","Plan")}</th><th>{pick("نام کاربری","Username")}</th><th>{pick("ترافیک","Traffic")}</th><th>{pick("ساخت","Created")}</th><th>{pick("انقضا","Expires")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(item=>{const user=userMap.get(n(item.user_id));const plan=planMap.get(n(item.plan_id));return <tr key={n(item.id)}><td><div className="user-cell"><b>{user?.full_name||s(item.customer_name)||`#${item.user_id}`}</b><small dir="ltr">{user?.email||s(item.customer_email)||"—"}</small></div></td><td><div className="user-cell"><b>{s(item.reseller_name)||pick("مستقیم","Direct")}</b>{n(item.reseller_id)>0&&<small dir="ltr">#{n(item.reseller_id)}</small>}</div></td><td><div className="user-cell"><b>{s(item.plan_name)||s(plan?.name)||`#${item.plan_id}`}</b><small dir="ltr">MV-{n(item.id)}</small></div></td><td><div className="secret-row"><b dir="ltr">{s(item.account_username)||"—"}</b>{s(item.account_username)&&<button className="mini-btn" onClick={()=>copy(s(item.account_username))}>{pick("کپی","Copy")}</button>}</div></td><td>{trafficCell(item)}</td><td>{formatDate(item.created_at)}</td><td>{expiryCell(item)}</td><td><Badge tone={tone(item.status)}>{statusLabel(item.status)}</Badge></td><td><div className="row-actions"><button className="danger" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button><button disabled={!!busy} onClick={()=>void toggleStatus(item)}>{s(item.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button onClick={()=>openEdit(item)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openExtend(item)}>{pick("تمدید","Renew")}</button><button className="ghost" disabled={!!busy} onClick={()=>void openTransfer(item)}>{pick("انتقال اکانت","Transfer account")}</button><button className="primary-soft" onMouseEnter={()=>prefetchSubscriptionLink(item)} onFocus={()=>prefetchSubscriptionLink(item)} onClick={()=>void openSubscriptionLink(item)}>{pick("سابلینک","Sub-link")}</button><button className="ghost" type="button" data-testid="admin-app-delivery-action" onClick={()=>setAppDeliverySubscriptionId(n(item.id)||null)}>{pick("ورود اپ","App Delivery")}</button></div></td></tr>;})}</tbody></table>{filtered.length===0&&<div className="runtime-empty">{pick("اشتراکی پیدا نشد","No subscriptions found")}</div>}</div>}

      <div className="mobile-subscription-cards" aria-label={pick("فهرست اشتراک‌ها","Subscriptions list")}>
        {filtered.map(item=>{
          const user=userMap.get(n(item.user_id));
          const plan=planMap.get(n(item.plan_id));
          return <article className="mobile-subscription-card" key={n(item.id)}>
            <div className="mobile-subscription-card-head">
              <div className="mobile-subscription-user">
                <span className="mobile-subscription-avatar" aria-hidden="true">◉</span>
                <div className="mobile-subscription-identities">
                  <b dir="auto">{s(item.account_username)||user?.full_name||s(item.customer_name)||`#${item.user_id}`}</b>
                  <small>{user?.full_name||s(item.customer_name)||pick("کاربر","Customer")}</small>
                </div>
              </div>
              <Badge tone={tone(item.status)}>{statusLabel(item.status)}</Badge>
            </div>
            <div className="mobile-subscription-meta">
              <span className="mobile-subscription-plan">{s(item.plan_name)||s(plan?.name)||pick("پلن دستی","Manual plan")}</span>
              <span dir="ltr">MV-{n(item.id)}</span>
              <span>{s(item.reseller_name)||pick("کاربر مستقیم","Direct customer")}</span>
              <span dir="auto" className="mobile-subscription-contact">{user?.email||s(item.customer_email)||"—"}</span>
            </div>
            <div className="mobile-subscription-usage">
              <div><small>{pick("حجم","Traffic")}</small>{trafficCell(item)}</div>
              <div><small>{pick("انقضا","Expiry")}</small>{expiryCell(item)}</div>
            </div>
            <div className="mobile-subscription-actions">
              <button type="button" className="mobile-action mobile-action-renew" disabled={!!busy} onClick={()=>openExtend(item)}>▣ {pick("تمدید","Renew")}</button>
              <button type="button" className="mobile-action mobile-action-edit" disabled={!!busy} onClick={()=>openEdit(item)}>✎ {pick("ویرایش","Edit")}</button>
              <button type="button" className="mobile-action mobile-action-reset" disabled={!!busy} onClick={()=>{if(!busy){setError("");setOk("");setResetTarget(item);}}}>↻ {pick("ریست","Reset")}</button>
              <button type="button" className="mobile-action mobile-action-connect" onMouseEnter={()=>prefetchSubscriptionLink(item)} onFocus={()=>prefetchSubscriptionLink(item)} onClick={()=>void openSubscriptionLink(item)}>↗ {pick("اتصال","Connect")}</button>
            </div>
            <details className="mobile-subscription-more">
              <summary>{pick("عملیات بیشتر","More actions")} <span aria-hidden="true">⋯</span></summary>
              <div className="mobile-subscription-more-actions">
                <button type="button" className={s(item.status).toLowerCase()==="active"?"mobile-more-suspend":"mobile-more-activate"} disabled={!!busy} onClick={()=>void toggleStatus(item)}>{s(item.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button>
                <button type="button" className="mobile-more-transfer" disabled={!!busy} onClick={()=>void openTransfer(item)}>{pick("انتقال اکانت","Transfer account")}</button>
                <button type="button" className="mobile-more-app" onClick={()=>setAppDeliverySubscriptionId(n(item.id)||null)}>{pick("ورود اپ","App Delivery")}</button>
                <button type="button" className="danger mobile-more-delete" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button>
              </div>
            </details>
          </article>;
        })}
        {!loading&&filtered.length===0&&<div className="runtime-empty">{pick("اشتراکی پیدا نشد","No subscriptions found")}</div>}
      </div>
      <style>{`
        .legacy-subscriptions-page .runtime-toolbar+.table{display:none}
        .legacy-subscriptions-page .mobile-subscription-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:15px;direction:rtl}
          .legacy-subscriptions-page .mobile-subscription-card{min-width:0;overflow:hidden;padding:15px;border:1px solid rgba(119,118,240,.48);border-radius:19px;background:linear-gradient(145deg,rgba(52,44,106,.34),rgba(12,23,44,.96) 58%,rgba(11,21,40,.98));box-shadow:inset 0 1px rgba(255,255,255,.075),0 8px 23px rgba(0,0,0,.14)}
          .legacy-subscriptions-page .mobile-subscription-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
          .legacy-subscriptions-page .mobile-subscription-user{display:flex;align-items:center;min-width:0;gap:10px}
          .legacy-subscriptions-page .mobile-subscription-avatar{display:grid;place-items:center;flex:none;width:39px;height:39px;border:1px solid rgba(151,114,255,.65);border-radius:50%;color:#e9d5ff;background:linear-gradient(135deg,#6430b8,#263d91)}
          .legacy-subscriptions-page .mobile-subscription-identities{min-width:0;display:flex;flex-direction:column;gap:3px}
          .legacy-subscriptions-page .mobile-subscription-identities b{font-size:15px;max-width:100%;overflow-wrap:anywhere}
          .legacy-subscriptions-page .mobile-subscription-identities small{color:#aebbd5;font-size:11px;overflow-wrap:anywhere}
          .legacy-subscriptions-page .mobile-subscription-meta{display:flex;gap:8px 12px;flex-wrap:wrap;align-items:center;margin:12px 0;font-size:12px;color:#b8c7e5}
          .legacy-subscriptions-page .mobile-subscription-meta>span{overflow-wrap:anywhere}
          .legacy-subscriptions-page .mobile-subscription-plan{border:1px solid rgba(45,145,255,.54);border-radius:999px;background:rgba(8,83,182,.44);color:#d2e9ff;padding:4px 10px;font-weight:700}
          .legacy-subscriptions-page .mobile-subscription-contact{max-width:100%}
          .legacy-subscriptions-page .mobile-subscription-usage{display:grid;grid-template-columns:1fr 1fr;gap:8px;border-top:1px solid rgba(148,163,184,.14);padding-top:10px;margin-bottom:13px}
          .legacy-subscriptions-page .mobile-subscription-usage>div{min-width:0;overflow-wrap:anywhere}
          .legacy-subscriptions-page .mobile-subscription-usage>div>small{display:block;color:#93a6c8;margin-bottom:3px}
          .legacy-subscriptions-page .mobile-subscription-usage .user-cell b{font-size:12px}
          .legacy-subscriptions-page .mobile-subscription-actions{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
          .legacy-subscriptions-page .mobile-action{display:flex;align-items:center;justify-content:center;gap:4px;min-width:0;min-height:43px;padding:8px 3px;color:#f8faff;font-size:12px;font-weight:700;border:1px solid rgba(121,145,192,.46);border-radius:12px;background:linear-gradient(180deg,#25334e,#141e34);cursor:pointer;white-space:nowrap}
          .legacy-subscriptions-page .mobile-action-renew{background:linear-gradient(125deg,#137ee9,#1351b7);border-color:#309cfb}
          .legacy-subscriptions-page .mobile-action-connect{background:linear-gradient(125deg,#7226ad,#4934aa);border-color:#a05aff}
          .legacy-subscriptions-page .mobile-action:disabled{opacity:.5;cursor:not-allowed}
          .legacy-subscriptions-page .mobile-subscription-more{margin-top:11px;border-top:1px solid rgba(148,163,184,.16);padding-top:8px}
          .legacy-subscriptions-page .mobile-subscription-more summary{cursor:pointer;font-size:12px;color:#b8c9f1;list-style:none;display:flex;justify-content:space-between;align-items:center}
          .legacy-subscriptions-page .mobile-subscription-more summary::-webkit-details-marker{display:none}
          .legacy-subscriptions-page .mobile-subscription-more-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:10px}
          .legacy-subscriptions-page .mobile-subscription-more-actions button{min-height:42px;border-radius:10px}
          .legacy-subscriptions-page .mobile-subscription-more-actions .danger{color:#fecaca}
          .legacy-subscriptions-page .mobile-subscription-card{height:100%;box-sizing:border-box}
          .legacy-subscriptions-page .mobile-subscription-usage{margin-top:auto}
          .legacy-subscriptions-page .mobile-subscription-identities{max-width:100%}
          .legacy-subscriptions-page .mobile-subscription-usage .user-cell b{overflow-wrap:anywhere}
          .legacy-subscriptions-page .mobile-subscription-more-actions button{
            cursor:pointer;border:1px solid rgba(161,178,218,.54);
            padding:9px 7px;background:linear-gradient(145deg,#253756,#182740);
            color:#f5f7ff;font-size:12px;font-weight:700;font-family:inherit
          }
          .legacy-subscriptions-page .mobile-subscription-more-actions .mobile-more-transfer{
            background:linear-gradient(135deg,#314969,#203451);border-color:#829ed7;color:#fff
          }
          .legacy-subscriptions-page .mobile-subscription-more-actions .mobile-more-suspend{
            background:linear-gradient(135deg,#79531d,#533516);border-color:#edaa4d;color:#fff
          }
          .legacy-subscriptions-page .mobile-subscription-more-actions .mobile-more-activate{
            background:linear-gradient(135deg,#146c56,#0d4038);border-color:#36c99f;color:#fff
          }
          .legacy-subscriptions-page .mobile-subscription-more-actions .mobile-more-app{
            background:linear-gradient(135deg,#185fbf,#1c3984);border-color:#559aff;color:#fff
          }
          .legacy-subscriptions-page .mobile-subscription-more-actions .mobile-more-delete{
            background:linear-gradient(135deg,#63202f,#3e1824);border-color:#db7288;color:#ffe2e7
          }
          .legacy-subscriptions-page .mobile-subscription-more-actions button:disabled{opacity:.52;cursor:not-allowed}
          .legacy-subscriptions-page .mobile-action-edit{
            background:linear-gradient(135deg,#395173,#243652);border-color:#8aa5d9;color:#fff
          }
          .legacy-subscriptions-page .mobile-action-reset{
            background:linear-gradient(135deg,#89541e,#5b3516);border-color:#f4af58;color:#fff
          }
          .legacy-subscriptions-page .mobile-subscription-card:focus-within{
            border-color:rgba(171,137,255,.82);box-shadow:0 0 0 2px rgba(120,87,233,.15)
          }
          .legacy-subscriptions-page .mobile-subscription-more summary:focus-visible,
          .legacy-subscriptions-page .mobile-subscription-actions button:focus-visible{
            outline:2px solid #b2a4ff;outline-offset:2px
          }
          @media(min-width:1650px){
            .legacy-subscriptions-page .mobile-subscription-cards{grid-template-columns:repeat(4,minmax(0,1fr))}
          }
          @media(max-width:1220px){
            .legacy-subscriptions-page .mobile-subscription-cards{grid-template-columns:repeat(2,minmax(0,1fr))}
          }
          @media(max-width:760px){
            .legacy-subscriptions-page .mobile-subscription-cards{grid-template-columns:1fr}
          }
        @media(max-width:355px){
          .legacy-subscriptions-page .mobile-subscription-actions{grid-template-columns:repeat(2,minmax(0,1fr))}
        }
      `}</style>
    </Card>
    <div className="runtime-toolbar" style={{justifyContent:"space-between",marginTop:12}}>
      <span>{matchedTotal.toLocaleString("fa-IR")} {pick("نتیجه","results")} · {pick("صفحه","Page")} {(page+1).toLocaleString("fa-IR")} / {pageCount.toLocaleString("fa-IR")}</span>
      <nav className="subscription-page-navigation" aria-label={pick("صفحه‌بندی اشتراک‌ها","Subscription pagination")}>
        <button type="button" className="ghost" disabled={loading||page===0} onClick={()=>changePage(page-1)}>{pick("قبلی","Previous")}</button>
        {pageWindowStart>0&&<span className="subscription-page-ellipsis" aria-hidden="true">…</span>}
        {visiblePages.map(index=><button
          type="button"
          key={index}
          className={`subscription-page-number ${page===index?"is-active":""}`}
          aria-label={pick(`صفحه ${index+1}`,`Page ${index+1}`)}
          aria-current={page===index?"page":undefined}
          disabled={loading}
          onClick={()=>changePage(index)}
        >{(index+1).toLocaleString(pick("fa-IR","en-US"))}</button>)}
        {pageWindowStart+visiblePages.length<pageCount&&<span className="subscription-page-ellipsis" aria-hidden="true">…</span>}
        <button type="button" className="ghost" disabled={loading||page+1>=pageCount} onClick={()=>changePage(page+1)}>{pick("بعدی","Next")}</button>
      </nav>
      <style>{`
        .subscription-page-navigation{display:flex;flex-wrap:wrap;align-items:center;gap:6px;direction:rtl}
        .subscription-page-number{min-width:34px;height:34px;padding:0 7px;border-radius:9px;border:1px solid var(--line,rgba(148,163,184,.2));background:var(--surface2,#111827);color:inherit;cursor:pointer;font:inherit;transition:background .15s,border-color .15s}
        .subscription-page-number:hover:not(:disabled){border-color:var(--brand-primary,#2563eb);background:color-mix(in srgb,var(--brand-primary,#2563eb) 12%,transparent)}
        .subscription-page-number.is-active{background:var(--brand-primary,#2563eb);border-color:var(--brand-primary,#2563eb);color:#fff;font-weight:700}
        .subscription-page-number:focus-visible{outline:2px solid var(--brand-primary,#2563eb);outline-offset:2px}
        .subscription-page-number:disabled{cursor:wait;opacity:.65}
        .subscription-page-ellipsis{padding:0 3px;color:var(--muted,#94a3b8)}
        @media(max-width:700px){.subscription-page-navigation{gap:4px}.subscription-page-number{min-width:30px;height:32px;padding:0 5px}}
      `}</style>
    </div>

    {resetTarget&&<Modal
      title={pick("تأیید ریست حجم مصرفی","Confirm usage reset")}
      sub={`MV-${n(resetTarget.id)} · ${s(resetTarget.account_username)||pick("اشتراک","Subscription")}`}
      onClose={()=>{if(!busy)setResetTarget(null);}}
    >
      <p>{pick("حجم مصرفی این اشتراک صفر شود؟ حجم کل، تاریخ انقضا، رمز و کانفیگ‌ها تغییر نمی‌کنند.","Reset this subscription's used traffic to zero? Total quota, expiration, password and configurations will not change.")}</p>
      <small className="muted">{pick("سوابق مصرف و شمارنده‌های نود برای جلوگیری از محاسبه تکراری محفوظ می‌مانند.","Historical usage and node accounting cursors are preserved.")}</small>
      {error&&<Notice error={error} ok=""/>}
      <div className="modalActions">
        <button type="button" className="ghost" disabled={!!busy} onClick={()=>setResetTarget(null)}>{pick("خیر","No")}</button>
        <button type="button" className="primary" disabled={!!busy} onClick={confirmUsageReset}>{busy==="reset-usage"?pick("در حال ریست…","Resetting…"):pick("بله، ریست کن","Yes, reset")}</button>
      </div>
    </Modal>}

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
      
      <form onSubmit={saveEdit} className="subs-edit-form">
        <div className="subs-edit-main">
          <div className="subs-edit-main-title">{pick("تنظیمات اصلی","Main settings")}</div>
          <div className="subs-edit-grid">
            <label className="field"><span>{pick("پلن","Plan")}</span><select value={draft.plan_id} onChange={event=>setDraft(current=>({...current,plan_id:Number(event.target.value)}))}><option value={0} disabled={n(selected.plan_id)>0}>{pick("اشتراک دستی (بدون پلن)","Manual subscription (no plan)")}</option>{plans.map(plan=><option key={n(plan.id)} value={n(plan.id)}>{s(plan.name)||`#${plan.id}`}</option>)}</select></label>
            <label className="field"><span>{pick("حجم کل GB","Total traffic GB")}</span><input type="number" min={0} step="0.1" value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:event.target.value}))} placeholder={pick("خالی = نامحدود","empty = unlimited")}/></label>
            <label className="field"><span>{pick("اتصال هم‌زمان مجاز","Allowed concurrent devices")}</span><input type="number" min={0} max={1000} step={1} required value={draft.device_limit} onChange={event=>setDraft(current=>({...current,device_limit:event.target.value}))}/><small>{pick("۰ = نامحدود؛ عدد انتخابی به همین اشتراک اعمال می‌شود","0 = unlimited; applied to this account")}</small></label>
            <label className="field"><span>{pick("مدت اعتبار (روز)","Validity (days)")}</span><input type="number" min={0} max={3650} step={1} value={draft.duration_days} onChange={event=>{setDraft(current=>({...current,duration_days:event.target.value}));setEditExpiry("");}}/></label>
            <label className="field"><span>{pick("تاریخ انقضا","Expiry date")}</span><input type="date" value={editExpiry} onChange={event=>setEditExpiry(event.target.value)}/><small>{pick("اگر خالی باشد، تاریخ فعلی حفظ می‌شود","Leave blank to preserve current expiry")}</small></label>
          </div>
        </div>
        <details className="subs-edit-section">
          <summary>
            <span>{pick("نام کاربری و رمز عبور","Username and password")}</span>
            <small>{pick("فقط هنگام نیاز باز کنید","Open when needed")}</small>
          </summary>
          <div className="subs-edit-section-content subs-edit-credentials">
            <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))}/></label>
            <label className="field"><span>{pick("رمز جدید","New password")}</span><input dir="ltr" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))} placeholder={pick("خالی = بدون تغییر","empty = unchanged")}/></label>
          </div>
        </details>
        <details className="subs-edit-section subs-edit-protocols">
          <summary>
            <span>{pick("پروتکل‌ها","Protocols")}</span>
            <small>{draft.protocols.length.toLocaleString("fa-IR")} {pick("انتخاب‌شده","selected")}</small>
          </summary>
          <div className="subs-edit-section-content">
            <div className="protocol-toggle-grid subs-edit-protocol-grid">{protocolKeys.map(key=>{const modern=!classicProtocolSet.has(key);const supported=modern||nodes.some(node=>node.status==="online"&&Boolean((node as unknown as RuntimeRow)[`enable_${key}`]));const checked=draft.protocols.includes(key);return <label key={key} className="toggle module-toggle compact-toggle"><span>{protocolLabels[key]}<small>{modern?pick("وضعیت Runtime هنگام ذخیره بررسی می‌شود","Runtime readiness is checked on save"):supported?pick("قابل استفاده","Available"):pick("روی سرور آنلاین فعال نیست","Not enabled on an online server")}</small></span><input type="checkbox" disabled={!supported} checked={checked} onChange={event=>setDraft(current=>({...current,protocols:event.target.checked?[...new Set([...current.protocols,key])]:current.protocols.filter(item=>item!==key)}))}/><i/></label>;})}</div>
          </div>
        </details>
        <details className="subs-edit-section">
          <summary>
            <span>{pick("تنظیمات پیشرفته","Advanced settings")}</span>
            <small>{editResetUsage?pick("ریست مصرف انتخاب شده","Traffic reset selected"):pick("ریست ترافیک مصرفی","Reset used traffic")}</small>
          </summary>
          <div className="subs-edit-section-content subs-edit-advanced">
            <label className="field" style={{display:"flex",alignItems:"center",gap:10,marginTop:12}}><input type="checkbox" checked={editResetUsage} onChange={event=>setEditResetUsage(event.target.checked)}/><span>{pick("ریست ترافیک مصرفی (صفر شدن مصرف دوره)","Reset used traffic (start usage at zero)")}</span></label><small className="muted">{pick("فقط مصرف این اشتراک صفر می‌شود؛ سوابق حسابداری و شمارنده‌های نود حفظ می‌شوند.","Only this subscription's used balance is reset; accounting history and node counters are preserved.")}</small>
          </div>
        </details>
        <div className="modalActions"><button type="button" className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="edit"||(!draft.plan_id&&n(selected.plan_id)>0)||!draft.protocols.length}>{busy==="edit"?pick("در حال ذخیره…","Saving…"):pick("ذخیره تغییرات","Save changes")}</button></div>
      </form>

    </Modal>}

    {transferOpen&&selected&&<Modal title={pick("انتقال اکانت","Transfer account")} sub={`MV-${n(selected.id)} · ${s(selected.account_username)}`} onClose={()=>!busy&&setTransferOpen(false)}>
      <p className="muted">{pick("مالک واقعی اشتراک تغییر می‌کند؛ شناسه، کانفیگ، حجم مصرف‌شده و انقضا حفظ می‌شوند. در انتقال به نماینده، مشتری همان نمایندگی را انتخاب کنید.","Real ownership changes; VPN account ID, configs, usage and expiry remain unchanged. For reseller transfers, select a customer of that reseller.")}</p>
      <label className="field"><span>{pick("مقصد انتقال","Transfer destination")}</span><select value={transferMode} disabled={!!busy} onChange={event=>{setTransferMode(event.target.value as "user"|"reseller");setTransferUserId(0);setTransferCustomerId(0);}}>
        <option value="user">{pick("کاربر مستقیم","Direct user")}</option>
        <option value="reseller">{pick("نماینده و مشتری نماینده","Reseller and its customer")}</option>
      </select></label>
      {transferMode==="user"?
        <div className="setting-grid">
          <label className="field"><span>{pick("جستجوی کاربر مقصد","Find destination user")}</span><input value={transferUserSearch} onChange={event=>{setTransferUserSearch(event.target.value);setTransferUserId(0);}} placeholder={pick("نام، ایمیل یا شماره کاربر…","Name, email or user ID…")}/></label>
          <label className="field"><span>{pick("انتخاب مالک جدید","Select new owner")}</span><select value={transferUserId} disabled={!!busy} onChange={event=>setTransferUserId(Number(event.target.value))}>
            <option value={0}>{pick("انتخاب کاربر","Select user")}</option>
            {transferUserMatches.map(user=><option key={user.id} value={user.id}>{user.full_name||user.email||`#${user.id}`} · {user.email||`#${user.id}`}</option>)}
          </select></label>
        </div>:
      <><div className="setting-grid">
        <label className="field"><span>{pick("نماینده مقصد","Destination reseller")}</span>
          <select value={transferResellerId} disabled={transferLoading||!!busy} onChange={event=>void selectTransferReseller(Number(event.target.value))}>
            <option value={0}>{pick("انتخاب نماینده","Select reseller")}</option>
            {transferResellers.filter(row=>row.is_active===true).map(row=><option key={n(row.id)} value={n(row.id)}>{s(row.name)||s(row.brand_name)||`#${row.id}`} · {s(row.code)}</option>)}
          </select>
        </label>
        <label className="field"><span>{pick("جستجوی کاربر موجود","Search existing site user")}</span><input value={transferCustomerSearch} disabled={!transferResellerId||!!busy} onChange={event=>{setTransferCustomerSearch(event.target.value);setTransferCustomerId(0);}} placeholder={pick("نام، ایمیل، موبایل یا شناسه کاربر…","Name, email, phone or user ID…")}/></label>
        <label className="field"><span>{pick("کاربر مقصد","Destination user")}</span>
          <select value={transferCustomerId} disabled={!transferResellerId||transferLoading||!!busy} onChange={event=>setTransferCustomerId(Number(event.target.value))}>
            <option value={0}>{pick("انتخاب مشتری","Select customer")}</option>
            {transferCustomers.map(customer=><option key={customer.id} value={customer.id}>{customer.name}{customer.is_owner?` · ${pick("حساب نماینده","Reseller owner")}`:""}</option>)}
          </select>
        </label>
      </div>
      {transferResellerId&&!transferLoading&&!transferCustomers.length?<p className="runtime-error">{pick("کاربری پیدا نشد؛ نام، ایمیل، موبایل یا شناسه کاربر موجود را جستجو کنید.","No active customer found for this reseller. Create a customer first.")}</p>:null}</>}
      <div className="modalActions"><button className="ghost" disabled={!!busy} onClick={()=>setTransferOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={!!busy||transferLoading||(transferMode==="user"?!transferUserId:!transferResellerId||!transferCustomerId)} onClick={submitTransfer}>{busy==="transfer"?pick("در حال انتقال…","Transferring…"):pick("تأیید انتقال","Confirm transfer")}</button></div>
    </Modal>}
    {modal==="extend"&&selected&&<Modal title={pick("تمدید اشتراک","Renew subscription")} sub={`MV-${n(selected.id)} · ${selected.expires_at?formatDate(selected.expires_at):selected.duration_unlimited===true||n(selected.activation_duration_days)<=0?pick("نامحدود","Unlimited"):pick("از اولین اتصال","From first connection")}`} onClose={()=>!busy&&setModal(null)}>
      <Notice error={error} ok={ok}/>
      <div className="setting-grid">
        <label className="field"><span>{pick("روز اضافه / مدت دوره جدید","Add days / new period days")}</span><input type="number" min={0} value={extendDays} onChange={event=>setExtendDays(Math.max(0,Number(event.target.value)||0))}/></label>
        <label className="field"><span>{pick("حجم اضافه GB","Add traffic GB")}</span><input type="number" min={0} step="0.1" value={extendTraffic} onChange={event=>setExtendTraffic(Math.max(0,Number(event.target.value)||0))}/></label>
      </div>
      <label className="field" style={{display:"flex",alignItems:"center",gap:10,marginTop:12}}><input type="checkbox" checked={extendResetUsage} onChange={event=>setExtendResetUsage(event.target.checked)}/><span>{pick("ریست ترافیک مصرفی","Reset used traffic")}</span></label>
      <label className="field" style={{display:"flex",alignItems:"center",gap:10,marginTop:8}}><input type="checkbox" checked={extendResetDate} onChange={event=>setExtendResetDate(event.target.checked)}/><span>{pick("ریست تاریخ (شروع اعتبار جدید از امروز)","Reset expiry (new period begins now)")}</span></label>
      {extendResetDate&&<small className="muted">{pick("با ریست تاریخ، روزهای واردشده از همین لحظه محاسبه می‌شوند، نه از انقضای قبلی.","The entered days start now rather than adding to the previous expiry.")}</small>}
      <div className="modalActions"><button className="ghost" disabled={!!busy} onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={!!busy||(!extendDays&&!extendTraffic&&!extendResetUsage)||(extendResetDate&&!extendDays)} onClick={saveExtend}>{busy==="extend"?"…":pick("اعمال تمدید","Apply renewal")}</button></div>
    </Modal>}

    {modal==="connect"&&selected&&<Modal title={pick("اطلاعات اتصال","Connection information")} sub={`MV-${n(selected.id)}`} onClose={()=>setModal(null)} wide>
      <Notice error={error} ok={ok}/>
      {busy==="connection"?<div className="runtime-loading">…</div>:<>
        <div className="stats dashboard-stats modal-stats"><Stat label={pick("نام کاربری","Username")} value={s(account?.username||selected.account_username)||"—"}/><Stat label={pick("پروتکل‌ها","Protocols")} value={String(credentials.length)}/><Stat label={pick("سرورها","Servers")} value={String(credentials.reduce((sum,item)=>sum+list(item.items).length,0))}/></div>
        <div className="manage-actions"><button className="primary" disabled={!!busy} onClick={()=>void provision()}>{busy==="provision"?"…":pick("ساخت/بازسازی اتصال","Provision connection")}</button><button className="ghost" disabled={!!busy} onClick={()=>void refreshPasswords()}>{busy==="passwords"?"…":pick("رمز جدید Cisco/L2TP","Refresh Cisco/L2TP password")}</button>{shareLink&&<><button className="ghost" onClick={()=>copy(shareLink)}>{pick("کپی سابلینک","Copy sub-link")}</button><a className="ghost" href={shareLink} target="_blank" rel="noreferrer">{pick("صفحه اتصال","Connection page")}</a></>}</div>
        <div className="setting-grid"><div className="setting-box"><small>{pick("نام کاربری اکانت","Account username")}</small><div className="secret-row"><b dir="ltr">{s(account?.username||selected.account_username)||"—"}</b>{s(account?.username||selected.account_username)&&<button className="mini-btn" onClick={()=>copy(s(account?.username||selected.account_username))}>{pick("کپی","Copy")}</button>}</div></div><div className="setting-box"><small>{pick("رمز عبور اکانت","Account password")}</small><div className="secret-row"><b dir="ltr">{showPassword?s(account?.password)||"—":"••••••••"}</b><button className="mini-btn" onClick={()=>setShowPassword(value=>!value)}>{showPassword?pick("مخفی","Hide"):pick("نمایش","Show")}</button>{s(account?.password)&&<button className="mini-btn" onClick={()=>copy(s(account?.password))}>{pick("کپی","Copy")}</button>}</div></div></div>
        {credentials.length===0?<div className="runtime-empty">{pick("هنوز اطلاعات اتصال ساخته نشده است. «ساخت/بازسازی اتصال» را بزنید.","Connection data has not been provisioned yet.")}</div>:<><div className="runtime-tabs">{credentials.map(item=><button type="button" key={s(item.protocol)} className={activeProtocol===s(item.protocol)?"active":""} onClick={()=>setActiveProtocol(s(item.protocol))}>{protocolLabels[s(item.protocol)]||s(item.protocol)}</button>)}</div><div className="manage-card-section"><div className="manage-section-head"><div><b>{protocolLabels[s(selectedCredential?.protocol)]||s(selectedCredential?.protocol)}</b><small>{selectedItems.length.toLocaleString("fa-IR")} {pick("سرور قابل استفاده","available servers")}</small></div></div><div className="protocol-toggle-grid">{selectedItems.map((item,index)=>{const protocol=s(selectedCredential?.protocol);const server=s(item.server||item.server_ip);const port=s(item.port||item.ports);const username=s(item.username||selectedCredential?.username||account?.username);const password=s(item.password||account?.password);const config=s(item.config);const uri=s(item.uri);const psk=s(item.psk);const filename=s(item.filename)||`${protocol}-${n(selected.id)}-${index+1}.${protocol==="openvpn"?"ovpn":protocol==="wireguard"?"conf":"txt"}`;return <div className="setting-box" key={`${protocol}-${n(item.node_id)}-${index}`}><div className="card-head"><div><b>{s(item.node)||`${pick("سرور","Server")} ${index+1}`}</b><small dir="ltr">{server}{port?`:${port}`:""}</small></div><Badge tone="ok">{pick("آماده","Ready")}</Badge></div><div className="setting-grid">{server&&<div><small>{pick("سرور","Server")}</small><div className="secret-row"><code dir="ltr">{server}</code><button className="mini-btn" onClick={()=>copy(server)}>{pick("کپی","Copy")}</button></div></div>}{port&&<div><small>{pick("پورت / Transport","Port / Transport")}</small><b dir="ltr">{port}{s(item.transport)?` · ${s(item.transport)}`:""}</b></div>}{username&&<div><small>{pick("نام کاربری","Username")}</small><div className="secret-row"><code dir="ltr">{username}</code><button className="mini-btn" onClick={()=>copy(username)}>{pick("کپی","Copy")}</button></div></div>}{password&&<div><small>{pick("رمز عبور","Password")}</small><div className="secret-row"><code dir="ltr">{showPassword?password:"••••••••"}</code><button className="mini-btn" onClick={()=>copy(password)}>{pick("کپی","Copy")}</button></div></div>}{psk&&<div><small>PSK</small><div className="secret-row"><code dir="ltr">{psk}</code><button className="mini-btn" onClick={()=>copy(psk)}>{pick("کپی","Copy")}</button></div></div>}{s(item.address)&&<div><small>{pick("آدرس WireGuard","WireGuard address")}</small><code dir="ltr">{s(item.address)}</code></div>}{s(item.uuid)&&<div><small>UUID</small><div className="secret-row"><code dir="ltr">{s(item.uuid)}</code><button className="mini-btn" onClick={()=>copy(s(item.uuid))}>{pick("کپی","Copy")}</button></div></div>}</div>{(config||uri)&&<div className="manage-actions">{config&&<><button className="primary-soft" onClick={()=>copy(config)}>{pick("کپی کانفیگ","Copy config")}</button><button className="ghost" onClick={()=>downloadText(filename,config)}>{pick("دانلود فایل","Download file")}</button></>}{uri&&<button className="primary-soft" onClick={()=>copy(uri)}>{pick("کپی لینک V2Ray","Copy V2Ray URI")}</button>}</div>}{(protocol==="wireguard"&&config||protocol==="v2ray"&&uri)&&<div style={{display:"grid",placeItems:"center",marginTop:12}}><div style={{background:"white",padding:12,borderRadius:14}}><QRCodeSVG value={protocol==="wireguard"?config:uri} size={160}/></div></div>}</div>;})}</div></div></>}
      </>}
    </Modal>}

    {appDeliverySubscriptionId!==null&&<Modal
      title={pick("ورود مخصوص اپ TwinConnect","TwinConnect App Delivery")}
      sub={pick("نام کاربری و رمز مستقل از VPN","Separate app login, independent of VPN credentials")}
      onClose={()=>setAppDeliverySubscriptionId(null)}
      wide
    >
      <AppCredentialDeliveryCard
        key={appDeliverySubscriptionId}
        owner="admin"
        subscriptionId={appDeliverySubscriptionId}
      />
    </Modal>}

    <SubscriptionLinkDeliveryModal
      appOwner="admin"
      subscriptionId={linkModalId??undefined}
      open={linkModalId!==null}
      link={linkModalLink}
      reference={linkModalId?`MV-${linkModalId}`:""}
      loading={linkModalLoading}
      error={linkModalError}
      onClose={closeSubscriptionLink}
    />
  </div></Shell>;
}