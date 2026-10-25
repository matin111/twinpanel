"use client";

import {useEffect, useMemo, useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge, PageHead, Shell} from "./ui";
import styles from "./singbox-outbound-center.module.css";


type OutboundRow={
  type:string;
  tag:string;
  server?:string;
  server_port?:number;
  username?:string;
  password?:string;
  has_password?:boolean;
  managed?:boolean;
};

type OutboundNode={
  id:number;
  name:string;
  public_ip:string;
  public_domain?:string|null;
  service_active:boolean;
  error?:unknown;
  outbounds:OutboundRow[];
  default_tag?:string|null;
  default_mode:string;
};

type Inventory={
  ok:boolean;
  supported_types:string[];
  nodes:OutboundNode[];
};

type Draft={
  tag:string;
  type:"direct"|"socks"|"http";
  server:string;
  port:string;
  username:string;
  password:string;
  setDefault:boolean;
};

const EMPTY:Draft={
  tag:"",
  type:"socks",
  server:"",
  port:"1080",
  username:"",
  password:"",
  setDefault:false,
};

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
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
    if(payload&&typeof payload==="object"&&"detail" in payload){
      const detail=(payload as {detail?:unknown}).detail;
      if(typeof detail==="string")throw new Error(detail);
      if(detail&&typeof detail==="object"){
        const message=(detail as {message?:unknown;error?:unknown}).message;
        const error=(detail as {message?:unknown;error?:unknown}).error;
        throw new Error([message,error].filter(Boolean).map(String).join(" · ")||`API ${response.status}`);
      }
    }
    throw new Error(`API ${response.status}`);
  }
  return payload as T;
}

function errorText(value:unknown):string{
  if(!value)return "";
  if(typeof value==="string")return value;
  try{return JSON.stringify(value);}catch{return String(value);}
}

