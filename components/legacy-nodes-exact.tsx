"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,RuntimeRow} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";

const s=(v:unknown)=>String(v??"");
const n=(v:unknown)=>{const x=Number(v??0);return Number.isFinite(x)?x:0;};
const date=(v:unknown)=>{if(!v)return "—";const d=new Date(String(v));return Number.isNaN(d.getTime())?String(v):d.toLocaleString("fa-IR");};
const tone=(v:unknown):"ok"|"warn"|"bad"|"violet"=>{const x=s(v).toLowerCase();return ["active","online","ok","healthy","configured"].includes(x)?"ok":["inactive","offline","failed","error","expired","canceled"].includes(x)?"bad":"warn";};
const protocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"] as const;
const protocolLabels:Record<(typeof protocolKeys)[number],string>={cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray"};

type NodeRole="mother"|"iran"|"exit";
type NodeModal="protocols"|"ssh"|"domain"|null;
type ExtendedNode=AdminNode&{is_mother?:boolean;public_domain?:string|null};

type ProtocolRuntime={protocol?:string;name?:string;installed?:boolean;ok?:boolean;service?:string;listeners?:Record<string,boolean>;port_text?:string;transport?:string};

function roleOf(node:ExtendedNode):NodeRole{
  if(node.is_mother||node.node_type==="mother"||node.node_type==="core")return "mother";
  return node.node_type==="iran"?"iran":"exit";
}
function enabledProtocols(node:ExtendedNode){return protocolKeys.filter(key=>Boolean(node[`enable_${key}` as keyof ExtendedNode]));}
function Notice({error,ok,warning}:{error:string;ok:string;warning?:string}){return <>{error&&<div className="runtime-error">{error}</div>}{warning&&<div className="runtime-warning">{warning}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}

export function LegacyNodesRuntimePage(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<ExtendedNode[]>([]);
  const [domains,setDomains]=useState<RuntimeRow[]>([]);
  const [selectedId,setSelectedId]=useState(0);
  const [filter,setFilter]=useState<"all"|"iran"|"exit">("all");
  const [q,setQ]=useState("");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [warning,setWarning]=useState("");
  const [ok,setOk]=useState("");
  const [modal,setModal]=useState<NodeModal>(null);
  const [accessConfigured,setAccessConfigured]=useState(false);
  const [accessDraft,setAccessDraft]=useState({port:22,username:"root",password:""});
  const [domainDraft,setDomainDraft]=useState("");
  const [runtime,setRuntime]=useState<Record<string,ProtocolRuntime>>({});

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    setError("");
    try{
      const ns=await adminApi.nodes() as ExtendedNode[];
      setNodes(ns);
      setSelectedId(id=>id&&ns.some(x=>x.id===id)?id:(ns[0]?.id||0));
      try{
        const ds=await legacyAdminApi.nodeDomains();
        setDomains(Array.isArray(ds.nodes)?ds.nodes:[]);
        setWarning("");
      }catch{
        setDomains([]);
        setWarning(pick("لیست نودها دریافت شد، اما سرویس دامنه نود پاسخ نداد. سایر مدیریت نود قابل استفاده است.","Nodes loaded, but node-domain service did not respond. Other node management remains available."));
      }
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{if(!silent)setLoading(false);}
  };

  useEffect(()=>{void load();const id=window.setInterval(()=>void load(true),15000);return()=>window.clearInterval(id);},[]);

  const selected=nodes.find(x=>x.id===selectedId)||null;
  const selectedRole=selected?roleOf(selected):null;
  const selectedDomain=selected?domains.find(x=>n(x.id||x.node_id)===selected.id):null;
  const effectiveDomain=s(selected?.public_domain||selectedDomain?.public_domain||selectedDomain?.domain);
  const selectedProtocols=selected?enabledProtocols(selected):[];

  const filtered=useMemo(()=>{
    const needle=q.trim().toLowerCase();
    return nodes.filter(node=>{
      const role=roleOf(node);
      if(filter!=="all"&&role!==filter)return false;
      if(!needle)return true;
      return `${node.id} ${node.name} ${node.public_ip||""} ${node.public_domain||""} ${node.country_code||""} ${role}`.toLowerCase().includes(needle);
    });
  },[nodes,q,filter]);

  useEffect(()=>{
    if(!selected){setAccessConfigured(false);return;}
    let active=true;
    legacyAdminApi.nodeAccess(selected.id).then(result=>{
      if(!active)return;
      setAccessConfigured(Boolean(result.configured));
      setAccessDraft({port:n(result.port)||22,username:s(result.username)||"root",password:""});
    }).catch(()=>{if(active){setAccessConfigured(false);setAccessDraft({port:22,username:"root",password:""});}});
    setDomainDraft(effectiveDomain);
    setRuntime({});
    return()=>{active=false;};
  },[selectedId,effectiveDomain]);

  const flash=(message:string)=>{setOk(message);window.setTimeout(()=>setOk(""),2800);};
  const fail=(e:unknown,fallback:string)=>setError(e instanceof Error?e.message:fallback);
  const openSsh=()=>{setError("");setAccessDraft(d=>({...d,password:""}));setModal("ssh");};
  const ensureAccess=()=>{if(accessConfigured)return true;setWarning(pick("برای این عملیات ابتدا دسترسی SSH نود را ثبت کنید.","Register SSH access before this operation."));openSsh();return false;};

  const saveAccess=async()=>{
    if(!selected||busy)return;
    if(!accessDraft.password){setError(pick("رمز SSH را وارد کنید.","Enter the SSH password."));return;}
    setBusy("ssh");setError("");setWarning("");
    try{
      await legacyAdminApi.saveNodeAccess({node_id:selected.id,host:selected.public_ip||effectiveDomain,port:accessDraft.port,username:accessDraft.username,password:accessDraft.password});
      setAccessConfigured(true);setModal(null);setAccessDraft(d=>({...d,password:""}));flash(pick("دسترسی SSH ثبت شد.","SSH access saved."));
    }catch(e){fail(e,pick("ثبت دسترسی SSH ناموفق بود.","Failed to save SSH access."));}
    finally{setBusy("");}
  };

  const saveDomain=async()=>{
    if(!selected||busy)return;
    setBusy("domain");setError("");
    try{
      const result=await legacyAdminApi.updateNodeDomain(selected.id,domainDraft.trim());
      const value=s(result.public_domain||domainDraft.trim());
      setDomains(current=>{
        const next:RuntimeRow={id:selected.id,node_id:selected.id,public_domain:value,domain:value};
        return current.some(x=>n(x.id||x.node_id)===selected.id)?current.map(x=>n(x.id||x.node_id)===selected.id?{...x,...next}:x):[...current,next];
      });
      setModal(null);flash(pick("دامنه نود ذخیره شد.","Node domain saved."));
    }catch(e){fail(e,pick("ذخیره دامنه ناموفق بود.","Failed to save domain."));}
    finally{setBusy("");}
  };

  const checkProtocols=async(open=true)=>{
    if(!selected||busy||selectedRole==="iran")return;
    if(!ensureAccess())return;
    setBusy("health");setError("");setWarning("");
    try{
      const result=await legacyAdminApi.protocolHealth(selected.id);
      const map=result&&typeof result.protocols==="object"&&result.protocols?result.protocols as Record<string,ProtocolRuntime>:{};
      setRuntime(map);
      if(open)setModal("protocols");
      flash(result.ok?pick("پروتکل‌های نود سالم هستند.","Node protocols are healthy."):pick("برخی پروتکل‌ها نیاز به بررسی دارند.","Some protocols need attention."));
    }catch(e){fail(e,pick("بررسی پروتکل‌ها ناموفق بود.","Protocol health check failed."));}
    finally{setBusy("");}
  };

  const restartProtocol=async(key:string)=>{
    if(!selected||busy||!ensureAccess())return;
    setBusy(`restart-${key}`);setError("");
    try{
      const result=await legacyAdminApi.restartProtocol(selected.id,key);
      const p=result&&typeof result.protocol==="object"&&result.protocol?result.protocol as ProtocolRuntime:runtime[key];
      setRuntime(current=>({...current,[key]:p||{}}));
      flash(s(result.message)||`${protocolLabels[key as keyof typeof protocolLabels]} ${pick("ریستارت شد","restarted")}`);
    }catch(e){fail(e,pick("ریستارت پروتکل ناموفق بود.","Protocol restart failed."));}
    finally{setBusy("");}
  };

  const restartAll=async()=>{
    if(!selected||busy||selectedRole==="iran"||!ensureAccess())return;
    if(!window.confirm(pick(`همه پروتکل‌های فعال روی «${selected.name}» ریستارت شوند؟`,`Restart all enabled protocols on ${selected.name}?`)))return;
    setBusy("restart-all");setError("");
    try{
      for(const key of selectedProtocols)await legacyAdminApi.restartProtocol(selected.id,key);
      const result=await legacyAdminApi.protocolHealth(selected.id);
      setRuntime(result&&typeof result.protocols==="object"&&result.protocols?result.protocols as Record<string,ProtocolRuntime>:{});
      flash(pick("همه پروتکل‌های نود ریستارت شدند.","All node protocols restarted."));
    }catch(e){fail(e,pick("ریستارت همه پروتکل‌ها ناموفق بود.","Restart-all failed."));}
    finally{setBusy("");}
  };

  const repair=async()=>{
    if(!selected||busy||selectedRole!=="exit"||!ensureAccess())return;
    if(!window.confirm(pick(`پروتکل‌های نصب‌شده روی «${selected.name}» بررسی و تعمیر شوند؟`,`Check and repair installed protocols on ${selected.name}?`)))return;
    setBusy("repair");setError("");
    try{const result=await legacyAdminApi.repairProtocolsSaved(selected.id);flash(s(result.message)||pick("تعمیر سرویس‌ها انجام شد.","Services repaired."));await load(true);}
    catch(e){fail(e,pick("تعمیر سرویس‌ها ناموفق بود.","Service repair failed."));}
    finally{setBusy("");}
  };

  const upgradeAgent=async()=>{
    if(!selected||busy||selectedRole==="mother"||!ensureAccess())return;
    if(!window.confirm(pick(`Node Agent روی «${selected.name}» ارتقا پیدا کند؟`,`Upgrade Node Agent on ${selected.name}?`)))return;
    setBusy("agent");setError("");
    try{const result=await legacyAdminApi.upgradeAgent(selected.id);flash(s(result.message)||pick("Node Agent ارتقا یافت.","Node Agent upgraded."));await load(true);}
    catch(e){fail(e,pick("ارتقای Agent ناموفق بود.","Agent upgrade failed."));}
    finally{setBusy("");}
  };

  const installFabric=async()=>{
    if(!selected||busy||selectedRole==="mother"||!ensureAccess())return;
    if(!window.confirm(pick(`Tunnel Fabric روی «${selected.name}» نصب یا بهینه‌سازی شود؟`,`Install or optimize Tunnel Fabric on ${selected.name}?`)))return;
    setBusy("fabric");setError("");
    try{const result=await legacyAdminApi.installTunnelFabric(selected.id);const fabric=result&&typeof result.fabric==="object"&&result.fabric?result.fabric as RuntimeRow:{};flash(`${pick("Tunnel Fabric آماده است","Tunnel Fabric is ready")}${fabric.profile?` - ${s(fabric.profile)}`:""}`);}
    catch(e){fail(e,pick("نصب Tunnel Fabric ناموفق بود.","Tunnel Fabric installation failed."));}
    finally{setBusy("");}
  };

  const toggleMaintenance=async()=>{
    if(!selected||busy||selectedRole==="mother")return;
    setBusy("maintenance");setError("");
    try{const updated=await adminApi.toggleNodeMaintenance(selected.id);setNodes(current=>current.map(x=>x.id===updated.id?{...x,...updated}:x));flash(updated.status==="maintenance"?pick("حالت نگهداری فعال شد.","Maintenance enabled."):pick("نود به سرویس برگشت.","Node returned to service."));}
    catch(e){fail(e,pick("تغییر وضعیت نود ناموفق بود.","Failed to change node status."));}
    finally{setBusy("");}
  };

  const deleteNode=async()=>{
    if(!selected||busy||selectedRole==="mother")return;
    if(!window.confirm(pick(`نود «${selected.name}» حذف شود؟ این عملیات قابل بازگشت نیست.`,`Delete ${selected.name}? This cannot be undone.`)))return;
    setBusy("delete");setError("");
    try{await adminApi.deleteNode(selected.id);flash(pick("نود حذف شد.","Node deleted."));setSelectedId(0);await load();}
    catch(e){fail(e,pick("حذف نود ناموفق بود.","Node deletion failed."));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/nodes"><div className="page legacy-nodes-page">
    <div className="page-head"><div><h1>{pick("نودها","Nodes")}</h1><small>{pick("مدیریت نود مطابق جریان پنل قدیمی؛ عملیات حساس فقط هنگام درخواست اجرا می‌شوند.","Legacy node workflow; sensitive operations run only on request.")}</small></div><Link href="/admin/provision" className="primary">＋ {pick("افزودن نود","Add node")}</Link></div>
    <Notice error={error} warning={warning} ok={ok}/>
    <div className="stats dashboard-stats"><Stat label={pick("کل نودها","Total nodes")} value={String(nodes.length)}/><Stat label={pick("آنلاین","Online")} value={String(nodes.filter(x=>s(x.status).toLowerCase()==="online").length)}/><Stat label={pick("ایران","Iran")} value={String(nodes.filter(x=>roleOf(x)==="iran").length)}/><Stat label={pick("خروجی","Exit")} value={String(nodes.filter(x=>roleOf(x)==="exit").length)}/></div>

    <div className="legacy-node-toolbar"><div className="filter-tabs"><button className={filter==="all"?"active":""} onClick={()=>setFilter("all")}>{pick("همه","All")}</button><button className={filter==="iran"?"active":""} onClick={()=>setFilter("iran")}>{pick("ایران","Iran")}</button><button className={filter==="exit"?"active":""} onClick={()=>setFilter("exit")}>{pick("خروجی","Exit")}</button></div><label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("نام، IP، دامنه…","Name, IP, domain…")}/></label><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button></div>

    {loading&&nodes.length===0?<Card><div className="runtime-loading">{pick("در حال دریافت نودها…","Loading nodes…")}</div></Card>:nodes.length===0?<Card><div className="runtime-empty">{pick("نودی ثبت نشده است.","No nodes registered.")}</div></Card>:<div className="legacy-node-workspace">
      <div className="legacy-node-list">{filtered.map(node=>{const role=roleOf(node);const domain=s(node.public_domain||domains.find(x=>n(x.id||x.node_id)===node.id)?.public_domain);return <button key={node.id} className={`legacy-node-card ${selectedId===node.id?"selected":""}`} onClick={()=>setSelectedId(node.id)}><div className="node-card-top"><span className={`node-role ${role}`}>{role==="mother"?pick("مادر","Mother"):role==="iran"?pick("ایران","Iran"):pick("خروجی","Exit")}</span><Badge tone={tone(node.status)}>{node.status||"—"}</Badge></div><b>{node.name}</b><small dir="ltr">{domain||node.public_ip||"—"}</small><div className="node-card-foot"><span>{pick("کاربر","Users")}: {n(node.current_users)}</span><span>{date(node.last_seen_at)}</span></div></button>})}</div>

      {selected&&<Card className="legacy-node-inspector"><div className="card-head"><div><b>{selected.name}</b><small>#{selected.id} · {selectedRole==="mother"?pick("سرور مادر","Mother server"):selectedRole==="iran"?pick("نود ایران","Iran node"):pick("نود خروجی","Exit node")}</small></div><Badge tone={tone(selected.status)}>{selected.status||"—"}</Badge></div>
        <div className="subs-summary-grid"><div><span>IP</span><b dir="ltr">{selected.public_ip||"—"}</b></div><div><span>{pick("دامنه","Domain")}</span><b dir="ltr">{effectiveDomain||pick("ثبت نشده","Not set")}</b></div><div><span>{pick("کاربران متصل","Connected users")}</span><b>{n(selected.current_users)} / {n(selected.capacity_users)}</b></div><div><span>Heartbeat</span><b>{date(selected.last_seen_at)}</b></div></div>
        {selectedRole==="iran"?<div className="node-role-note"><b>{pick("نود تونل ایران","Iran tunnel node")}</b><small>{pick("فقط Tunnel / Relay — بدون پروتکل کاربری","Tunnel / Relay only — no user VPN protocols")}</small></div>:<div className="node-protocol-chips">{protocolKeys.map(key=><span key={key} className={selectedProtocols.includes(key)?"on":"off"}>{protocolLabels[key]}</span>)}</div>}
        <div className="node-action-grid">
          {selectedRole!=="iran"&&<button className="primary" disabled={!!busy} onClick={()=>void checkProtocols(true)}>{busy==="health"?"…":pick("بررسی پروتکل‌ها","Check protocols")}</button>}
          {selectedRole!=="iran"&&<button className="ghost" disabled={!!busy} onClick={()=>{if(accessConfigured){setModal("protocols");void checkProtocols(false);}else openSsh();}}>{pick("مدیریت پروتکل‌ها","Manage protocols")}</button>}
          {selectedRole==="exit"&&<button className="ghost" disabled={!!busy} onClick={()=>void repair()}>{busy==="repair"?"…":pick("تعمیر سرویس‌ها","Repair services")}</button>}
          {selectedRole!=="mother"&&<button className="ghost" disabled={!!busy} onClick={()=>void upgradeAgent()}>{busy==="agent"?"…":pick("ارتقای Agent","Upgrade agent")}</button>}
          <button className="ghost" onClick={()=>{setDomainDraft(effectiveDomain);setModal("domain");}}>{pick("دامنه سرور","Server domain")}</button>
          {selectedRole!=="mother"&&<button className="ghost" onClick={openSsh}>{accessConfigured?pick("دسترسی SSH","SSH access"):pick("ثبت دسترسی SSH","Register SSH")}</button>}
          {selectedRole!=="mother"&&<button className="ghost" disabled={!!busy} onClick={()=>void toggleMaintenance()}>{busy==="maintenance"?"…":selected.status==="maintenance"?pick("بازگشت به سرویس","Return to service"):pick("حالت نگهداری","Maintenance")}</button>}
          {selectedRole!=="mother"&&<button className="ghost" disabled={!!busy} onClick={()=>void installFabric()}>{busy==="fabric"?"…":pick("Tunnel Fabric","Tunnel Fabric")}</button>}
          {selectedRole!=="iran"&&<button className="ghost" disabled={!!busy||selectedProtocols.length===0} onClick={()=>void restartAll()}>{busy==="restart-all"?"…":pick("ریستارت همه پروتکل‌ها","Restart all protocols")}</button>}
          {selectedRole!=="mother"&&<button className="danger" disabled={!!busy} onClick={()=>void deleteNode()}>{busy==="delete"?"…":pick("حذف نود","Delete node")}</button>}
        </div>
      </Card>}
    </div>}

    {modal==="ssh"&&selected&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" onClick={()=>!busy&&setModal(null)}/><div className="runtime-modal-card"><div className="card-head"><div><b>{pick("دسترسی SSH","SSH access")}</b><small>{selected.name}</small></div><button className="icon-button" disabled={!!busy} onClick={()=>setModal(null)}>×</button></div><div className="setting-grid"><label className="field"><span>Host</span><input dir="ltr" value={effectiveDomain||selected.public_ip||""} disabled/></label><label className="field"><span>{pick("پورت SSH","SSH port")}</span><input type="number" min={1} max={65535} value={accessDraft.port} onChange={e=>setAccessDraft(d=>({...d,port:Number(e.target.value)||22}))}/></label><label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={accessDraft.username} onChange={e=>setAccessDraft(d=>({...d,username:e.target.value}))}/></label><label className="field"><span>{pick("رمز SSH","SSH password")}</span><input dir="ltr" type="password" value={accessDraft.password} onChange={e=>setAccessDraft(d=>({...d,password:e.target.value}))}/></label></div><div className="runtime-modal-actions"><button className="ghost" disabled={!!busy} onClick={()=>setModal(null)}>{pick("بستن","Close")}</button><button className="primary" disabled={!!busy||!accessDraft.password} onClick={()=>void saveAccess()}>{busy==="ssh"?"…":pick("ثبت دسترسی","Save access")}</button></div></div></div>}

    {modal==="domain"&&selected&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" onClick={()=>!busy&&setModal(null)}/><div className="runtime-modal-card"><div className="card-head"><div><b>{pick("دامنه سرور","Server domain")}</b><small>{selected.name}</small></div><button className="icon-button" disabled={!!busy} onClick={()=>setModal(null)}>×</button></div><label className="field"><span>{pick("دامنه عمومی","Public domain")}</span><input dir="ltr" value={domainDraft} onChange={e=>setDomainDraft(e.target.value)} placeholder="de.example.com"/></label><div className="runtime-modal-actions"><button className="ghost" disabled={!!busy} onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={!!busy} onClick={()=>void saveDomain()}>{busy==="domain"?"…":pick("ذخیره دامنه","Save domain")}</button></div></div></div>}

    {modal==="protocols"&&selected&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" onClick={()=>!busy&&setModal(null)}/><div className="runtime-modal-card wide protocol-manager-modal"><div className="card-head"><div><b>{pick("پروتکل‌های","Protocols of")} {selected.name}</b><small>{accessConfigured?pick("SSH آماده است","SSH ready"):pick("SSH ثبت نشده","SSH not configured")}</small></div><button className="icon-button" disabled={!!busy} onClick={()=>setModal(null)}>×</button></div><div className="protocol-modal-toolbar"><Badge tone={accessConfigured?"ok":"bad"}>{accessConfigured?pick("SSH آماده","SSH ready"):pick("SSH ثبت نشده","SSH missing")}</Badge><button className="ghost" disabled={!!busy} onClick={()=>void checkProtocols(false)}>{busy==="health"?"…":pick("بررسی همه","Check all")}</button></div><div className="protocol-health-grid">{protocolKeys.map(key=>{const live=runtime[key]||{};const enabled=selectedProtocols.includes(key);const listeners=Object.entries(live.listeners||{});return <div className={`protocol-health-card ${enabled?"enabled":"disabled"}`} key={key}><div><b>{protocolLabels[key]}</b><small>{live.service||live.port_text||pick("بررسی نشده","Not checked")}</small><div className="protocol-listeners">{listeners.length?listeners.map(([name,state])=><span key={name} className={state?"live":"dead"}>{name}</span>):<span className="dead">Listener —</span>}</div></div><Badge tone={live.ok?"ok":enabled?"warn":"bad"}>{live.ok?"ONLINE":enabled?"READY":"OFF"}</Badge><button className="mini-btn" disabled={!enabled||!!busy} onClick={()=>void restartProtocol(key)}>{busy===`restart-${key}`?"…":pick("ریستارت","Restart")}</button></div>})}</div><div className="runtime-modal-actions"><button className="ghost" disabled={!!busy} onClick={()=>setModal(null)}>{pick("بستن","Close")}</button><button className="danger" disabled={!!busy||selectedProtocols.length===0} onClick={()=>void restartAll()}>{busy==="restart-all"?"…":pick("ریستارت همه","Restart all")}</button></div></div></div>}
  </div></Shell>;
}
