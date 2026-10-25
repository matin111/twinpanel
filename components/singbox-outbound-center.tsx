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
  imported?:boolean;
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
  supported_import_types?:string[];
  nodes:OutboundNode[];
};

type ImportResult={
  ok:boolean;
  node_id:number;
  tag:string;
  type:string;
  label:string;
  set_default:boolean;
};

type Draft={
  config:string;
  setDefault:boolean;
};

const EMPTY:Draft={config:"",setDefault:true};

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

function protocolTitle(value:string):string{
  const key=String(value||"").toLowerCase();
  if(key==="vless")return "VLESS";
  if(key==="vmess")return "VMess";
  if(key==="trojan")return "Trojan";
  if(key==="shadowsocks")return "Shadowsocks";
  if(key==="direct")return "DIRECT";
  if(key==="socks")return "SOCKS5";
  if(key==="http")return "HTTP";
  return key.toUpperCase();
}

export function SingboxOutboundCenter(){
  const {pick}=useI18n();
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [nodeId,setNodeId]=useState(0);
  const [draft,setDraft]=useState<Draft>(EMPTY);
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
  const supported=inventory?.supported_import_types||["vless","vmess","trojan","shadowsocks"];

  const importConfig=async()=>{
    if(!node)return;
    const config=draft.config.trim();
    if(!config){
      setError(pick("کانفیگ را Paste کنید.","Paste a config first."));
      return;
    }
    setBusy("import");setError("");setNotice("");
    try{
      const result=await request<ImportResult>(`/v1/settings/vpn/outbounds/${node.id}/import`,{
        method:"POST",
        body:JSON.stringify({config,set_default:draft.setDefault}),
      });
      setDraft(EMPTY);
      setNotice(
        draft.setDefault
          ?pick(`کانفیگ ${protocolTitle(result.type)} بررسی، ذخیره و به خروجی پیش‌فرض تبدیل شد.`,`The ${protocolTitle(result.type)} config was validated, saved, and activated as the default egress.`)
          :pick(`کانفیگ ${protocolTitle(result.type)} بررسی و ذخیره شد.`,`The ${protocolTitle(result.type)} config was validated and saved.`),
      );
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
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/outbounds">
    <div className={styles.page}>
      <PageHead title={pick("Outbound","Outbound")}/>

      <section className={styles.hero}>
        <div>
          <b>{pick("خروجی با کانفیگ V2Ray","Config-based egress")}</b>
          <p>{pick("کانفیگ VLESS، VMess، Trojan یا Shadowsocks را Paste کنید. TwinPanel آن را به Outbound واقعی Sing-box تبدیل می‌کند، قبل از اعمال اعتبارسنجی می‌کند و در خطا به config قبلی برمی‌گردد.","Paste a VLESS, VMess, Trojan, or Shadowsocks config. TwinPanel converts it to a real Sing-box outbound, validates it before activation, and rolls back on failure.")}</p>
        </div>
        <button onClick={()=>void load()} disabled={loading||Boolean(busy)}>{pick("به‌روزرسانی","Refresh")}</button>
      </section>

      {error?<div className={styles.error}>{error}</div>:null}
      {notice?<div className={styles.notice}>{notice}</div>:null}

      <section className={styles.toolbar}>
        <label>{pick("نود","Node")}
          <select value={nodeId} onChange={event=>{setNodeId(Number(event.target.value));setDraft(EMPTY);}} disabled={loading}>
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
                <div><strong>{row.tag}</strong><small>{protocolTitle(row.type)}</small></div>
                <div className={styles.badges}>
                  {isDefault?<Badge tone="violet">{pick("فعال / پیش‌فرض","Active / Default")}</Badge>:null}
                  {row.imported?<Badge tone="ok">{pick("کانفیگ واردشده","Imported config")}</Badge>:null}
                  {!row.managed?<Badge tone="warn">{pick("فقط خواندنی","Read only")}</Badge>:null}
                </div>
              </div>
              <div className={styles.meta}>
                {row.server?<span>{row.server}:{row.server_port||"—"}</span>:<span>{pick("خروج مستقیم اینترنت","Direct Internet")}</span>}
                {row.username?<span>{pick("کاربر:","User:")} {row.username}</span>:null}
                {row.has_password?<span>{pick("رمز: ذخیره شده","Password: saved")}</span>:null}
              </div>
              <div className={styles.actions}>
                {!isDefault?<button onClick={()=>void makeDefault(row.tag)} disabled={Boolean(busy)}>{pick("استفاده به‌عنوان خروجی","Use as egress")}</button>:null}
                {row.managed&&row.tag!=="direct"?<button className={styles.danger} onClick={()=>void remove(row.tag)} disabled={Boolean(busy)}>{pick("حذف","Delete")}</button>:null}
              </div>
            </article>;
          })}
          {!node.outbounds.length?<div className={styles.empty}>{pick("Outbound ثبت‌شده‌ای در config پیدا نشد.","No outbounds found in config.")}</div>:null}
        </section>

        <section className={styles.editor}>
          <div className={styles.sectionTitle}><b>{pick("افزودن Outbound با کانفیگ","Add outbound from config")}</b></div>
          <p className={styles.intro}>{pick("فقط کانفیگ را Paste کن؛ Tag، پروتکل، سرور، پورت، TLS و Transport به‌صورت خودکار استخراج می‌شوند.","Just paste the config; tag, protocol, server, port, TLS, and transport are detected automatically.")}</p>
          <div className={styles.protocols}>
            {supported.map(item=><span key={item}>{protocolTitle(item)}</span>)}
          </div>
          <label>{pick("کانفیگ V2Ray / Sing-box","V2Ray / Sing-box config")}
            <textarea
              dir="ltr"
              value={draft.config}
              placeholder={"vless://...\nvmess://...\ntrojan://...\nss://...\n\nیا یک Outbound JSON از Sing-box"}
              spellCheck={false}
              onChange={event=>setDraft({...draft,config:event.target.value})}
            />
          </label>
          <label className={styles.check}>
            <input type="checkbox" checked={draft.setDefault} onChange={event=>setDraft({...draft,setDefault:event.target.checked})}/>
            <span>{pick("بعد از بررسی و ذخیره، همین کانفیگ خروجی فعال شود","After validation, make this config the active egress")}</span>
          </label>
          <div className={styles.editorActions}>
            <button className={styles.primary} onClick={()=>void importConfig()} disabled={Boolean(busy)||Boolean(node.error)||!draft.config.trim()}>
              {busy==="import"?pick("در حال بررسی و اعمال...","Validating and applying..."):pick("بررسی، ذخیره و فعال‌سازی","Validate, save & activate")}
            </button>
            {draft.config?<button onClick={()=>setDraft(EMPTY)} disabled={Boolean(busy)}>{pick("پاک کردن","Clear")}</button>:null}
          </div>
          <p className={styles.hint}>{pick("قبل از جایگزینی config، Sing-box check اجرا و نسخه قبلی Backup می‌شود. اگر restart یا health سرویس شکست بخورد، rollback خودکار انجام می‌شود.","Before replacement, Sing-box validates the config and TwinPanel backs up the previous version. Restart/service failures trigger automatic rollback.")}</p>
        </section>
      </div>:null}
    </div>
  </Shell>;
}
