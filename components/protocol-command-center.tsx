"use client";

import {useEffect, useMemo, useState} from "react";

import {adminApi, type XrayDomainState} from "../lib/admin-api";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {
  legacyAdminApi,
  type ClassicProtocolInventoryNode,
  type ClassicProtocolInventoryRow,
  type ClassicProtocolKey,
} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";
import {Badge, PageHead, Shell} from "./ui";
import styles from "./protocol-command-center.module.css";
import {XrayInboundEditorInProtocol} from "./xray-inbound-editor-in-protocol";


type OptionDef={value:string;label_fa:string;label_en:string};
type FieldDef={
  key:string;
  label_fa:string;
  label_en:string;
  type:string;
  help_fa?:string;
  help_en?:string;
  options?:OptionDef[];
  min?:number|null;
  max?:number|null;
  advanced?:boolean;
  secret?:boolean;
};
type CatalogItem={
  key:string;
  title:string;
  category:string;
  core:string;
  adapter:string;
  runtime_status:string;
  installable:boolean;
  transport:string;
  default_port:number;
  tls:boolean;
  recommended_for:string[];
  formats:Record<string,boolean>;
  platforms:string[];
  presets:Record<string,Record<string,unknown>>;
  fields:FieldDef[];
  warnings?:string[];
};
type ModernProtocolRow={
  protocol:string;
  name:string;
  category:string;
  core:string;
  adapter:string;
  runtime_status:string;
  installable:boolean;
  operator_disabled?:boolean;
  port:number;
  transport:string;
  service:string;
  status:string;
  last_error?:string|null;
  checked_at?:string|null;
  preset:string;
  settings:Record<string,unknown>;
  effective_settings:Record<string,unknown>;
  warnings:string[];
  config_hash?:string|null;
  last_applied_at?:string|null;
};
type ModernNode={
  id:number;
  name:string;
  public_ip:string;
  public_domain?:string|null;
  status:string;
  protocols:ModernProtocolRow[];
};
type ModernInventory={ok:boolean;schema_version:number;catalog:CatalogItem[];nodes:ModernNode[]};
type ModernPreview={
  ok:boolean;
  protocol:string;
  preset:string;
  effective_settings:Record<string,unknown>;
  warnings:string[];
  preview:Record<string,unknown>;
  config_hash:string;
  runtime_status:string;
};
type ModernInstallResult={
  ok:boolean;
  protocols?:Record<string,{ok?:boolean;error?:string|null}>;
  failed_protocols?:string[];
};
type ClassicRuntime={
  protocol?:string;
  name?:string;
  installed?:boolean;
  ok?:boolean;
  service?:string;
  listeners?:Record<string,boolean>;
  port?:number|null;
  port_text?:string;
  transport?:string;
  error?:string|null;
};
type ClassicDraft={port:number;transport:"udp"|"tcp"};
type UnifiedNode={
  id:number;
  name:string;
  public_ip:string;
  public_domain?:string|null;
  status:string;
  classic?:ClassicProtocolInventoryNode;
  modern?:ModernNode;
};
type UnifiedProtocol={
  id:string;
  kind:"classic"|"modern";
  protocol:string;
  name:string;
  core:string;
  transport:string;
  category:string;
  status:string;
  installed:boolean;
  installable:boolean;
  operatorDisabled:boolean;
  portText:string;
  service?:string;
  recommended:boolean;
  error?:string|null;
  classicRow?:ClassicProtocolInventoryRow;
  modernRow?:ModernProtocolRow;
};
type SelectedProtocol={kind:"classic"|"modern";protocol:string}|null;
type ModernEditor={
  node:ModernNode;
  row:ModernProtocolRow;
  definition:CatalogItem;
  port:number;
  preset:string;
  settings:Record<string,unknown>;
  showAdvanced:boolean;
};
type FilterKey="all"|"active"|"classic"|"modern"|"planned";

const CLASSIC_PROTOCOLS:Array<{key:ClassicProtocolKey;label:string;core:string;transport:string;defaultPort:number|null}>=[
  {key:"cisco",label:"Cisco / OpenConnect",core:"ocserv",transport:"TCP + DTLS",defaultPort:443},
  {key:"openvpn",label:"OpenVPN",core:"OpenVPN",transport:"TCP / UDP",defaultPort:1194},
  {key:"wireguard",label:"WireGuard",core:"Kernel WG",transport:"UDP",defaultPort:51820},
  {key:"l2tp",label:"L2TP / IPsec",core:"strongSwan + xl2tpd",transport:"UDP / IPsec",defaultPort:null},
  {key:"v2ray",label:"V2Ray / Xray",core:"Xray",transport:"TCP / TLS / REALITY",defaultPort:8443},
];
const CLASSIC_MAP=new Map(CLASSIC_PROTOCOLS.map(row=>[row.key,row]));
const PRESETS:Record<string,[string,string]>={
  recommended:["پیشنهادی","Recommended"],
  performance:["سرعت","Performance"],
  compatibility:["سازگاری","Compatibility"],
  custom:["سفارشی","Custom"],
};
const WARNING_LABELS:Record<string,[string,string]>={
  trusted_tls_recommended:["برای NaiveProxy گواهی TLS معتبر عمومی بهتر از Self-signed است.","A publicly trusted TLS certificate is recommended for NaiveProxy."],
  security_audit_required:["این Adapter قبل از فعال شدن نیاز به Audit امنیتی دارد.","This adapter requires a security audit before activation."],
  client_ecosystem_limited:["اکوسیستم کلاینت محدود است و فعلاً Production-Ready محسوب نمی‌شود.","Client ecosystem is limited; not production-ready yet."],
  tuic_zero_rtt_replay_risk:["TUIC 0-RTT ریسک Replay دارد؛ خاموش ماندن آن توصیه می‌شود.","TUIC 0-RTT has replay risk; keeping it disabled is recommended."],
  obfs_password_will_be_generated:["رمز Obfuscation به‌صورت امن و پایدار روی نود تولید می‌شود.","A stable secure obfuscation password will be generated on the node."],
  saved_settings_need_review:["تنظیم ذخیره‌شده با Schema جدید نیاز به بازبینی دارد.","Saved settings need review against the new schema."],
};

