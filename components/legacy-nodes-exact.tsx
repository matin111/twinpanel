"use client";

import {useEffect,useMemo,useState} from "react";

import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,type AdminNode,type RuntimeRow} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"").trim();
const n=(value:unknown)=>{const parsed=Number(value??0);return Number.isFinite(parsed)?parsed:0;};
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const state=s(value).toLowerCase();
  if(["active","online","ok","healthy","configured"].includes(state))return "ok";
  if(["inactive","offline","failed","error","expired","canceled"].includes(state))return "bad";
  if(state==="maintenance")return "violet";
  return "warn";
};

const protocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"] as const;
const protocolLabels:Record<(typeof protocolKeys)[number],string>={
  cisco:"Cisco / OpenConnect",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP / IPsec",
  v2ray:"V2Ray / Xray",
};

type NodeRole="iran"|"exit"|"mother";
type NodeModal="ssh"|"domain"|"protocols"|null;
type ExtendedNode=AdminNode&{is_mother?:boolean;public_domain?:string|null};
type ProtocolRuntime={
  protocol?:string;
  name?:string;
  installed?:boolean;
  ok?:boolean;
  service?:string;
  listeners?:Record<string,boolean>;
  port_text?:string;
  error?:string|null;
  modern_ready?:boolean;
  modern_health?:{ok?:boolean;tls_enabled?:boolean;tls_domain_configured?:boolean;error?:string|null};
};

function roleOf(node:ExtendedNode):NodeRole{
  if(node.is_mother||node.node_type==="mother"||node.node_type==="core")return "mother";
  return node.node_type==="iran"?"iran":"exit";
}

function enabledProtocols(node:ExtendedNode){
  return protocolKeys.filter(key=>Boolean(node[`enable_${key}` as keyof ExtendedNode]));
}

function Modal({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}){
  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className="runtime-modal-card">
      <div className="card-head"><b>{title}</b><button type="button" className="icon-button" onClick={onClose}>×</button></div>
      {children}
    </div>
  </div>;
}