export function SingboxOutboundCenter(){
  const {pick}=useI18n();
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [nodeId,setNodeId]=useState(0);
  const [draft,setDraft]=useState<Draft>(EMPTY);
  const [editingTag,setEditingTag]=useState("");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    setError("");
    try{
      const data=await request<Inventory>("/v1/settings/vpn/outbounds");
      setInventory(data);
      setNodeId(current=>data.nodes.some(node=>node.id===current)?current:(data.nodes[0]?.id||0));
    }catch(exc){
      setError(exc instanceof Error?exc.message:String(exc));
    }finally{
      if(!silent)setLoading(false);
    }
  };

  useEffect(()=>{void load();},[]);

  const node=useMemo(()=>inventory?.nodes.find(item=>item.id===nodeId)||null,[inventory,nodeId]);

  const reset=()=>{
    setEditingTag("");
    setDraft(EMPTY);
  };

  const edit=(row:OutboundRow)=>{
    if(!row.managed)return;
    setEditingTag(row.tag);
    setDraft({
      tag:row.tag,
      type:(row.type==="direct"||row.type==="http"?row.type:"socks"),
      server:row.server||"",
      port:row.server_port?String(row.server_port):(row.type==="http"?"8080":"1080"),
      username:row.username||"",
      password:"",
      setDefault:node?.default_tag===row.tag,
    });
  };

  const save=async()=>{
    if(!node)return;
    const tag=draft.tag.trim();
    if(!tag){setError(pick("Tag الزامی است.","Tag is required."));return;}
    if(editingTag&&editingTag!==tag){setError(pick("برای تغییر Tag، Outbound جدید بسازید و قبلی را حذف کنید.","Create a new outbound to change its tag, then remove the old one."));return;}
    if(draft.type!=="direct"&&(!draft.server.trim()||!Number(draft.port))){setError(pick("آدرس و پورت Proxy الزامی است.","Proxy server and port are required."));return;}
    setBusy("save");setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(tag)}`,{
        method:"PUT",
        body:JSON.stringify({
          type:draft.type,
          server:draft.type==="direct"?null:draft.server.trim(),
          server_port:draft.type==="direct"?null:Number(draft.port),
          username:draft.type==="direct"?null:(draft.username||null),
          password:draft.type==="direct"?null:(draft.password||null),
          set_default:draft.setDefault,
        }),
      });
      setNotice(pick("Outbound پس از اعتبارسنجی Sing-box اعمال شد.","Outbound was applied after Sing-box validation."));
      reset();
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const makeDefault=async(tag:string)=>{
    if(!node)return;
    setBusy(`default:${tag}`);setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/default`,{method:"POST",body:JSON.stringify({tag})});
      setNotice(pick(`خروجی پیش‌فرض روی ${tag} قرار گرفت.`,`Default outbound is now ${tag}.`));
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const clearDefault=async()=>{
    if(!node)return;
    setBusy("clear-default");setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/default/clear`,{method:"POST"});
      setNotice(pick("انتخاب صریح خروجی پیش‌فرض حذف شد.","Explicit default outbound was cleared."));
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const remove=async(tag:string)=>{
    if(!node||tag==="direct")return;
    if(!window.confirm(pick(`Outbound «${tag}» حذف شود؟`,`Delete outbound “${tag}”?`)))return;
    setBusy(`delete:${tag}`);setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(tag)}`,{method:"DELETE"});
      setNotice(pick("Outbound حذف شد.","Outbound deleted."));
      if(editingTag===tag)reset();
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/outbounds">
    <div className={styles.page}>
      <PageHead title={pick("Outbound","Outbound")}/>

      <section className={styles.hero}>
        <div>
          <b>{pick("خروجی Sing-box","Sing-box egress")}</b>
          <p>{pick("مسیر خروج Core را بدون دست‌کاری تونل‌ها مدیریت کنید. هر تغییر ابتدا validate می‌شود و در خطای restart به config قبلی برمی‌گردد.","Manage core egress without changing tunnel routing. Every change is validated first and rolls back if restart fails.")}</p>
        </div>
        <button onClick={()=>void load()} disabled={loading||Boolean(busy)}>{pick("به‌روزرسانی","Refresh")}</button>
      </section>

      {error?<div className={styles.error}>{error}</div>:null}
      {notice?<div className={styles.notice}>{notice}</div>:null}

      <section className={styles.toolbar}>
        <label>{pick("نود","Node")}
          <select value={nodeId} onChange={event=>{setNodeId(Number(event.target.value));reset();}} disabled={loading}>
            {(inventory?.nodes||[]).map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}
          </select>
        </label>
        {node?<div className={styles.nodeState}>
          <Badge tone={node.service_active?"ok":"bad"}>{node.service_active?pick("Core فعال","Core active"):pick("Core غیرفعال","Core inactive")}</Badge>
          <span>{pick("خروجی پیش‌فرض:","Default:")} <b>{node.default_tag||pick("ضمنی","Implicit")}</b></span>
          {node.default_tag?<button onClick={()=>void clearDefault()} disabled={Boolean(busy)}>{pick("حذف انتخاب پیش‌فرض","Clear explicit default")}</button>:null}
        </div>:null}
      </section>

      {loading?<div className={styles.empty}>{pick("در حال دریافت Outboundها...","Loading outbounds...")}</div>:null}
      {!loading&&!node?<div className={styles.empty}>{pick("نود سازگار پیدا نشد.","No compatible node found.")}</div>:null}
      {node&&node.error?<div className={styles.error}>{errorText(node.error)}</div>:null}

      {node?<div className={styles.layout}>
        <section className={styles.list}>
          <div className={styles.sectionTitle}><b>{pick("Outboundهای این نود","Node outbounds")}</b><span>{node.outbounds.length}</span></div>
          {node.outbounds.map(row=>{
            const isDefault=node.default_tag===row.tag;
            return <article className={styles.card} key={row.tag}>
              <div className={styles.cardHead}>
                <div><strong>{row.tag}</strong><small>{row.type.toUpperCase()}</small></div>
                <div className={styles.badges}>{isDefault?<Badge tone="violet">{pick("پیش‌فرض","Default")}</Badge>:null}{!row.managed?<Badge tone="warn">{pick("فقط خواندنی","Read only")}</Badge>:null}</div>
              </div>
              <div className={styles.meta}>
                {row.server?<span>{row.server}:{row.server_port||"—"}</span>:<span>{pick("خروج مستقیم اینترنت","Direct Internet")}</span>}
                {row.username?<span>{pick("کاربر:","User:")} {row.username}</span>:null}
                {row.has_password?<span>{pick("رمز: ذخیره شده","Password: saved")}</span>:null}
              </div>
              <div className={styles.actions}>
                {!isDefault?<button onClick={()=>void makeDefault(row.tag)} disabled={Boolean(busy)}>{pick("پیش‌فرض کن","Set default")}</button>:null}
                {row.managed?<button onClick={()=>edit(row)} disabled={Boolean(busy)}>{pick("ویرایش","Edit")}</button>:null}
                {row.managed&&row.tag!=="direct"?<button className={styles.danger} onClick={()=>void remove(row.tag)} disabled={Boolean(busy)}>{pick("حذف","Delete")}</button>:null}
              </div>
            </article>;
          })}
          {!node.outbounds.length?<div className={styles.empty}>{pick("Outbound ثبت‌شده‌ای در config پیدا نشد.","No outbounds found in config.")}</div>:null}
        </section>

        <section className={styles.editor}>
          <div className={styles.sectionTitle}><b>{editingTag?pick("ویرایش Outbound","Edit outbound"):pick("Outbound جدید","New outbound")}</b></div>
          <label>Tag<input value={draft.tag} disabled={Boolean(editingTag)} placeholder="proxy-de" onChange={event=>setDraft({...draft,tag:event.target.value})}/></label>
          <label>{pick("نوع","Type")}
            <select value={draft.type} disabled={draft.tag==="direct"} onChange={event=>{
              const type=event.target.value as Draft["type"];
              setDraft({...draft,type,port:type==="http"?"8080":type==="socks"?"1080":""});
            }}>
              <option value="socks">SOCKS5</option><option value="http">HTTP Proxy</option><option value="direct">Direct</option>
            </select>
          </label>
          {draft.type!=="direct"?<>
            <label>{pick("آدرس Proxy","Proxy server")}<input value={draft.server} placeholder="proxy.example.com" onChange={event=>setDraft({...draft,server:event.target.value})}/></label>
            <label>{pick("پورت","Port")}<input type="number" min="1" max="65535" value={draft.port} onChange={event=>setDraft({...draft,port:event.target.value})}/></label>
            <label>{pick("نام کاربری (اختیاری)","Username (optional)")}<input value={draft.username} onChange={event=>setDraft({...draft,username:event.target.value})}/></label>
            <label>{pick(editingTag?"رمز جدید؛ خالی = حفظ قبلی":"رمز (اختیاری)",editingTag?"New password; blank = keep existing":"Password (optional)")}<input type="password" value={draft.password} onChange={event=>setDraft({...draft,password:event.target.value})}/></label>
          </>:null}
          <label className={styles.check}><input type="checkbox" checked={draft.setDefault} onChange={event=>setDraft({...draft,setDefault:event.target.checked})}/><span>{pick("بعد از ذخیره خروجی پیش‌فرض شود","Set as default after save")}</span></label>
          <div className={styles.editorActions}><button className={styles.primary} onClick={()=>void save()} disabled={Boolean(busy)||Boolean(node.error)}>{busy==="save"?pick("در حال اعمال...","Applying..."):pick("ذخیره و اعمال امن","Validate & apply")}</button>{editingTag?<button onClick={reset}>{pick("انصراف","Cancel")}</button>:null}</div>
          <p className={styles.hint}>{pick("ساخت Outbound به‌تنهایی مسیر کاربران را عوض نمی‌کند؛ فقط با «پیش‌فرض کن» یا گزینه بالا route.final تغییر می‌کند.","Creating an outbound alone does not change user routing; route.final changes only when you explicitly select it as default.")}</p>
        </section>
      </div>:null}
    </div>
  </Shell>;
}
