"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type Row=Record<string,unknown>;
type Tier="economic_v2ray"|"premium_static_ip";
type Draft={id:number;reseller_tier:Tier;title:string;traffic_gb:string;price_toman:string;sort_order:string;is_active:boolean};
const TIER_OPTIONS:readonly {value:Tier;fa:string;en:string}[]=[
  {value:"economic_v2ray",fa:"ویتوری",en:"V2Ray"},
  {value:"premium_static_ip",fa:"ویژه",en:"Premium"},
];
const isTier=(value:unknown):value is Tier=>value==="economic_v2ray"||value==="premium_static_ip";

const emptyDraft:Draft={id:0,reseller_tier:"premium_static_ip",title:"",traffic_gb:"",price_toman:"",sort_order:"100",is_active:true};

function text(row:Row,key:string){const value=row?.[key];return value===undefined||value===null?"":String(value);}
function num(row:Row,key:string){const value=Number(text(row,key).replace(/[,٬]/g,"")||0);return Number.isFinite(value)?value:0;}
function money(value:number){return `${Number(value||0).toLocaleString("fa-IR")} تومان`;}
function traffic(value:number){return `${Number(value||0).toLocaleString("fa-IR",{maximumFractionDigits:2})} GB`;}

async function api<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    let message=`API error ${response.status}`;
    if(payload&&typeof payload==="object"){
      const row=payload as {detail?:unknown;message?:unknown};
      if(typeof row.detail==="string")message=row.detail;
      else if(Array.isArray(row.detail))message=row.detail.map(item=>typeof item==="object"&&item&&"msg" in item?String((item as {msg:unknown}).msg):String(item)).join("، ");
      else if(typeof row.message==="string")message=row.message;
    }
    throw new Error(message);
  }
  return payload as T;
}