function classicKey(nodeId:number,protocol:ClassicProtocolKey){return `${nodeId}:${protocol}`;}
function tone(value:string):"ok"|"warn"|"bad"|"violet"{
  const status=String(value||"").toLowerCase();
  if(["online","active","ok","healthy","enabled","ready"].includes(status))return "ok";
  if(["offline","failed","error"].includes(status))return "bad";
  if(status==="not_installed"||status==="disabled"||status.includes("pending"))return "warn";
  return "violet";
}
function iconFor(protocol:string){
  const map:Record<string,string>={
    cisco:"OC",openvpn:"OV",wireguard:"WG",l2tp:"L2",v2ray:"XR",
    hysteria2:"H2",tuic:"TU",anytls:"AT",naiveproxy:"NV",shadowtls:"ST",mieru:"MI",trusttunnel:"TT",snell:"SN",sudoku:"SU",
  };
  return map[protocol.toLowerCase()]||protocol.slice(0,2).toUpperCase();
}
function shownValue(editor:ModernEditor,field:FieldDef):unknown{
  if(field.key in editor.settings)return editor.settings[field.key];
  const preset=editor.preset==="custom"?"recommended":editor.preset;
  return editor.definition.presets?.[preset]?.[field.key]??"";
}
async function modernRequest<T>(path:string,init:RequestInit={}):Promise<T>{
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
      if(detail&&typeof detail==="object"&&"message" in detail)throw new Error(String((detail as {message?:unknown}).message||`API error ${response.status}`));
    }
    throw new Error(`API error ${response.status}`);
  }
  return payload as T;
}