export function LegacyNodesRuntimePage(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<ExtendedNode[]>([]);
  const [domains,setDomains]=useState<RuntimeRow[]>([]);
  const [selectedId,setSelectedId]=useState(0);
  const [filter,setFilter]=useState<"all"|"iran"|"exit">("all");
  const [query,setQuery]=useState("");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");
  const [warning,setWarning]=useState("");
  const [modal,setModal]=useState<NodeModal>(null);
  const [accessConfigured,setAccessConfigured]=useState(false);
  const [accessDraft,setAccessDraft]=useState({port:22,username:"root",password:""});
  const [domainDraft,setDomainDraft]=useState("");
  const [runtime,setRuntime]=useState<Record<string,ProtocolRuntime>>({});

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    if(!silent)setError("");
    try{
      const ns=await adminApi.nodes() as ExtendedNode[];
      setNodes(ns);
      setSelectedId(current=>current&&ns.some(row=>row.id===current)?current:(ns[0]?.id||0));
      try{
        const ds=await legacyAdminApi.nodeDomains();
        setDomains(Array.isArray(ds.nodes)?ds.nodes:[]);
      }catch{
        setDomains([]);
      }
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setLoading(false);}
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(true),15000);return()=>window.clearInterval(timer);},[]);

  const selected=nodes.find(row=>row.id===selectedId)||null;
  const selectedRole=selected?roleOf(selected):null;
  const selectedDomain=selected?domains.find(row=>n(row.id||row.node_id)===selected.id):null;
  const effectiveDomain=s(selected?.public_domain||selectedDomain?.public_domain||selectedDomain?.domain);
  const selectedProtocols=selected?enabledProtocols(selected):[];

  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return nodes.filter(node=>{
      const role=roleOf(node);
      if(filter!=="all"&&role!==filter)return false;
      if(!q)return true;
      return `${node.id} ${node.name} ${node.public_ip||""} ${node.country_code||""} ${role}`.toLowerCase().includes(q);
    });
  },[nodes,filter,query]);

  const onlineCount=nodes.filter(node=>s(node.status).toLowerCase()==="online").length;
  const iranCount=nodes.filter(node=>roleOf(node)==="iran").length;
  const exitCount=nodes.filter(node=>roleOf(node)==="exit").length;

  useEffect(()=>{
    if(!selected){setAccessConfigured(false);setRuntime({});return;}
    let active=true;
    legacyAdminApi.nodeAccess(selected.id).then(result=>{
      if(!active)return;
      setAccessConfigured(Boolean(result.configured));
      setAccessDraft({port:n(result.port)||22,username:s(result.username)||"root",password:""});
    }).catch(()=>{
      if(active){setAccessConfigured(false);setAccessDraft({port:22,username:"root",password:""});}
    });
    setDomainDraft(effectiveDomain);
    setRuntime({});
    setError("");setWarning("");setSuccess("");
    return()=>{active=false;};
  },[selectedId,effectiveDomain]);

  const ensureAccess=()=>{
    if(accessConfigured)return true;
    setWarning(pick("برای این عملیات ابتدا دسترسی SSH نود را ثبت کنید.","Register SSH access before this operation."));
    setModal("ssh");
    return false;
  };

  const saveAccess=async()=>{
    if(!selected||busy)return;
    if(!accessDraft.password){setError(pick("رمز SSH را وارد کنید.","Enter the SSH password."));return;}
    setBusy("ssh");setError("");setWarning("");
    try{
      await legacyAdminApi.saveNodeAccess({node_id:selected.id,host:selected.public_ip||effectiveDomain,port:accessDraft.port,username:accessDraft.username,password:accessDraft.password});
      setAccessConfigured(true);setModal(null);setAccessDraft(current=>({...current,password:""}));
      setSuccess(pick("دسترسی SSH ذخیره شد.","SSH access saved."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const saveDomain=async()=>{
    if(!selected||busy)return;
    setBusy("domain");setError("");setWarning("");
    try{
      const result=await legacyAdminApi.updateNodeDomain(selected.id,domainDraft.trim());
      const value=s(result.public_domain||domainDraft.trim());
      const next:RuntimeRow={id:selected.id,node_id:selected.id,public_domain:value,domain:value};
      setDomains(current=>current.some(row=>n(row.id||row.node_id)===selected.id)
        ?current.map(row=>n(row.id||row.node_id)===selected.id?{...row,...next}:row)
        :[...current,next]);
      setModal(null);setSuccess(pick("دامنه ذخیره شد.","Domain saved."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const checkProtocols=async()=>{
    if(!selected||busy||selectedRole!=="exit"||!ensureAccess())return;
    setBusy("health");setError("");setWarning("");setSuccess("");
    try{
      const result=await legacyAdminApi.protocolHealth(selected.id);
      const map=result&&typeof result.protocols==="object"&&result.protocols?result.protocols as Record<string,ProtocolRuntime>:{};
      setRuntime(map);setModal("protocols");
      setSuccess(Boolean(result.ok)?pick("سلامت پروتکل‌ها تایید شد.","Protocol health verified."):pick("برخی پروتکل‌ها نیاز به بررسی دارند.","Some protocols need attention."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const restartProtocol=async(key:string)=>{
    if(!selected||busy||!ensureAccess())return;
    setBusy(`restart-${key}`);setError("");setWarning("");
    try{
      const result=await legacyAdminApi.restartProtocol(selected.id,key);
      const protocol=result&&typeof result.protocol==="object"&&result.protocol?result.protocol as ProtocolRuntime:runtime[key];
      setRuntime(current=>({...current,[key]:protocol||{}}));
      setSuccess(`${protocolLabels[key as keyof typeof protocolLabels]} ${pick("ریستارت شد.","restarted.")}`);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const toggleMaintenance=async()=>{
    if(!selected||busy||selectedRole==="mother")return;
    setBusy("maintenance");setError("");
    try{
      const updated=await adminApi.toggleNodeMaintenance(selected.id);
      setNodes(current=>current.map(row=>row.id===updated.id?{...row,...updated}:row));
      setSuccess(updated.status==="maintenance"?pick("حالت نگهداری فعال شد.","Maintenance enabled."):pick("حالت نگهداری غیرفعال شد.","Maintenance disabled."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const deleteNode=async()=>{
    if(!selected||busy)return;
    if(!window.confirm(pick(`نود «${selected.name}» حذف شود؟`,`Delete node ${selected.name}?`)))return;
    setBusy("delete");setError("");
    try{
      await adminApi.deleteNode(selected.id);
      setSuccess(pick("نود حذف شد.","Node deleted."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/nodes">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div><h1>{pick("نودها","Nodes")}</h1><small>{pick("فقط کنترل‌های عملیاتی و قابل استفاده نمایش داده می‌شوند.","Only functional operational controls are shown.")}</small></div>
        <button type="button" className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
      </div>

      {error&&<div className="runtime-error">{error}</div>}
      {warning&&<div className="runtime-warning">{warning}</div>}
      {success&&<div className="runtime-success">{success}</div>}

      <div className="stats dashboard-stats">
        <Stat label={pick("کل نودها","Total nodes")} value={nodes.length.toLocaleString("fa-IR")} icon="◉"/>
        <Stat label={pick("آنلاین","Online")} value={onlineCount.toLocaleString("fa-IR")} icon="✓"/>
        <Stat label={pick("ایران","Iran")} value={iranCount.toLocaleString("fa-IR")} icon="IR"/>
        <Stat label={pick("خارج","Exit")} value={exitCount.toLocaleString("fa-IR")} icon="↗"/>
      </div>

      <Card>
        <div className="runtime-toolbar">
          <label>⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("نام، IP یا شناسه...","Name, IP or ID...")}/></label>
          <select value={filter} onChange={event=>setFilter(event.target.value as "all"|"iran"|"exit")}>
            <option value="all">{pick("همه","All")}</option><option value="iran">{pick("ایران","Iran")}</option><option value="exit">{pick("خارج","Exit")}</option>
          </select>
        </div>
        <div className="table"><table><thead><tr><th>{pick("نود","Node")}</th><th>{pick("نوع","Type")}</th><th>IP</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead>
          <tbody>{filtered.map(node=><tr key={node.id} className={node.id===selectedId?"is-selected":""}>
            <td><b>{node.name}</b></td><td>{roleOf(node)}</td><td dir="ltr">{node.public_ip||"—"}</td><td><Badge tone={tone(node.status)}>{node.status||"—"}</Badge></td>
            <td><button type="button" className={node.id===selectedId?"primary-soft":"ghost"} onClick={()=>setSelectedId(node.id)}>{pick("مدیریت","Manage")}</button></td>
          </tr>)}</tbody>
        </table></div>
      </Card>

      {selected&&<Card>
        <div className="card-head"><div><b>{selected.name}</b><small dir="ltr">{selected.public_ip||"—"}</small></div><Badge tone={tone(selected.status)}>{selected.status||"—"}</Badge></div>
        <div className="runtime-info-list">
          <div><span>{pick("نقش","Role")}</span><b>{selectedRole}</b></div>
          <div><span>{pick("دسترسی SSH","SSH access")}</span><Badge tone={accessConfigured?"ok":"warn"}>{accessConfigured?pick("ثبت شده","Saved"):pick("ثبت نشده","Missing")}</Badge></div>
          <div><span>{pick("دامنه","Domain")}</span><b dir="ltr">{effectiveDomain||"—"}</b></div>
          <div><span>{pick("پروتکل‌های فعال","Enabled protocols")}</span><b>{selectedProtocols.length.toLocaleString("fa-IR")}</b></div>
        </div>
        <div className="action-row">
          <button type="button" className="primary-soft" onClick={()=>{setError("");setAccessDraft(current=>({...current,password:""}));setModal("ssh");}}>{pick("دسترسی SSH","SSH access")}</button>
          <button type="button" className="primary-soft" onClick={()=>{setDomainDraft(effectiveDomain);setModal("domain");}}>{pick("دامنه","Domain")}</button>
          {selectedRole==="exit"?<button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void checkProtocols()}>{busy==="health"?"…":pick("بررسی پروتکل‌ها","Check protocols")}</button>:null}
          {selectedRole!=="mother"?<button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void toggleMaintenance()}>{selected.status==="maintenance"?pick("خروج از نگهداری","Leave maintenance"):pick("حالت نگهداری","Maintenance")}</button>:null}
          <button type="button" className="danger" disabled={Boolean(busy)} onClick={()=>void deleteNode()}>{pick("حذف نود","Delete node")}</button>
        </div>
      </Card>}

      {modal==="ssh"&&selected?<Modal title={pick("دسترسی SSH","SSH access")} onClose={()=>setModal(null)}>
        <div className="runtime-form">
          <label>{pick("پورت","Port")}<input type="number" value={accessDraft.port} onChange={event=>setAccessDraft(current=>({...current,port:Number(event.target.value)||22}))}/></label>
          <label>{pick("نام کاربری","Username")}<input value={accessDraft.username} onChange={event=>setAccessDraft(current=>({...current,username:event.target.value}))}/></label>
          <label>{pick("رمز عبور","Password")}<input type="password" value={accessDraft.password} onChange={event=>setAccessDraft(current=>({...current,password:event.target.value}))}/></label>
          <button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void saveAccess()}>{busy==="ssh"?"…":pick("ذخیره","Save")}</button>
        </div>
      </Modal>:null}

      {modal==="domain"&&selected?<Modal title={pick("دامنه نود","Node domain")} onClose={()=>setModal(null)}>
        <div className="runtime-form"><label>{pick("دامنه","Domain")}<input dir="ltr" value={domainDraft} onChange={event=>setDomainDraft(event.target.value)} placeholder="node.example.com"/></label><button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void saveDomain()}>{busy==="domain"?"…":pick("ذخیره","Save")}</button></div>
      </Modal>:null}

      {modal==="protocols"&&selected?<Modal title={pick("سلامت پروتکل‌ها","Protocol health")} onClose={()=>setModal(null)}>
        <div className="tunnel-service-compact-grid">{selectedProtocols.map(key=>{const row=runtime[key]||{};const ok=Boolean(row.ok);return <div className="tunnel-service-compact-item" key={key}>
          <div className="tunnel-service-compact-item-head"><b>{protocolLabels[key]}</b><Badge tone={ok?"ok":"warn"}>{ok?"ONLINE":"CHECK"}</Badge></div>
          {row.error?<small dir="ltr">{row.error}</small>:null}
          {key==="v2ray"&&row.modern_health?<div className="runtime-info-list"><div><span>TLS</span><b>{row.modern_health.tls_enabled?"ON":"OFF"}</b></div><div><span>Domain</span><b>{row.modern_health.tls_domain_configured?"OK":"—"}</b></div></div>:null}
          {!ok?<button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>void restartProtocol(key)}>{busy===`restart-${key}`?"…":pick("ریستارت سرویس","Restart service")}</button>:null}
        </div>;})}</div>
      </Modal>:null}
    </div>
  </Shell>;
}
