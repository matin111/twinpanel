"use client";

import {useEffect, useMemo, useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge, PageHead, Shell} from "./ui";
import styles from "./singbox-outbound-center.module.css";


type TransportInfo={
  type?:string;
  path?:string;
  headers?:Record<string,string>;
};

type TlsInfo={
  enabled?:boolean;
  server_name?:string;
};

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
  transport?:TransportInfo;
  tls?:TlsInfo;
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

type TestResult={
  ok:boolean;
  node_id:number;
  tag:string;
  tcp_ok:boolean;
  tcp_ms?:number|null;
  e2e_ok:boolean;
  exit_ip?:string|null;
  http_code?:number|null;
  latency_ms?:number|null;
  error?:string|null;
};

type Draft={
  config:string;
  setDefault:boolean;
};

type EditDraft={
  server:string;
  serverPort:string;
  host:string;
  path:string;
  sni:string;
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

function headerValue(headers:Record<string,string>|undefined,name:string):string{
  if(!headers)return "";
  const wanted=name.toLowerCase();
  const key=Object.keys(headers).find(item=>item.toLowerCase()===wanted);
  return key?String(headers[key]||""):"";
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
  const [tests,setTests]=useState<Record<string,TestResult>>({});
  const [editingTag,setEditingTag]=useState("");
  const [editDraft,setEditDraft]=useState<EditDraft|null>(null);

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
  const preferredOutbound=useMemo(
    ()=>node?.outbounds.find(item=>item.imported&&item.managed)||null,
    [node],
  );
  const nodeOutboundEnabled=Boolean(node?.default_tag&&node.default_tag!=="direct");

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
      setNotice(pick(`خروجی پیش‌فرض این نود روی ${tag} قرار گرفت.`,`Default outbound for this node is now ${tag}.`));
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const clearDefault=async()=>{
    if(!node)return;
    setBusy("clear-default");setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/default/clear`,{method:"POST"});
      setNotice(pick("Outbound برای این نود غیرفعال شد و مسیر پیش‌فرض به حالت Direct/ضمنی برگشت.","Outbound was disabled for this node and the default path returned to Direct/implicit mode."));
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const toggleNodeOutbound=async()=>{
    if(nodeOutboundEnabled){
      await clearDefault();
      return;
    }
    if(!preferredOutbound){
      setError(pick("ابتدا یک کانفیگ Outbound برای این نود اضافه کنید.","Add an outbound config to this node first."));
      return;
    }
    await makeDefault(preferredOutbound.tag);
  };

  const remove=async(tag:string)=>{
    if(!node||tag==="direct")return;
    if(!window.confirm(pick(`Outbound «${tag}» حذف شود؟`,`Delete outbound “${tag}”?`)))return;
    setBusy(`delete:${tag}`);setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(tag)}`,{method:"DELETE"});
      setTests(current=>{const next={...current};delete next[tag];return next;});
      if(editingTag===tag){setEditingTag("");setEditDraft(null);}
      setNotice(pick("Outbound حذف شد.","Outbound deleted."));
      await load(true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const testOutbound=async(tag:string)=>{
    if(!node)return;
    setBusy(`test:${tag}`);setError("");setNotice("");
    try{
      const result=await request<TestResult>(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(tag)}/test`,{method:"POST"});
      setTests(current=>({...current,[tag]:result}));
      setNotice(
        result.ok
          ?pick(`تست واقعی ${tag} موفق بود؛ Exit IP: ${result.exit_ip||"—"}`,`${tag} passed the real egress test; Exit IP: ${result.exit_ip||"—"}`)
          :pick(`تست ${tag} ناموفق بود.`,`Outbound test failed for ${tag}.`),
      );
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const openEdit=(row:OutboundRow)=>{
    setEditingTag(row.tag);
    setEditDraft({
      server:row.server||"",
      serverPort:row.server_port?String(row.server_port):"",
      host:headerValue(row.transport?.headers,"Host"),
      path:row.transport?.path||"",
      sni:row.tls?.server_name||"",
    });
    setError("");setNotice("");
  };

  const saveEdit=async()=>{
    if(!node||!editingTag||!editDraft)return;
    const port=Number(editDraft.serverPort);
    if(!editDraft.server.trim()||!Number.isInteger(port)||port<1||port>65535){
      setError(pick("آدرس/IP و پورت معتبر وارد کنید.","Enter a valid address/IP and port."));
      return;
    }
    setBusy(`edit:${editingTag}`);setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(editingTag)}`,{
        method:"PATCH",
        body:JSON.stringify({
          server:editDraft.server.trim(),
          server_port:port,
          host:editDraft.host.trim(),
          path:editDraft.path.trim(),
          ...(editDraft.sni.trim()?{sni:editDraft.sni.trim()}:{}),
        }),
      });
      setTests(current=>{const next={...current};delete next[editingTag];return next;});
      setNotice(pick("Outbound ویرایش، اعتبارسنجی و اعمال شد. برای اطمینان «تست اتصال» را اجرا کنید.","Outbound was edited, validated, and applied. Run Connection Test to verify data-plane health."));
      setEditingTag("");setEditDraft(null);
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
          <p>{pick("کانفیگ VLESS، VMess، Trojan یا Shadowsocks را Paste کنید. برای هر نود می‌توانید Outbound را جداگانه فعال/غیرفعال، ویرایش و با تست واقعی Exit IP بررسی کنید.","Paste a VLESS, VMess, Trojan, or Shadowsocks config. Each node can enable/disable, edit, and verify its outbound with a real Exit-IP test independently.")}</p>
        </div>
        <button onClick={()=>void load()} disabled={loading||Boolean(busy)}>{pick("به‌روزرسانی","Refresh")}</button>
      </section>

      {error?<div className={styles.error}>{error}</div>:null}
      {notice?<div className={styles.notice}>{notice}</div>:null}

      <section className={styles.toolbar}>
        <label>{pick("نود","Node")}
          <select value={nodeId} onChange={event=>{setNodeId(Number(event.target.value));setDraft(EMPTY);setEditingTag("");setEditDraft(null);setTests({});}} disabled={loading}>
            {(inventory?.nodes||[]).map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}
          </select>
        </label>
        {node?<div className={styles.nodeState}>
          <Badge tone={node.service_active?"ok":"bad"}>{node.service_active?pick("Core فعال","Core active"):pick("Core غیرفعال","Core inactive")}</Badge>
          <Badge tone={nodeOutboundEnabled?"violet":"warn"}>{nodeOutboundEnabled?pick("Outbound نود: فعال","Node outbound: ON"):pick("Outbound نود: غیرفعال","Node outbound: OFF")}</Badge>
          <span>{pick("خروجی:","Egress:")} <b>{node.default_tag||pick("Direct / ضمنی","Direct / implicit")}</b></span>
          <button
            onClick={()=>void toggleNodeOutbound()}
            disabled={Boolean(busy)||(!nodeOutboundEnabled&&!preferredOutbound)}
          >
            {nodeOutboundEnabled?pick("غیرفعال کردن برای این نود","Disable on this node"):pick("فعال کردن برای این نود","Enable on this node")}
          </button>
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
            const result=tests[row.tag];
            const isEditing=editingTag===row.tag&&editDraft;
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
                {row.transport?.type?<span>{pick("Transport:","Transport:")} {row.transport.type.toUpperCase()}</span>:null}
                {headerValue(row.transport?.headers,"Host")?<span>Host: {headerValue(row.transport?.headers,"Host")}</span>:null}
                {row.transport?.path?<span>Path: {row.transport.path}</span>:null}
                {row.tls?.server_name?<span>SNI: {row.tls.server_name}</span>:null}
                {row.username?<span>{pick("کاربر:","User:")} {row.username}</span>:null}
                {row.has_password?<span>{pick("رمز: ذخیره شده","Password: saved")}</span>:null}
              </div>

              {result?<div className={`${styles.testResult} ${result.ok?styles.testPass:styles.testFail}`}>
                <b>{result.ok?pick("تست واقعی موفق","Real egress test passed"):pick("تست واقعی ناموفق","Real egress test failed")}</b>
                <span>TCP: {result.tcp_ok?"PASS":"FAIL"}{result.tcp_ms!=null?` · ${result.tcp_ms} ms`:""}</span>
                <span>Exit IP: {result.exit_ip||"—"}</span>
                <span>HTTP: {result.http_code??"—"}</span>
                <span>Latency: {result.latency_ms!=null?`${result.latency_ms} ms`:"—"}</span>
                {result.error?<small>{result.error}</small>:null}
              </div>:null}

              {isEditing?<div className={styles.inlineEditor}>
                <div className={styles.editGrid}>
                  <label>{pick("آدرس / IP","Address / IP")}
                    <input dir="ltr" value={editDraft.server} onChange={event=>setEditDraft({...editDraft,server:event.target.value})}/>
                  </label>
                  <label>{pick("پورت","Port")}
                    <input dir="ltr" inputMode="numeric" value={editDraft.serverPort} onChange={event=>setEditDraft({...editDraft,serverPort:event.target.value})}/>
                  </label>
                  <label>Host
                    <input dir="ltr" value={editDraft.host} onChange={event=>setEditDraft({...editDraft,host:event.target.value})}/>
                  </label>
                  <label>Path
                    <input dir="ltr" value={editDraft.path} onChange={event=>setEditDraft({...editDraft,path:event.target.value})}/>
                  </label>
                  <label>SNI
                    <input dir="ltr" value={editDraft.sni} onChange={event=>setEditDraft({...editDraft,sni:event.target.value})}/>
                  </label>
                </div>
                <div className={styles.editorActions}>
                  <button className={styles.primary} onClick={()=>void saveEdit()} disabled={Boolean(busy)}>{busy===`edit:${row.tag}`?pick("در حال اعمال...","Applying..."):pick("ذخیره و اعمال امن","Save & apply safely")}</button>
                  <button onClick={()=>{setEditingTag("");setEditDraft(null);}} disabled={Boolean(busy)}>{pick("انصراف","Cancel")}</button>
                </div>
                <p className={styles.hint}>{pick("UUID/Password و سایر پارامترهای کانفیگ دست‌نخورده می‌مانند. قبل از اعمال، Sing-box check و Backup انجام می‌شود.","UUID/password and all other config fields are preserved. Sing-box check and backup run before activation.")}</p>
              </div>:null}

              <div className={styles.actions}>
                {row.imported&&row.managed?<button onClick={()=>void testOutbound(row.tag)} disabled={Boolean(busy)}>{busy===`test:${row.tag}`?pick("در حال تست...","Testing..."):pick("تست اتصال","Connection test")}</button>:null}
                {row.imported&&row.managed?<button onClick={()=>openEdit(row)} disabled={Boolean(busy)}>{pick("ویرایش","Edit")}</button>:null}
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
            <span>{pick("بعد از بررسی و ذخیره، همین کانفیگ خروجی فعال این نود شود","After validation, make this config the active egress for this node")}</span>
          </label>
          <div className={styles.editorActions}>
            <button className={styles.primary} onClick={()=>void importConfig()} disabled={Boolean(busy)||Boolean(node.error)||!draft.config.trim()}>
              {busy==="import"?pick("در حال بررسی و اعمال...","Validating and applying..."):pick("بررسی، ذخیره و فعال‌سازی","Validate, save & activate")}
            </button>
            {draft.config?<button onClick={()=>setDraft(EMPTY)} disabled={Boolean(busy)}>{pick("پاک کردن","Clear")}</button>:null}
          </div>
          <p className={styles.hint}>{pick("قبل از جایگزینی config، Sing-box check اجرا و نسخه قبلی Backup می‌شود. تست اتصال نیز بدون تغییر سرویس اصلی روی همان Node اجرا می‌شود.","Before replacement, Sing-box validates the config and TwinPanel backs up the previous version. Connection tests run on the same node without changing the main service.")}</p>
        </section>
      </div>:null}
    </div>
  </Shell>;
}