function FieldControl({editor,field,pick,onChange}:{editor:ModernEditor;field:FieldDef;pick:(fa:string,en:string)=>string;onChange:(value:unknown)=>void}){
  const value=shownValue(editor,field);
  const help=pick(field.help_fa||"",field.help_en||"");
  return <div className={`${styles.field} ${field.type==="textarea"?styles.fieldWide:""}`}>
    <label>{pick(field.label_fa,field.label_en)}</label>
    {field.type==="boolean"?(
      <label className={styles.switchRow}><input type="checkbox" checked={Boolean(value)} onChange={event=>onChange(event.target.checked)}/><span>{Boolean(value)?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</span></label>
    ):field.type==="select"?(
      <select value={String(value??"")} onChange={event=>onChange(event.target.value)}>{(field.options||[]).map(option=><option key={option.value} value={option.value}>{pick(option.label_fa,option.label_en)}</option>)}</select>
    ):field.type==="textarea"?(
      <textarea rows={6} value={String(value??"")} onChange={event=>onChange(event.target.value)}/>
    ):(
      <input type={field.type==="number"?"number":field.secret?"password":"text"} min={field.min??undefined} max={field.max??undefined} value={String(value??"")} onChange={event=>onChange(field.type==="number"?Number(event.target.value):event.target.value)}/>
    )}
    {help?<small>{help}</small>:null}
  </div>;
}

export function ProtocolCommandCenter(){
  const {pick}=useI18n();
  const [classicNodes,setClassicNodes]=useState<ClassicProtocolInventoryNode[]>([]);
  const [modernInventory,setModernInventory]=useState<ModernInventory|null>(null);
  const [selectedNodeId,setSelectedNodeId]=useState(0);
  const [selectedProtocol,setSelectedProtocol]=useState<SelectedProtocol>(null);
  const [filter,setFilter]=useState<FilterKey>("all");
  const [query,setQuery]=useState("");
  const [busy,setBusy]=useState("");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [classicRuntime,setClassicRuntime]=useState<Record<string,ClassicRuntime>>({});
  const [classicChecked,setClassicChecked]=useState<Record<string,boolean>>({});
  const [portWarnings,setPortWarnings]=useState<Record<string,string>>({});
  const [classicDrafts,setClassicDrafts]=useState<Record<string,ClassicDraft>>({});
  const [modernEditor,setModernEditor]=useState<ModernEditor|null>(null);
  const [modernPreview,setModernPreview]=useState<ModernPreview|null>(null);
  const [domainMeta,setDomainMeta]=useState<XrayDomainState|null>(null);
  const [domainDraft,setDomainDraft]=useState("");
  const [domainOpen,setDomainOpen]=useState(false);

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    setError("");
    const [classicResult,modernResult]=await Promise.allSettled([
      legacyAdminApi.classicProtocols(),
      modernRequest<ModernInventory>("/v1/settings/vpn/modern-protocols"),
    ]);
    if(classicResult.status==="fulfilled"){
      setClassicNodes(classicResult.value.nodes||[]);
      setClassicDrafts(current=>{
        const next={...current};
        for(const node of classicResult.value.nodes||[]){
          for(const row of node.protocols||[]){
            const def=CLASSIC_MAP.get(row.protocol);
            const key=classicKey(node.id,row.protocol);
            if(!(key in next))next[key]={port:Number(row.port||def?.defaultPort||0),transport:row.protocol==="openvpn"&&row.transport==="tcp"?"tcp":"udp"};
          }
        }
        return next;
      });
    }
    if(modernResult.status==="fulfilled")setModernInventory(modernResult.value);
    const failures=[classicResult,modernResult].filter(result=>result.status==="rejected") as PromiseRejectedResult[];
    if(failures.length===2)setError(failures.map(item=>item.reason instanceof Error?item.reason.message:String(item.reason)).join(" · "));
    else if(failures.length===1)setError(pick("بخشی از Inventory در دسترس نیست؛ بخش سالم همچنان قابل مدیریت است.","Part of the inventory is unavailable; the healthy part remains manageable."));
    if(!silent)setLoading(false);
  };

  useEffect(()=>{void load();},[]);

  const catalogMap=useMemo(()=>{
    const map=new Map<string,CatalogItem>();
    for(const item of modernInventory?.catalog||[])map.set(item.key,item);
    return map;
  },[modernInventory]);

  const nodes=useMemo(()=>{
    const map=new Map<number,UnifiedNode>();
    for(const node of classicNodes){
      map.set(node.id,{id:node.id,name:node.name,public_ip:node.public_ip,public_domain:node.public_domain,status:node.status,classic:node});
    }
    for(const node of modernInventory?.nodes||[]){
      const current=map.get(node.id);
      map.set(node.id,{id:node.id,name:node.name||current?.name||`#${node.id}`,public_ip:node.public_ip||current?.public_ip||"",public_domain:node.public_domain||current?.public_domain,status:node.status||current?.status||"—",classic:current?.classic,modern:node});
    }
    return [...map.values()].sort((a,b)=>a.id-b.id);
  },[classicNodes,modernInventory]);

  useEffect(()=>{
    if(!nodes.length)return;
    let requested=0;
    if(typeof window!=="undefined")requested=Number(new URLSearchParams(window.location.search).get("node")||0);
    setSelectedNodeId(current=>nodes.some(node=>node.id===current)?current:nodes.some(node=>node.id===requested)?requested:nodes[0].id);
  },[nodes]);

  const selectedNode=nodes.find(node=>node.id===selectedNodeId)||null;

  const unifiedProtocols=useMemo(()=>{
    if(!selectedNode)return [] as UnifiedProtocol[];
    const rows:UnifiedProtocol[]=[];
    for(const def of CLASSIC_PROTOCOLS){
      const row=selectedNode.classic?.protocols.find(item=>item.protocol===def.key) || ({
        protocol:def.key,enabled:false,port:def.defaultPort,port_text:def.key==="l2tp"?"500/4500/1701":String(def.defaultPort||""),transport:def.key==="openvpn"?"udp":def.transport,status:"not_installed",
      } satisfies ClassicProtocolInventoryRow);
      rows.push({
        id:`classic:${def.key}`,kind:"classic",protocol:def.key,name:def.label,core:def.core,transport:row.transport||def.transport,category:"classic",status:row.enabled?(row.status||"enabled"):"not_installed",installed:Boolean(row.enabled),installable:true,operatorDisabled:Boolean(row.operator_disabled),portText:row.port_text||"—",service:row.service||undefined,recommended:["cisco","wireguard","v2ray"].includes(def.key),error:row.last_error,classicRow:row,
      });
    }
    for(const row of selectedNode.modern?.protocols||[]){
      rows.push({
        id:`modern:${row.protocol}`,kind:"modern",protocol:row.protocol,name:row.name,core:row.core,transport:row.transport,category:row.category,status:row.status,installed:row.status!=="not_installed",installable:row.installable,operatorDisabled:Boolean(row.operator_disabled),portText:String(row.port||"—"),service:row.service,recommended:row.category==="recommended",error:row.last_error,modernRow:row,
      });
    }
    return rows;
  },[selectedNode]);

  const filteredProtocols=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return unifiedProtocols
      .filter(row=>{
        if(filter==="active"&&!row.installed)return false;
        if(filter==="classic"&&row.kind!=="classic")return false;
        if(filter==="modern"&&row.kind!=="modern")return false;
        if(filter==="planned"&&!(row.kind==="modern"&&!row.installable))return false;
        if(q&&!`${row.name} ${row.protocol} ${row.core} ${row.transport}`.toLowerCase().includes(q))return false;
        return true;
      })
      .sort((a,b)=>{
        const score=(row:UnifiedProtocol)=>(row.installed?0:2)+(row.recommended?0:1)+(row.installable?0:4);
        return score(a)-score(b)||a.name.localeCompare(b.name);
      });
  },[unifiedProtocols,filter,query]);

  const metrics=useMemo(()=>({
    total:unifiedProtocols.length,
    active:unifiedProtocols.filter(row=>row.installed&&!row.operatorDisabled).length,
    healthy:unifiedProtocols.filter(row=>{
      if(row.operatorDisabled)return false;
      if(row.kind==="modern")return row.status==="online";
      const run=classicRuntime[classicKey(selectedNodeId,row.protocol as ClassicProtocolKey)];
      return Boolean(run?.ok);
    }).length,
    planned:unifiedProtocols.filter(row=>row.kind==="modern"&&!row.installable).length,
  }),[unifiedProtocols,classicRuntime,selectedNodeId]);

  const selectedRow=selectedProtocol?unifiedProtocols.find(row=>row.kind===selectedProtocol.kind&&row.protocol===selectedProtocol.protocol)||null:null;

  const selectNode=(id:number)=>{
    setSelectedNodeId(id);setSelectedProtocol(null);setModernEditor(null);setDomainOpen(false);setError("");setNotice("");
    if(typeof window!=="undefined"){
      const url=new URL(window.location.href);url.searchParams.set("node",String(id));window.history.replaceState({},"",url.toString());
    }
  };

  const openProtocol=(row:UnifiedProtocol)=>{
    setSelectedProtocol({kind:row.kind,protocol:row.protocol});setError("");setNotice("");setDomainOpen(false);setDomainMeta(null);setModernPreview(null);
    if(row.kind==="modern"&&row.modernRow&&selectedNode?.modern){
      const definition=catalogMap.get(row.protocol);
      if(definition)setModernEditor({node:selectedNode.modern,row:row.modernRow,definition,port:row.modernRow.port,preset:row.modernRow.preset||"recommended",settings:{...(row.modernRow.settings||{})},showAdvanced:false});
    }else setModernEditor(null);
  };

  const classicHealth=async(row:UnifiedProtocol)=>{
    if(!selectedNode?.classic||row.kind!=="classic"||busy)return;
    const protocol=row.protocol as ClassicProtocolKey;
    const key=classicKey(selectedNode.id,protocol);
    setBusy(`classic-health:${key}`);setError("");setNotice("");
    try{
      const result=await legacyAdminApi.protocolHealth(selectedNode.id,protocol);
      const protocols=result&&typeof result.protocols==="object"&&result.protocols?result.protocols as Record<string,ClassicRuntime>:{};
      const runtimeRow=protocols[protocol]||{};
      setClassicRuntime(current=>({...current,[key]:runtimeRow}));setClassicChecked(current=>({...current,[key]:true}));
      setNotice(runtimeRow.ok?pick(`${row.name} سالم است.`,`${row.name} is healthy.`):pick(`${row.name} نیاز به بررسی دارد.`,`${row.name} needs attention.`));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const checkClassicPort=async(row:UnifiedProtocol)=>{
    if(!selectedNode||row.kind!=="classic"||row.protocol==="l2tp"||busy)return;
    const protocol=row.protocol as ClassicProtocolKey;
    const key=classicKey(selectedNode.id,protocol);
    const draft=classicDrafts[key]||{port:Number(row.classicRow?.port||CLASSIC_MAP.get(protocol)?.defaultPort||0),transport:"udp" as const};
    setBusy(`port-check:${key}`);setError("");
    try{
      const result=await legacyAdminApi.classicPortCheck({node_id:selectedNode.id,protocol,port:draft.port,...(protocol==="openvpn"?{transport:draft.transport}:{})});
      setPortWarnings(current=>({...current,[key]:result.available?pick("پورت‌های انتخاب‌شده آزاد هستند.","Selected ports are available."):pick(`تداخل پورت: ${result.conflicts.map(x=>`${x.port}/${x.transport.toUpperCase()}`).join("، ")}. پورت دیگری انتخاب کنید؛ سرویس فعلی تغییر نمی‌کند.`,`Port conflict: ${result.conflicts.map(x=>`${x.port}/${x.transport.toUpperCase()}`).join(", ")}. Choose another port; the current service stays unchanged.`)}));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const ensureClassic=async(row:UnifiedProtocol)=>{
    if(!selectedNode?.classic||row.kind!=="classic"||!row.classicRow||busy)return;
    const protocol=row.protocol as ClassicProtocolKey;
    const def=CLASSIC_MAP.get(protocol);if(!def)return;
    const key=classicKey(selectedNode.id,protocol);
    const draft=classicDrafts[key]||{port:Number(row.classicRow.port||def.defaultPort||0),transport:row.classicRow.transport==="tcp"?"tcp":"udp"};
    setBusy(`classic-ensure:${key}`);setError("");setNotice("");
    try{
      if(!row.installed&&protocol!=="l2tp"){
        const probe=await legacyAdminApi.classicPortCheck({node_id:selectedNode.id,protocol,port:draft.port,...(protocol==="openvpn"?{transport:draft.transport}:{})});
        if(!probe.available){
          const ports=probe.conflicts.map(item=>`${item.port}/${item.transport.toUpperCase()}`).join(", ");
          setSelectedProtocol({kind:"classic",protocol});
          setError(pick(`تداخل پورت ${ports}. در مدیریت پروتکل پورت آزاد انتخاب کنید؛ هیچ سرویس فعالی متوقف نمی‌شود.`,`Port conflict ${ports}. Choose a free port in protocol management; no running services will be stopped.`));
          return;
        }
      }
      const result=await legacyAdminApi.ensureClassicProtocol({node_id:selectedNode.id,protocol,...(protocol==="l2tp"?{}:{port:draft.port}),...(protocol==="openvpn"?{transport:draft.transport}:{})});
      const runtimeRow=result&&typeof result.runtime==="object"&&result.runtime?result.runtime as ClassicRuntime:{};
      setClassicRuntime(current=>({...current,[key]:runtimeRow}));setClassicChecked(current=>({...current,[key]:true}));
      setNotice(pick(`${row.name} نصب/Repair و Health Check شد.`,`${row.name} was installed/repaired and health-checked.`));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));await load(true).catch(()=>undefined);}
    finally{setBusy("");}
  };

  const restartClassic=async(row:UnifiedProtocol)=>{
    if(!selectedNode||row.kind!=="classic"||busy)return;
    const key=classicKey(selectedNode.id,row.protocol as ClassicProtocolKey);
    if(!row.installed||!window.confirm(pick("ری‌استارت "+row.name+" روی "+selectedNode.name+" اتصال‌های فعلی همین پروتکل را موقتاً قطع می‌کند. ادامه می‌دهید؟","Restarting "+row.name+" on "+selectedNode.name+" briefly interrupts connections using this protocol. Continue?")))return;
    setBusy("classic-restart:"+key);setError("");setNotice("");
    try{
      const result=await legacyAdminApi.restartProtocol(selectedNode.id,row.protocol);
      const runtimeRow=result&&typeof result.protocol==="object"&&result.protocol?result.protocol as ClassicRuntime:{};
      setClassicRuntime(current=>({...current,[key]:runtimeRow}));setClassicChecked(current=>({...current,[key]:true}));
      if(runtimeRow.ok===false)throw new Error(pick("سرویس ری‌استارت شد ولی Health Check موفق نبود.","Restart completed but health check failed."));
      setNotice(pick(row.name+" روی "+selectedNode.name+" ری‌استارت و بررسی شد.",row.name+" on "+selectedNode.name+" restarted and checked."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };


  const restartOnNode=async(row:UnifiedProtocol)=>{
    if(!selectedNode||!row.installed||busy)return;
    if(row.kind==="classic"){await restartClassic(row);return;}
    const shared=!["mieru","trusttunnel","amneziawg","sudoku"].includes(row.protocol);
    const warning=shared
      ?pick("این پروتکل روی Core مشترک sing-box است؛ ری‌استارت آن سایر پروتکل‌های مدرن همین نود را هم برای چند لحظه قطع می‌کند.","This protocol uses the shared sing-box core; restarting briefly interrupts all sing-box protocols on this node.")
      :pick("اتصال کاربران همین پروتکل برای چند لحظه قطع می‌شود.","Connections using this protocol will be briefly interrupted.");
    if(!window.confirm(pick("ری‌استارت "+row.name+" روی "+selectedNode.name+"؟\\n"+warning,"Restart "+row.name+" on "+selectedNode.name+"?\\n"+warning)))return;
    setBusy("modern-restart:"+selectedNode.id+":"+row.protocol);setError("");setNotice("");
    try{
      const result=await modernRequest<{ok:boolean;message?:string}>("/v1/settings/vpn/modern-protocols/"+selectedNode.id+"/"+row.protocol+"/restart",{method:"POST"});
      await load(true);
      if(!result.ok)throw new Error(result.message||pick("پس از ری‌استارت Health Check موفق نبود.","Health check failed after restart."));
      setNotice(pick(row.name+" روی "+selectedNode.name+" با موفقیت ری‌استارت شد.",row.name+" was restarted on "+selectedNode.name+"."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const toggleOnNode=async(row:UnifiedProtocol)=>{
    if(!selectedNode||!row.installed||busy)return;
    const disabled=!row.operatorDisabled;
    const message=disabled
      ?pick("فقط "+row.name+" روی نود "+selectedNode.name+" از فهرست سرورها و کانفیگ‌های جدید کاربران مخفی شود؟\\n\\nسرویس متوقف نمی‌شود و اتصال‌های فعلی قطع نخواهند شد.","Hide only "+row.name+" on node "+selectedNode.name+" from newly fetched configs?\\n\\nThe runtime and existing connections remain untouched.")
      :pick(row.name+" روی نود "+selectedNode.name+" دوباره برای دریافت کانفیگ فعال شود؟","Make "+row.name+" on "+selectedNode.name+" available in fetched configs again?");
    if(!window.confirm(message))return;
    setBusy("node-toggle:"+selectedNode.id+":"+row.protocol);setError("");setNotice("");
    try{
      await modernRequest("/v1/admin/node-protocol-controls/"+selectedNode.id+"/"+row.protocol,{method:"PUT",body:JSON.stringify({disabled})});
      await load(true);
      setNotice(disabled
        ?pick(row.name+" فقط روی نود "+selectedNode.name+" برای کانفیگ‌های جدید غیرفعال شد.",row.name+" was hidden for new configs on "+selectedNode.name+".")
        :pick(row.name+" روی نود "+selectedNode.name+" دوباره فعال شد.",row.name+" on "+selectedNode.name+" was enabled again."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const modernApply=async(editor:ModernEditor)=>{
    if(busy||!editor.definition.installable)return;
    const key=`${editor.node.id}:${editor.row.protocol}`;setBusy(`modern-apply:${key}`);setError("");setNotice("");
    try{
      await modernRequest(`/v1/settings/vpn/modern-protocols/${editor.node.id}/install`,{method:"POST",body:JSON.stringify({protocols:[editor.row.protocol],ports:{[editor.row.protocol]:editor.port},profiles:{[editor.row.protocol]:{preset:editor.preset,settings:editor.settings}}})});
      setNotice(pick(`${editor.row.name} اعمال و Health Check شد.`,`${editor.row.name} was applied and health-checked.`));await load(true);setSelectedProtocol(null);setModernEditor(null);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const modernSyncAll=async()=>{
    const node=selectedNode?.modern;
    if(!node||busy)return;
    const rows=node.protocols.filter(row=>row.installable&&!row.operator_disabled&&Boolean(catalogMap.get(row.protocol)?.installable));
    if(!rows.length){
      setError("");
      setNotice(pick("هیچ پروتکل مدرن قابل همگام‌سازی روی این نود وجود ندارد.","There are no installable modern protocols to sync on this node."));
      return;
    }
    const protocols=rows.map(row=>row.protocol);
    const ports=Object.fromEntries(rows.map(row=>[row.protocol,row.port]));
    const profiles=Object.fromEntries(rows.map(row=>[row.protocol,{preset:row.preset||"recommended",settings:{...(row.settings||{})}}]));
    const busyKey=`modern-sync-all:${node.id}`;
    setBusy(busyKey);setError("");setNotice("");
    try{
      const result=await modernRequest<ModernInstallResult>(`/v1/settings/vpn/modern-protocols/${node.id}/install`,{method:"POST",body:JSON.stringify({protocols,ports,profiles})});
      await load(true);
      const failed=new Set(result.failed_protocols||[]);
      if(!result.ok){
        for(const row of rows){
          if(result.protocols?.[row.protocol]?.ok===false)failed.add(row.protocol);
        }
      }
      if(failed.size||!result.ok){
        const labels=[...failed].map(key=>rows.find(row=>row.protocol===key)?.name||key);
        setError(labels.length
          ?pick(`همگام‌سازی کامل نشد؛ پروتکل‌های ناموفق: ${labels.join("، ")}`,`Sync completed with failures: ${labels.join(", ")}`)
          :pick("همگام‌سازی کامل نشد؛ وضعیت پروتکل‌ها را بررسی کنید.","Sync did not complete successfully; review protocol status."));
        return;
      }
      setNotice(pick(`${rows.length.toLocaleString("fa-IR")} پروتکل مدرن روی ${node.name} همگام شدند.`,`${rows.length} modern protocols were synced on ${node.name}.`));
    }catch(reason){
      const message=reason instanceof Error?reason.message:String(reason);
      await load(true).catch(()=>undefined);
      setError(message);
    }finally{setBusy("");}
  };

  const modernHealth=async(row:UnifiedProtocol)=>{
    if(!selectedNode?.modern||row.kind!=="modern"||busy)return;
    setBusy(`modern-health:${selectedNode.id}`);setError("");
    try{await modernRequest(`/v1/settings/vpn/modern-protocols/${selectedNode.id}/health`,{method:"POST",body:JSON.stringify({})});setNotice(pick("Health Check انجام شد.","Health check completed."));await load(true);}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const modernRemove=async(row:UnifiedProtocol)=>{
    if(!selectedNode?.modern||row.kind!=="modern"||!row.modernRow?.installable||busy)return;
    if(!window.confirm(pick(`${row.name} از ${selectedNode.name} حذف شود؟`,`Remove ${row.name} from ${selectedNode.name}?`)))return;
    setBusy(`modern-remove:${selectedNode.id}:${row.protocol}`);setError("");
    try{await modernRequest(`/v1/settings/vpn/modern-protocols/${selectedNode.id}/${row.protocol}`,{method:"DELETE"});setNotice(pick(`${row.name} حذف شد.`,`${row.name} was removed.`));await load(true);setSelectedProtocol(null);setModernEditor(null);}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const previewModern=async()=>{
    if(!modernEditor||busy)return;setBusy("modern-preview");setError("");
    try{
      const result=await modernRequest<ModernPreview>(`/v1/settings/vpn/modern-protocols/${modernEditor.node.id}/preview`,{method:"POST",body:JSON.stringify({protocol:modernEditor.row.protocol,port:modernEditor.port,preset:modernEditor.preset,settings:modernEditor.settings})});
      setModernPreview(result);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const openDomain=async()=>{
    if(!selectedNode||busy)return;setBusy(`domain:${selectedNode.id}`);setError("");
    try{const result=await adminApi.xrayDomain(selectedNode.id);setDomainMeta(result);setDomainDraft(String(result.xray_domain||""));setDomainOpen(true);}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const saveDomain=async(prepare:boolean)=>{
    if(!selectedNode||busy)return;setBusy(prepare?"domain-prepare":"domain-save");setError("");
    try{
      const saved=await adminApi.saveXrayDomain(selectedNode.id,domainDraft.trim());setDomainMeta(saved);
      if(prepare&&domainDraft.trim()){const prepared=await adminApi.prepareXrayDomain(selectedNode.id,true);setDomainMeta(current=>({...current,...prepared}));setNotice(pick("دامنه ذخیره و TLS آماده شد.","Domain saved and TLS prepared."));}
      else setNotice(pick("دامنه Xray ذخیره شد.","Xray domain saved."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const quickAction=async(row:UnifiedProtocol)=>{
    if(row.kind==="classic"){if(row.installed)await classicHealth(row);else await ensureClassic(row);return;}
    if(!row.installable){openProtocol(row);return;}
    if(row.installed)await modernHealth(row);
    else{
      const definition=catalogMap.get(row.protocol);if(!definition||!row.modernRow||!selectedNode?.modern)return;
      await modernApply({node:selectedNode.modern,row:row.modernRow,definition,port:row.modernRow.port,preset:row.modernRow.preset||"recommended",settings:{...(row.modernRow.settings||{})},showAdvanced:false});
    }
  };

  const filterItems:Array<{key:FilterKey;fa:string;en:string}>=[
    {key:"all",fa:"همه",en:"All"},{key:"active",fa:"فعال",en:"Active"},{key:"classic",fa:"کلاسیک",en:"Classic"},{key:"modern",fa:"مدرن",en:"Modern"},{key:"planned",fa:"آزمایشی",en:"Planned"},
  ];

  return <Shell active="/admin/modern-protocols">
    <div className="page legacy-control-page">
      <PageHead title={pick("پروتکل‌ها","Protocols")} sub={pick("یک Command Center برای انتخاب سرور، نصب، Health، Repair، TLS و تنظیمات همه پروتکل‌ها","One command center for server selection, install, health, repair, TLS and every protocol setting")}/>

      <div className={styles.workspace}>
        <section className={styles.commandSurface}>
          <div className={styles.commandTop}>
            <div>
              <small>{pick("سرور فعال","Active server")}</small>
              <strong>{selectedNode?.name||pick("در حال بارگذاری…","Loading…")}</strong>
              <span dir="ltr">{selectedNode?.public_domain||selectedNode?.public_ip||"—"}</span>
            </div>
            <div className={styles.actionRow}>
              {selectedNode?.modern?<button type="button" className={styles.primaryButton} disabled={loading||!!busy} onClick={()=>void modernSyncAll()}>{busy===`modern-sync-all:${selectedNode.id}`?"…":pick("همگام‌سازی همه پروتکل‌های مدرن","Sync all modern protocols")}</button>:null}
              <button type="button" className={styles.refreshButton} disabled={loading||!!busy} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
            </div>
          </div>

          <div className={styles.nodeRail} aria-label={pick("انتخاب سرور","Select server")}>
            {nodes.map(node=><button key={node.id} type="button" className={`${styles.nodePill} ${node.id===selectedNodeId?styles.nodePillActive:""}`} onClick={()=>selectNode(node.id)}>
              <span className={`${styles.statusDot} ${String(node.status).toLowerCase()==="online"?styles.statusDotOnline:""}`}/>
              <span><b>{node.name}</b><small dir="ltr">{node.public_domain||node.public_ip||`#${node.id}`}</small></span>
            </button>)}
          </div>

          <div className={styles.metrics}>
            <div><span>{pick("فعال","Active")}</span><b>{metrics.active.toLocaleString("fa-IR")}</b><small>/ {metrics.total.toLocaleString("fa-IR")}</small></div>
            <div><span>{pick("سالم بعد از Health","Healthy")}</span><b>{metrics.healthy.toLocaleString("fa-IR")}</b></div>
            <div><span>{pick("در حال توسعه","Planned")}</span><b>{metrics.planned.toLocaleString("fa-IR")}</b></div>
            <div><span>{pick("وضعیت نود","Node")}</span><Badge tone={tone(selectedNode?.status||"")}>{selectedNode?.status||"—"}</Badge></div>
          </div>
        </section>

        {error?<div className={styles.errorBox}>{error}</div>:null}
        {notice?<div className={styles.successBox}>{notice}</div>:null}

        <section className={styles.librarySurface}>
          <div className={styles.libraryToolbar}>
            <label className={styles.searchBox}><span>⌕</span><input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("جستجوی پروتکل، Core یا Transport…","Search protocol, core or transport…")}/></label>
            <div className={styles.filterRail}>{filterItems.map(item=><button key={item.key} className={`${styles.filterButton} ${filter===item.key?styles.filterButtonActive:""}`} onClick={()=>setFilter(item.key)}>{pick(item.fa,item.en)}</button>)}</div>
          </div>

          <div className={styles.libraryHead}><div><strong>{pick("Protocol Library","Protocol Library")}</strong><small>{pick("کلاسیک و مدرن در یک نمای واحد؛ تنظیمات فقط وقتی لازم است باز می‌شوند.","Classic and modern in one view; settings open only when needed.")}</small></div><span>{filteredProtocols.length.toLocaleString("fa-IR")} {pick("پروتکل","protocols")}</span></div>

          <div className={styles.protocolGrid}>
            {filteredProtocols.map(row=>{
              const classicRun=row.kind==="classic"?classicRuntime[classicKey(selectedNodeId,row.protocol as ClassicProtocolKey)]:undefined;
              const visibleStatus=row.operatorDisabled?"admin_disabled":row.kind==="classic"&&classicChecked[classicKey(selectedNodeId,row.protocol as ClassicProtocolKey)]?(classicRun?.ok?"online":"check"):row.status;
              return <article key={row.id} className={`${styles.protocolCard} ${row.installed?styles.protocolCardActive:""}`}>
                <div className={styles.cardTop}>
                  <div className={styles.protocolIdentity}><span className={styles.protocolIcon}>{iconFor(row.protocol)}</span><div><strong>{row.name}</strong><small>{row.core} · {row.transport}</small></div></div>
                  <Badge tone={row.operatorDisabled?"warn":tone(visibleStatus)}>{row.operatorDisabled?pick("غیرفعال روی این نود","Disabled on this node"):visibleStatus==="not_installed"?pick("نصب نشده","Not installed"):visibleStatus}</Badge>
                </div>
                <div className={styles.metaLine}>
                  <span>{row.kind==="classic"?pick("Classic","Classic"):pick("Modern","Modern")}</span>
                  <span>{pick("Port","Port")} {row.portText}</span>
                  {row.recommended?<span className={styles.recommended}>{pick("پیشنهادی","Recommended")}</span>:null}
                  {!row.installable?<span className={styles.planned}>{pick("در حال توسعه","Planned")}</span>:null}
                </div>
                {row.error?<div className={styles.cardError}>{row.error}</div>:null}
                <div className={styles.cardFooter}>
                  <button className={styles.manageButton} onClick={()=>openProtocol(row)}>{pick("مدیریت","Manage")}</button>
                  <button className={styles.quickButton} disabled={!!busy||(row.kind==="modern"&&!row.installable)} onClick={()=>void quickAction(row)}>
                    {busy.includes(`${selectedNodeId}:${row.protocol}`)?"…":row.installed?"Health":row.installable?pick("نصب","Install"):pick("به‌زودی","Soon")}
                  </button>
                </div>
                {row.installed?<div className={styles.nodeActions}>
                  <button type="button" className={styles.secondaryButton} disabled={!!busy} onClick={()=>void restartOnNode(row)}>{pick("↻ ری‌استارت پروتکل","↻ Restart protocol")}</button>
                  <button type="button" className={row.operatorDisabled?styles.secondaryButton:styles.dangerButton} disabled={!!busy} onClick={()=>void toggleOnNode(row)}>{row.operatorDisabled?pick("فعال‌سازی روی نود","Enable on node"):pick("غیرفعال روی نود","Disable on node")}</button>
                </div>:null}
              </article>;
            })}
          </div>

          {!filteredProtocols.length&&!loading?<div className={styles.emptyState}>{pick("پروتکلی با این فیلتر پیدا نشد.","No protocol matches this filter.")}</div>:null}
        </section>
      </div>
    </div>

    {selectedRow&&selectedNode?<div className={styles.backdrop} onMouseDown={event=>{if(event.currentTarget===event.target){setSelectedProtocol(null);setModernEditor(null);setDomainOpen(false);}}}>
      <aside className={styles.drawer}>
        <div className={styles.drawerHead}>
          <div className={styles.drawerIdentity}><span className={styles.protocolIconLarge}>{iconFor(selectedRow.protocol)}</span><div><small>{selectedRow.kind==="classic"?"CLASSIC":"MODERN"}</small><h2>{selectedRow.name}</h2><p>{selectedNode.name} · {selectedRow.core} · {selectedRow.transport}</p></div></div>
          <button className={styles.closeButton} onClick={()=>{setSelectedProtocol(null);setModernEditor(null);setDomainOpen(false);}}>×</button>
        </div>

        {error?<div className={styles.errorBox}>{error}</div>:null}
        {notice?<div className={styles.successBox}>{notice}</div>:null}

        <div className={styles.drawerStatus}><div><span>{pick("وضعیت","Status")}</span><Badge tone={selectedRow.operatorDisabled?"warn":tone(selectedRow.status)}>{selectedRow.operatorDisabled?pick("غیرفعال روی این نود","Disabled on this node"):selectedRow.status}</Badge></div><div><span>{pick("نود","Node")}</span><b>{selectedNode.name}</b></div><div><span>{pick("Runtime","Runtime")}</span><b>{selectedRow.kind==="classic"?pick("Production","Production"):selectedRow.installable?pick("آماده","Ready"):pick("در حال توسعه","Planned")}</b></div></div>

        {selectedRow.installed?<section className={styles.drawerSection}>
          <div className={styles.sectionHead}><div><strong>{pick("کنترل همین نود","Controls for this node")}</strong><small>{pick("هر عمل فقط روی نود انتخاب‌شده اعمال می‌شود؛ تنظیمات سایر نودها تغییر نمی‌کند.","Actions target only this node; other nodes remain unchanged.")}</small></div></div>
          <div className={styles.actionRow}>
            <button type="button" className={styles.secondaryButton} disabled={!!busy} onClick={()=>void restartOnNode(selectedRow)}>{pick("↻ ری‌استارت پروتکل","↻ Restart protocol")}</button>
            <button type="button" className={selectedRow.operatorDisabled?styles.secondaryButton:styles.dangerButton} disabled={!!busy} onClick={()=>void toggleOnNode(selectedRow)}>{selectedRow.operatorDisabled?pick("فعال‌سازی پروتکل روی نود","Enable protocol on node"):pick("غیرفعال‌کردن پروتکل روی نود","Disable protocol on node")}</button>
          </div>
          <small className={styles.operatorHint}>{pick("غیرفعال‌کردن فقط نمایش کانفیگ‌های جدید را متوقف می‌کند؛ سرویس و اتصال‌های فعلی بدون تغییر می‌مانند.","Disabling hides new configs only; it does not stop the service or existing connections.")}</small>
        </section>:null}

        {selectedRow.kind==="classic"&&selectedRow.classicRow?(()=>{
          const protocol=selectedRow.protocol as ClassicProtocolKey;
          const def=CLASSIC_MAP.get(protocol)!;
          const key=classicKey(selectedNode.id,protocol);
          const draft=classicDrafts[key]||{port:Number(selectedRow.classicRow!.port||def.defaultPort||0),transport:selectedRow.classicRow!.transport==="tcp"?"tcp":"udp"};
          const run=classicRuntime[key];
          const checked=Boolean(classicChecked[key]);
          return <>
            <section className={styles.drawerSection}>
              <div className={styles.sectionHead}><div><strong>{pick("Listener","Listener")}</strong><small>{pick("تنظیمات اصلی سرویس","Primary service settings")}</small></div></div>
              {protocol==="l2tp"?<div className={styles.readonlyRow}><span>{pick("پورت‌های ثابت","Fixed ports")}</span><b dir="ltr">500 / 4500 / 1701 UDP</b></div>:<div className={styles.formGrid}><div className={styles.field}><label>{pick("پورت Listener","Listener port")}</label><input type="number" min={1} max={65535} value={draft.port} onChange={event=>setClassicDrafts(current=>({...current,[key]:{...draft,port:Number(event.target.value)}}))}/></div>{protocol==="openvpn"?<div className={styles.field}><label>Transport</label><select value={draft.transport} onChange={event=>setClassicDrafts(current=>({...current,[key]:{...draft,transport:event.target.value as "udp"|"tcp"}}))}><option value="udp">UDP</option><option value="tcp">TCP</option></select></div>:null}</div>}
              {protocol==="v2ray"?<div className={styles.warningBox}>{pick("تغییر پورت Xray مشکل صدور SSL را حل نمی‌کند؛ تأیید HTTP-01 به پورت عمومی 80 نیاز دارد.","Changing the Xray listener port does not fix SSL issuance; HTTP-01 requires public port 80.")}</div>:null}
              {portWarnings[key]?<div className={styles.warningBox}>{portWarnings[key]}</div>:null}
              {protocol!=="l2tp"?<button className={styles.secondaryButton} disabled={!!busy||!Number.isInteger(draft.port)||draft.port<1||draft.port>65535} onClick={()=>void checkClassicPort(selectedRow)}>{busy===`port-check:${key}`?"…":pick("بررسی تداخل پورت","Check port conflict")}</button>:null}
              {run?.error||selectedRow.error?<div className={styles.errorBox}>{run?.error||selectedRow.error}</div>:null}
              <div className={styles.actionRow}><button className={styles.primaryButton} disabled={!!busy} onClick={()=>void ensureClassic(selectedRow)}>{busy===`classic-ensure:${key}`?"…":selectedRow.installed?pick("اعمال / Repair","Apply / repair"):pick("نصب / فعال‌سازی","Install / enable")}</button>{selectedRow.installed?<button className={styles.secondaryButton} disabled={!!busy} onClick={()=>void classicHealth(selectedRow)}>{busy===`classic-health:${key}`?"…":"Health"}</button>:null}</div>
            </section>

            {protocol==="v2ray"&&selectedRow.installed?<section className={styles.drawerSection}>
              <div className={styles.sectionHead}><div><strong>{pick("Xray Domain & TLS","Xray Domain & TLS")}</strong><small>{pick("دامنه اختصاصی بدون تغییر دامنه عمومی نود","Dedicated domain without changing the node public domain")}</small></div><button className={styles.secondaryButton} onClick={()=>void openDomain()} disabled={!!busy}>{busy===`domain:${selectedNode.id}`?"…":domainOpen?pick("بارگذاری مجدد","Reload"):pick("باز کردن","Open")}</button></div>
              {domainOpen?<><div className={styles.formGrid}><div className={`${styles.field} ${styles.fieldWide}`}><label>{pick("دامنه Xray","Xray domain")}</label><input dir="ltr" value={domainDraft} onChange={event=>setDomainDraft(event.target.value)} placeholder="xray.example.com"/></div></div><div className={styles.tlsMeta}><span>{pick("Effective","Effective")}: <b dir="ltr">{domainMeta?.effective_xray_domain||"—"}</b></span><Badge tone={domainMeta?.tls_enabled?"ok":"warn"}>{domainMeta?.tls_enabled?"TLS READY":"TLS CHECK"}</Badge></div><div className={styles.actionRow}><button className={styles.secondaryButton} disabled={!!busy} onClick={()=>void saveDomain(false)}>{busy==="domain-save"?"…":pick("ذخیره","Save")}</button><button className={styles.primaryButton} disabled={!!busy||!domainDraft.trim()} onClick={()=>void saveDomain(true)}>{busy==="domain-prepare"?"…":pick("ذخیره و آماده‌سازی TLS","Save & prepare TLS")}</button></div></>:null}
            </section>:null}
            {protocol==="v2ray"&&selectedRow.installed?<XrayInboundEditorInProtocol nodeId={selectedNode.id}/>:null}
          </>;
        })():null}

        {selectedRow.kind==="modern"&&modernEditor?<>
          <section className={styles.drawerSection}>
            <div className={styles.sectionHead}><div><strong>{pick("Preset","Preset")}</strong><small>{pick("شروع سریع، بدون شلوغ کردن صفحه اصلی","Fast start without cluttering the main workspace")}</small></div></div>
            <div className={styles.presetGrid}>{Object.entries(PRESETS).map(([name,label])=><button key={name} className={`${styles.presetButton} ${modernEditor.preset===name?styles.presetButtonActive:""}`} onClick={()=>{setModernPreview(null);setModernEditor(current=>current?{...current,preset:name,settings:{}}:current);}}>{pick(label[0],label[1])}</button>)}</div>
          </section>

          <section className={styles.drawerSection}>
            <div className={styles.sectionHead}><div><strong>{pick("Listener و تنظیمات","Listener & settings")}</strong><small>{modernEditor.definition.core} · {modernEditor.definition.transport.toUpperCase()}</small></div></div>
            <div className={styles.formGrid}><div className={styles.field}><label>{pick("پورت","Port")}</label><input type="number" min={1} max={65535} value={modernEditor.port} onChange={event=>setModernEditor(current=>current?{...current,port:Number(event.target.value)}:current)}/></div>{modernEditor.definition.fields.filter(field=>!field.advanced).map(field=><FieldControl key={field.key} editor={modernEditor} field={field} pick={pick} onChange={value=>{setModernPreview(null);setModernEditor(current=>current?{...current,preset:"custom",settings:{...current.settings,[field.key]:value}}:current);}}/>)}</div>
            {modernEditor.definition.fields.some(field=>field.advanced)?<><button className={styles.advancedToggle} onClick={()=>setModernEditor(current=>current?{...current,showAdvanced:!current.showAdvanced}:current)}>{modernEditor.showAdvanced?pick("− بستن تنظیمات پیشرفته","− Hide advanced settings"):pick("+ تنظیمات پیشرفته","+ Advanced settings")}</button>{modernEditor.showAdvanced?<div className={styles.formGrid}>{modernEditor.definition.fields.filter(field=>field.advanced).map(field=><FieldControl key={field.key} editor={modernEditor} field={field} pick={pick} onChange={value=>{setModernPreview(null);setModernEditor(current=>current?{...current,preset:"custom",settings:{...current.settings,[field.key]:value}}:current);}}/>)}</div>:null}</>:null}
          </section>

          <section className={styles.drawerSection}>
            <div className={styles.compatibilityLine}>{modernEditor.definition.platforms.map(platform=><span key={platform}>{platform}</span>)}{Object.entries(modernEditor.definition.formats).filter(([,enabled])=>enabled).map(([format])=><span key={format}>{format.replace("_","-")}</span>)}</div>
            {(modernPreview?.warnings||modernEditor.row.warnings||[]).map(code=><div className={styles.warningBox} key={code}>{pick(...(WARNING_LABELS[code]||[code,code]))}</div>)}
            {!modernEditor.definition.installable?<div className={styles.warningBox}>{pick("Schema و Preset آماده است، اما Adapter رسمی هنوز Production-Ready نیست و نصب عمداً غیرفعال است.","Schema and presets are ready, but the official adapter is not production-ready, so installation is intentionally disabled.")}</div>:null}
            {modernPreview?<div className={styles.previewBox}><strong>{pick("Preview امن قبل از Apply","Safe preview before apply")}</strong><pre>{JSON.stringify(modernPreview.preview,null,2)}</pre></div>:null}
          </section>

          <div className={styles.drawerFooter}><button className={styles.secondaryButton} disabled={!!busy} onClick={()=>void previewModern()}>{busy==="modern-preview"?"…":pick("Preview / اعتبارسنجی","Preview / validate")}</button><button className={styles.primaryButton} disabled={!!busy||!modernEditor.definition.installable} onClick={()=>void modernApply(modernEditor)}>{pick("اعمال تنظیمات","Apply settings")}</button>{selectedRow.installed&&modernEditor.definition.installable?<button className={styles.dangerButton} disabled={!!busy} onClick={()=>void modernRemove(selectedRow)}>{pick("حذف Runtime","Remove runtime")}</button>:null}</div>
        </>:null}
      </aside>
    </div>:null}
  </Shell>;
}