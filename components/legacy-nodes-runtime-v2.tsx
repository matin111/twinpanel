"use client";

import {useEffect,useMemo,useState} from "react";

import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,type AdminNode,type RuntimeRow,type XrayDomainState} from "../lib/admin-api";
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
type NodeRole="iran"|"exit"|"mother";
type NodeModal="manage"|"ssh"|"domain"|"xray-domain"|null;
type ExtendedNode=AdminNode&{is_mother?:boolean;public_domain?:string|null};

function roleOf(node:ExtendedNode):NodeRole{
  if(node.is_mother||node.node_type==="mother"||node.node_type==="core")return "mother";
  return node.node_type==="iran"?"iran":"exit";
}

function enabledProtocolCount(node:ExtendedNode){
  return protocolKeys.filter(key=>Boolean(node[`enable_${key}` as keyof ExtendedNode])).length;
}

function Modal({title,sub,onClose,children,className=""}:{title:string;sub?:string;onClose:()=>void;children:React.ReactNode;className?:string}){
  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className={`runtime-modal-card ${className}`.trim()}>
      <div className="card-head"><div><b>{title}</b>{sub?<small dir="ltr">{sub}</small>:null}</div><button type="button" className="icon-button" onClick={onClose}>×</button></div>
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
  const [accessLoading,setAccessLoading]=useState(false);
  const [accessDraft,setAccessDraft]=useState({port:22,username:"root",password:""});
  const [domainDraft,setDomainDraft]=useState("");
  const [xrayDomainDraft,setXrayDomainDraft]=useState("");
  const [xrayDomainMeta,setXrayDomainMeta]=useState<XrayDomainState|null>(null);
  const [xrayDomainLoading,setXrayDomainLoading]=useState(false);

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    if(!silent)setError("");
    try{
      const ns=await adminApi.nodes() as ExtendedNode[];
      setNodes(ns);
      setSelectedId(current=>current&&ns.some(row=>row.id===current)?current:0);
      try{
        const ds=await legacyAdminApi.nodeDomains();
        setDomains(Array.isArray(ds.nodes)?ds.nodes:[]);
      }catch{
        setDomains([]);
      }
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      if(!silent)setLoading(false);
    }
  };

  useEffect(()=>{
    void load();
    const timer=window.setInterval(()=>void load(true),15000);
    return()=>window.clearInterval(timer);
  },[]);

  const selected=nodes.find(row=>row.id===selectedId)||null;
  const selectedRole=selected?roleOf(selected):null;
  const selectedDomain=selected?domains.find(row=>n(row.id||row.node_id)===selected.id):null;
  const effectiveDomain=s(selected?.public_domain||selectedDomain?.public_domain||selectedDomain?.domain);
  const storedXrayDomain=s(xrayDomainMeta?.xray_domain);
  const effectiveXrayDomain=s(xrayDomainMeta?.effective_xray_domain);
  const displayedXrayDomain=storedXrayDomain||effectiveXrayDomain;

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
    if(!selected){
      setAccessConfigured(false);
      setAccessLoading(false);
      setDomainDraft("");
      return;
    }
    let active=true;
    setAccessLoading(true);
    legacyAdminApi.nodeAccess(selected.id).then(result=>{
      if(!active)return;
      setAccessConfigured(Boolean(result.configured));
      setAccessDraft({port:n(result.port)||22,username:s(result.username)||"root",password:""});
    }).catch(()=>{
      if(active){
        setAccessConfigured(false);
        setAccessDraft({port:22,username:"root",password:""});
      }
    }).finally(()=>{if(active)setAccessLoading(false);});

    setDomainDraft(effectiveDomain);
    setError("");setWarning("");setSuccess("");
    return()=>{active=false;};
  },[selectedId,effectiveDomain]);

  useEffect(()=>{
    if(!selected||selectedRole!=="exit"){
      setXrayDomainMeta(null);
      setXrayDomainDraft("");
      setXrayDomainLoading(false);
      return;
    }
    let active=true;
    setXrayDomainLoading(true);
    adminApi.xrayDomain(selected.id).then(result=>{
      if(!active)return;
      setXrayDomainMeta(result);
      setXrayDomainDraft(s(result.xray_domain||result.effective_xray_domain));
    }).catch(reason=>{
      if(!active)return;
      setXrayDomainMeta(null);
      setWarning(reason instanceof Error?reason.message:String(reason));
    }).finally(()=>{if(active)setXrayDomainLoading(false);});
    return()=>{active=false;};
  },[selectedId,selectedRole]);

  const openManage=(id:number)=>{
    setSelectedId(id);
    setError("");setWarning("");setSuccess("");
    setModal("manage");
  };

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
      await legacyAdminApi.saveNodeAccess({
        node_id:selected.id,
        host:selected.public_ip||effectiveDomain,
        port:accessDraft.port,
        username:accessDraft.username,
        password:accessDraft.password,
      });
      setAccessConfigured(true);
      setModal("manage");
      setAccessDraft(current=>({...current,password:""}));
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
      setModal("manage");
      setSuccess(pick("دامنه عمومی نود ذخیره شد.","Node public domain saved."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const saveXrayDomain=async()=>{
    if(!selected||selectedRole!=="exit"||busy)return;
    setBusy("xray-domain");setError("");setWarning("");setSuccess("");
    try{
      const result=await adminApi.saveXrayDomain(selected.id,xrayDomainDraft.trim());
      setXrayDomainMeta(result);
      setXrayDomainDraft(s(result.xray_domain||result.effective_xray_domain));
      setModal("manage");
      setSuccess(pick("دامنه اختصاصی Xray / V2Ray ذخیره شد.","Dedicated Xray / V2Ray domain saved."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const prepareXrayDomain=async()=>{
    if(!selected||selectedRole!=="exit"||busy)return;
    setBusy("xray-prepare");setError("");setWarning("");setSuccess("");
    let saved:XrayDomainState|null=null;
    try{
      saved=await adminApi.saveXrayDomain(selected.id,xrayDomainDraft.trim());
      setXrayDomainMeta(saved);
      setXrayDomainDraft(s(saved.xray_domain||saved.effective_xray_domain));
      const prepared=await adminApi.prepareXrayDomain(selected.id,true);
      setXrayDomainMeta({...saved,...prepared});
      setXrayDomainDraft(s(prepared.xray_domain||prepared.effective_xray_domain||saved.xray_domain||saved.effective_xray_domain));
      setModal("manage");
      setSuccess(s(prepared.message)||pick("دامنه، TLS و پروفایل‌های Xray آماده شدند.","Xray domain, TLS and profiles are ready."));
    }catch(reason){
      if(saved){
        setWarning(pick("دامنه ذخیره شد، اما آماده‌سازی TLS کامل نشد. خطای زیر را بررسی کنید.","The domain was saved, but TLS preparation did not complete. Review the error below."));
      }
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{setBusy("");}
  };

  const upgradeAgent=async()=>{
    if(!selected||busy||selectedRole==="mother"||accessLoading||!ensureAccess())return;
    setBusy("agent");setError("");setWarning("");setSuccess("");
    try{
      const result=await legacyAdminApi.upgradeAgent(selected.id);
      const message=s(result.message);
      setSuccess(message||pick("Node Agent به‌روزرسانی شد.","Node Agent updated."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const toggleMaintenance=async()=>{
    if(!selected||busy||selectedRole==="mother")return;
    setBusy("maintenance");setError("");
    try{
      const updated=await adminApi.toggleNodeMaintenance(selected.id);
      setNodes(current=>current.map(row=>row.id===updated.id?{...row,...updated}:row));
      setSuccess(updated.status==="maintenance"
        ?pick("حالت نگهداری فعال شد.","Maintenance enabled.")
        :pick("حالت نگهداری غیرفعال شد.","Maintenance disabled."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const deleteNode=async()=>{
    if(!selected||busy)return;
    if(!window.confirm(pick(`نود «${selected.name}» حذف شود؟`,`Delete node ${selected.name}?`)))return;
    setBusy("delete");setError("");
    try{
      await adminApi.deleteNode(selected.id);
      setModal(null);setSelectedId(0);
      setSuccess(pick("نود حذف شد.","Node deleted."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/nodes">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div>
          <h1>{pick("نودها","Nodes")}</h1>
          <small>{pick("مدیریت نود، SSH، دامنه عمومی، دامنه اختصاصی Xray و Agent. نصب و تنظیم پروتکل‌ها از صفحه پروتکل‌ها انجام می‌شود.","Manage nodes, SSH, public domains, dedicated Xray domains and agents. Protocol install/configuration remains in Protocols.")}</small>
        </div>
        <div className="action-row">
          <a href="/admin/provision" className="primary">＋ {pick("افزودن سرور","Add server")}</a>
          <a href="/admin/modern-protocols" className="primary-soft">{pick("پروتکل‌ها","Protocols")}</a>
          <button type="button" className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
        </div>
      </div>

      {error&&modal===null?<div className="runtime-error">{error}</div>:null}
      {warning&&modal===null?<div className="runtime-warning">{warning}</div>:null}
      {success&&modal===null?<div className="runtime-success">{success}</div>:null}

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
            <option value="all">{pick("همه","All")}</option>
            <option value="iran">{pick("ایران","Iran")}</option>
            <option value="exit">{pick("خارج","Exit")}</option>
          </select>
        </div>
        <div className="table"><table><thead><tr><th>{pick("نود","Node")}</th><th>{pick("نوع","Type")}</th><th>IP</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead>
          <tbody>{filtered.map(node=><tr key={node.id} className={node.id===selectedId&&modal!==null?"is-selected":""}>
            <td><b>{node.name}</b></td>
            <td>{roleOf(node)}</td>
            <td dir="ltr">{node.public_ip||"—"}</td>
            <td><Badge tone={tone(node.status)}>{node.status||"—"}</Badge></td>
            <td><button type="button" className="primary-soft" onClick={()=>openManage(node.id)}>{pick("مدیریت","Manage")}</button></td>
          </tr>)}</tbody>
        </table></div>
      </Card>

      {modal==="manage"&&selected?<Modal title={selected.name} sub={selected.public_ip||"—"} className="manage-card node-manage-modal-card" onClose={()=>setModal(null)}>
        <div className="node-manage-hero">
          <div><small>{pick("مدیریت نود","Node management")}</small><b>{pick("کنترل‌های زیرساخت نود","Node infrastructure controls")}</b></div>
          <Badge tone={tone(selected.status)}>{selected.status||"—"}</Badge>
        </div>
        {error?<div className="runtime-error">{error}</div>:null}
        {warning?<div className="runtime-warning">{warning}</div>:null}
        {success?<div className="runtime-success">{success}</div>:null}
        <div className="runtime-info-list node-manage-info">
          <div><span>{pick("نقش","Role")}</span><b>{selectedRole}</b></div>
          <div><span>{pick("دسترسی SSH","SSH access")}</span><Badge tone={accessConfigured?"ok":"warn"}>{accessLoading?"…":accessConfigured?pick("ثبت شده","Saved"):pick("ثبت نشده","Missing")}</Badge></div>
          <div><span>{pick("دامنه عمومی","Public domain")}</span><b dir="ltr">{effectiveDomain||"—"}</b></div>
          {selectedRole==="exit"?<div><span>{pick("دامنه Xray / V2Ray","Xray / V2Ray domain")}</span><b dir="ltr">{xrayDomainLoading?"…":displayedXrayDomain||"—"}{xrayDomainMeta?.legacy_public_domain_fallback?` · ${pick("fallback عمومی","public fallback")}`:""}</b></div>:null}
          <div><span>{pick("پروتکل‌های کلاسیک فعال","Enabled classic protocols")}</span><b>{enabledProtocolCount(selected).toLocaleString("fa-IR")}</b></div>
        </div>
        <div className="runtime-warning">
          {pick("Health، Repair، Port و تنظیمات حرفه‌ای پروتکل‌ها از مرکز «پروتکل‌ها» مدیریت می‌شود. هویت دامنه Xray / V2Ray متعلق به خود Exit Server است و از همین بخش مدیریت می‌شود.","Protocol health, repair, ports and advanced settings remain in Protocols. Xray / V2Ray domain identity belongs to the Exit server and is managed here.")}
        </div>
        <div className="action-row node-manage-actions">
          <a className="primary" href={`/admin/modern-protocols?node=${selected.id}`}>{pick("مدیریت پروتکل‌ها","Manage protocols")}</a>
          <button type="button" className="primary-soft" onClick={()=>{setError("");setAccessDraft(current=>({...current,password:""}));setModal("ssh");}}>{pick("دسترسی SSH","SSH access")}</button>
          {selectedRole!=="mother"?<button type="button" className="primary-soft" disabled={Boolean(busy)||accessLoading} onClick={()=>void upgradeAgent()}>{busy==="agent"?"…":pick("به‌روزرسانی Agent","Update Agent")}</button>:null}
          <button type="button" className="primary-soft" onClick={()=>{setDomainDraft(effectiveDomain);setModal("domain");}}>{pick("دامنه عمومی","Public domain")}</button>
          {selectedRole==="exit"?<button type="button" className="primary-soft" disabled={xrayDomainLoading} onClick={()=>{setError("");setWarning("");setSuccess("");setXrayDomainDraft(storedXrayDomain||effectiveXrayDomain);setModal("xray-domain");}}>{xrayDomainLoading?"…":pick("دامنه Xray / V2Ray","Xray / V2Ray domain")}</button>:null}
          {selectedRole!=="mother"?<button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void toggleMaintenance()}>{selected.status==="maintenance"?pick("خروج از نگهداری","Leave maintenance"):pick("حالت نگهداری","Maintenance")}</button>:null}
          <button type="button" className="danger" disabled={Boolean(busy)} onClick={()=>void deleteNode()}>{pick("حذف نود","Delete node")}</button>
        </div>
      </Modal>:null}

      {modal==="ssh"&&selected?<Modal title={pick("دسترسی SSH","SSH access")} sub={selected.name} onClose={()=>setModal("manage")}>
        {error?<div className="runtime-error">{error}</div>:null}
        <div className="runtime-form">
          <label>{pick("پورت","Port")}<input type="number" value={accessDraft.port} onChange={event=>setAccessDraft(current=>({...current,port:Number(event.target.value)||22}))}/></label>
          <label>{pick("نام کاربری","Username")}<input value={accessDraft.username} onChange={event=>setAccessDraft(current=>({...current,username:event.target.value}))}/></label>
          <label>{pick("رمز عبور","Password")}<input type="password" value={accessDraft.password} onChange={event=>setAccessDraft(current=>({...current,password:event.target.value}))}/></label>
          <button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void saveAccess()}>{busy==="ssh"?"…":pick("ذخیره","Save")}</button>
        </div>
      </Modal>:null}

      {modal==="domain"&&selected?<Modal title={pick("دامنه عمومی نود","Node public domain")} sub={selected.name} onClose={()=>setModal("manage")}>
        {error?<div className="runtime-error">{error}</div>:null}
        <div className="runtime-form">
          <label>{pick("دامنه عمومی","Public domain")}<input dir="ltr" value={domainDraft} onChange={event=>setDomainDraft(event.target.value)} placeholder="node.example.com"/></label>
          <small>{pick("دامنه عمومی برای هویت کلی نود است. دامنه اختصاصی TLS مربوط به Xray / V2Ray از مدیریت همین Exit Server جداگانه تنظیم می‌شود.","The public domain is the node's general identity. Xray / V2Ray TLS domain is configured separately from this Exit server's management.")}</small>
          <button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void saveDomain()}>{busy==="domain"?"…":pick("ذخیره","Save")}</button>
        </div>
      </Modal>:null}

      {modal==="xray-domain"&&selected&&selectedRole==="exit"?<Modal title={pick("دامنه Xray / V2Ray","Xray / V2Ray domain")} sub={`${selected.name} · ${selected.public_ip||"—"}`} onClose={()=>setModal("manage")}>
        {error?<div className="runtime-error">{error}</div>:null}
        {warning?<div className="runtime-warning">{warning}</div>:null}
        {success?<div className="runtime-success">{success}</div>:null}
        <div className="runtime-form">
          <label>{pick("دامنه اختصاصی Xray / V2Ray","Dedicated Xray / V2Ray domain")}<input dir="ltr" value={xrayDomainDraft} onChange={event=>setXrayDomainDraft(event.target.value)} placeholder="xray.example.com"/></label>
          <small>{pick("دامنه را بدون http/https وارد کنید. برای آماده‌سازی TLS باید A Record دامنه به IP همین Exit Server اشاره کند.","Enter the hostname without http/https. TLS preparation requires the domain A record to resolve to this Exit server IP.")}</small>
          <div className="runtime-info-list">
            <div><span>{pick("IP مورد انتظار","Expected IP")}</span><b dir="ltr">{selected.public_ip||"—"}</b></div>
            <div><span>{pick("دامنه مؤثر فعلی","Current effective domain")}</span><b dir="ltr">{effectiveXrayDomain||"—"}</b></div>
            <div><span>{pick("منبع دامنه","Domain source")}</span><Badge tone={xrayDomainMeta?.legacy_public_domain_fallback?"warn":"ok"}>{xrayDomainMeta?.legacy_public_domain_fallback?pick("Fallback دامنه عمومی","Public-domain fallback"):storedXrayDomain?pick("اختصاصی Xray","Dedicated Xray"):pick("ثبت نشده","Not configured")}</Badge></div>
            {typeof xrayDomainMeta?.tls_enabled==="boolean"?<div><span>TLS</span><Badge tone={xrayDomainMeta.tls_enabled?"ok":"warn"}>{xrayDomainMeta.tls_enabled?pick("آماده","Ready"):pick("آماده نیست","Not ready")}</Badge></div>:null}
          </div>
          <div className="action-row">
            <button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>void saveXrayDomain()}>{busy==="xray-domain"?"…":pick("ذخیره دامنه","Save domain")}</button>
            <button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void prepareXrayDomain()}>{busy==="xray-prepare"?"…":pick("ذخیره + آماده‌سازی TLS","Save + prepare TLS")}</button>
          </div>
        </div>
      </Modal>:null}
    </div>
  </Shell>;
}