export function AdminResellerTrafficPlans(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<Row[]>([]);
  const [draft,setDraft]=useState<Draft>(emptyDraft);
  const [query,setQuery]=useState("");
  const [tierFilter,setTierFilter]=useState<"all"|Tier>("all");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    try{setRows(await api<Row[]>("/v1/admin/resellers/traffic-packages/all"));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  useEffect(()=>{void load();},[]);

  const filtered=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    return rows.filter(row=>(tierFilter==="all"||(isTier(row.reseller_tier)?row.reseller_tier:"premium_static_ip")===tierFilter)
      &&(!needle||[row.id,row.title,row.traffic_gb,row.price_toman].some(value=>String(value??"").toLowerCase().includes(needle))));
  },[rows,query,tierFilter]);

  const activeCount=rows.filter(row=>Boolean(row.is_active)).length;
  const totalGb=rows.filter(row=>Boolean(row.is_active)).reduce((sum,row)=>sum+num(row,"traffic_gb"),0);

  const edit=(row:Row)=>setDraft({
    id:Number(row.id||0),
    reseller_tier:isTier(row.reseller_tier)?row.reseller_tier:"premium_static_ip",
    title:text(row,"title"),
    traffic_gb:String(num(row,"traffic_gb")||""),
    price_toman:String(num(row,"price_toman")||""),
    sort_order:String(num(row,"sort_order")||100),
    is_active:Boolean(row.is_active),
  });

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    const title=draft.title.trim();
    const gb=Number(draft.traffic_gb);
    const price=Number(draft.price_toman);
    const order=Number(draft.sort_order||100);
    if(title.length<2||!Number.isFinite(gb)||gb<=0||!Number.isFinite(price)||price<=0){
      setError(pick("عنوان، حجم و قیمت معتبر وارد کنید.","Enter a valid title, traffic and price."));
      return;
    }
    setBusy(true);setError("");setOk("");
    try{
      const payload={reseller_tier:draft.reseller_tier,title,traffic_gb:gb,price_toman:price,is_active:draft.is_active,sort_order:Number.isFinite(order)&&order>=0?order:100};
      if(draft.id){
        await api(`/v1/admin/resellers/traffic-packages/${draft.id}`,{method:"PATCH",body:JSON.stringify(payload)});
        setOk(pick("پلن شارژ حجم ویرایش شد.","Traffic recharge plan updated."));
      }else{
        await api("/v1/admin/resellers/traffic-packages",{method:"POST",body:JSON.stringify(payload)});
        setOk(pick("پلن شارژ حجم ساخته شد.","Traffic recharge plan created."));
      }
      setDraft(emptyDraft);
      await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const disable=async(id:number)=>{
    if(!id||busy)return;
    setBusy(true);setError("");setOk("");
    try{
      await api(`/v1/admin/resellers/traffic-packages/${id}`,{method:"DELETE"});
      setOk(pick("پلن غیرفعال شد.","Plan disabled."));
      if(draft.id===id)setDraft(emptyDraft);
      await load();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const remove=async(id:number,title:string)=>{
    if(!id||busy)return;

    const confirmed=window.confirm(
      pick(
        `پلن «${title}» برای همیشه حذف شود؟`,
        `Permanently delete “${title}”?`
      )
    );

    if(!confirmed)return;

    setBusy(true);setError("");setOk("");

    try{
      await api(
        `/v1/admin/resellers/traffic-packages/${id}/hard`,
        {method:"DELETE"}
      );

      setOk(
        pick(
          "پلن شارژ حجم حذف شد.",
          "Traffic recharge plan deleted."
        )
      );

      if(draft.id===id)setDraft(emptyDraft);

      await load();
    }catch(reason){
      setError(
        reason instanceof Error
          ? reason.message
          : String(reason)
      );
    }finally{
      setBusy(false);
    }
  };


  return <Shell active="/admin/reseller-traffic-plans"><div className="page reseller-admin-v2">
    <div className="page-head"><h1>{pick("پلن‌های شارژ حجم نمایندگی","Reseller traffic recharge plans")}</h1></div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats reseller-admin-stats">
      <Stat label={pick("کل پلن‌ها","All plans")} value={String(rows.length)}/>
      <Stat label={pick("پلن فعال","Active plans")} value={String(activeCount)}/>
      <Stat label={pick("مجموع حجم پلن‌های فعال","Total active plan traffic")} value={traffic(totalGb)}/>
    </div>

    <Card>
      <div style={{fontSize:12,opacity:.85,lineHeight:1.9,marginBottom:12}}>{pick("پلن ویتوری و ویژه هرکدام قیمت مستقل دارند. سرورها و پروتکل‌های مجاز هر نوع نمایندگی به‌صورت خودکار از پلن‌های فعال پنل اصلی تعیین می‌شوند؛ این صفحه فقط قیمت و بسته حجم نماینده را مدیریت می‌کند.","V2Ray and Premium reseller packages have independent pricing. Allowed servers and protocols come from the active main-panel plans; this page manages reseller traffic package prices only.")}</div>
      <div className="card-head"><b>{draft.id?pick("ویرایش پلن شارژ حجم","Edit traffic recharge plan"):pick("ساخت پلن شارژ حجم","Create traffic recharge plan")}</b>{draft.id>0&&<button className="mini-btn" type="button" onClick={()=>setDraft(emptyDraft)}>{pick("پلن جدید","New plan")}</button>}</div>
      <form className="runtime-editor" onSubmit={submit}>
        <div className="setting-grid">
          <label className="field"><span>{pick("نوع نمایندگی","Reseller type")}</span><select value={draft.reseller_tier} onChange={event=>setDraft(value=>({...value,reseller_tier:event.target.value as Tier}))}>{TIER_OPTIONS.map(tier=><option key={tier.value} value={tier.value}>{pick(tier.fa,tier.en)}</option>)}</select></label>
          <label className="field"><span>{pick("عنوان پلن","Plan title")}</span><input required minLength={2} value={draft.title} onChange={event=>setDraft(value=>({...value,title:event.target.value}))} placeholder={pick("مثلاً 100 گیگ","e.g. 100 GB")}/></label>
          <label className="field"><span>{pick("حجم (GB)","Traffic (GB)")}</span><input required type="number" min={1} step={1} value={draft.traffic_gb} onChange={event=>setDraft(value=>({...value,traffic_gb:event.target.value}))}/></label>
          <label className="field"><span>{pick("قیمت خرید نماینده (تومان)","Reseller purchase price")}</span><input required type="number" min={1000} step={1000} value={draft.price_toman} onChange={event=>setDraft(value=>({...value,price_toman:event.target.value}))}/></label>
          <label className="field"><span>{pick("ترتیب نمایش","Display order")}</span><input type="number" min={0} value={draft.sort_order} onChange={event=>setDraft(value=>({...value,sort_order:event.target.value}))}/></label>
        </div>
        <label className="toggle module-toggle"><span>{pick("فعال","Active")}</span><input type="checkbox" checked={draft.is_active} onChange={event=>setDraft(value=>({...value,is_active:event.target.checked}))}/><i/></label>
        <div className="action-row"><button className="primary" disabled={busy}>{busy?"…":draft.id?pick("ذخیره ویرایش","Save changes"):pick("ساخت پلن","Create plan")}</button>{draft.id>0&&<button className="ghost" type="button" onClick={()=>setDraft(emptyDraft)}>{pick("انصراف","Cancel")}</button>}</div>
      </form>
    </Card>

    <Card>
      <div className="runtime-toolbar" style={{display:"flex",flexWrap:"wrap",gap:12,alignItems:"center"}}>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          {([{value:"all",fa:"همه پلن‌ها",en:"All plans"},...TIER_OPTIONS] as const).map(item=><button key={item.value} type="button" className={tierFilter===item.value?"primary":"mini-btn"} onClick={()=>{setTierFilter(item.value);if(item.value!=="all")setDraft(current=>current.id?current:{...current,reseller_tier:item.value});}} aria-pressed={tierFilter===item.value}>{pick(item.fa,item.en)} ({rows.filter(row=>item.value==="all"||(isTier(row.reseller_tier)?row.reseller_tier:"premium_static_ip")===item.value).length})</button>)}
        </div>
        <label>⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("جستجوی پلن...","Search plans...")}/></label><Badge tone="violet">{filtered.length}</Badge></div>
      <div className="table reseller-admin-table"><table><thead><tr><th>ID</th><th>{pick("عنوان","Title")}</th><th>{pick("نوع نمایندگی","Reseller type")}</th><th>{pick("حجم","Traffic")}</th><th>{pick("قیمت","Price")}</th><th>{pick("ترتیب","Order")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(row=>{const id=Number(row.id||0),active=Boolean(row.is_active);return <tr key={id}><td>#{id}</td><td><b>{text(row,"title")}</b></td><td><Badge tone={row.reseller_tier==="economic_v2ray"?"violet":"ok"}>{pick(row.reseller_tier==="economic_v2ray"?"ویتوری":"ویژه",row.reseller_tier==="economic_v2ray"?"V2Ray":"Premium")}</Badge></td><td><b>{traffic(num(row,"traffic_gb"))}</b></td><td><b>{money(num(row,"price_toman"))}</b></td><td>{num(row,"sort_order")}</td><td><Badge tone={active?"ok":"warn"}>{active?pick("فعال","Active"):pick("غیرفعال","Disabled")}</Badge></td><td><div className="row-actions"><button className="mini-btn" type="button" onClick={()=>edit(row)}>{pick("ویرایش","Edit")}</button>{active&&<button className="mini-btn" type="button" disabled={busy} onClick={()=>void disable(id)}>{pick("غیرفعال","Disable")}</button>}<button className="mini-btn danger" type="button" disabled={busy} onClick={()=>void remove(id,text(row,"title"))}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>
      {!filtered.length&&<div className="runtime-empty">{pick("هنوز پلن شارژ حجمی تعریف نشده است.","No traffic recharge plan has been defined yet.")}</div>}
    </Card>
  </div></Shell>;
}
