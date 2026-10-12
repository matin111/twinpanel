"use client";

import Link from "next/link";
import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {AdminNode,AdminTunnel,RuntimeRow} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {tunnelTransportApi} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const online=(value:unknown)=>s(value).toLowerCase()==="online";

function Modal({title,sub,onClose,children}:{title:string;sub?:string;onClose:()=>void;children:React.ReactNode}){
  return <div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" aria-label="close" onClick={onClose}/><div className="runtime-modal-card"><div className="card-head"><div><b>{title}</b>{sub&&<small>{sub}</small>}</div><button type="button" className="icon-button" onClick={onClose}>×</button></div>{children}</div></div>;
}

type Draft={iran_node_id:number;exit_node_id:number;priority:number};
const emptyDraft:Draft={iran_node_id:0,exit_node_id:0,priority:100};

export function LegacyTunnelsExactPage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<AdminTunnel[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [manageOpen,setManageOpen]=useState(false);
  const [selected,setSelected]=useState<AdminTunnel|null>(null);
  const [health,setHealth]=useState<RuntimeRow|null>(null);
  const [draft,setDraft]=useState<Draft>(emptyDraft);
  const [createStep,setCreateStep]=useState("");

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    setError("");
    try{
      const [tunnelRows,nodeRows]=await Promise.all([legacyControlApi.tunnels(),legacyControlApi.nodes()]);
      setRows(tunnelRows);
      setNodes(nodeRows);
      setSelected(current=>current?(tunnelRows.find(item=>item.id===current.id)||current):null);
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

  const nodeMap=useMemo(()=>new Map(nodes.map(item=>[item.id,item])),[nodes]);
  const iranNodes=nodes.filter(item=>s(item.node_type).toLowerCase()==="iran");
  const exitNodes=nodes.filter(item=>s(item.node_type).toLowerCase()==="exit");

  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    if(!q)return rows;
    return rows.filter(item=>{
      const iran=nodeMap.get(item.iran_node_id);
      const exit=nodeMap.get(item.exit_node_id);
      return `${item.id} ${item.status||""} ${iran?.name||""} ${iran?.public_ip||""} ${exit?.name||""} ${exit?.public_ip||""}`.toLowerCase().includes(q);
    });
  },[rows,query,nodeMap]);

  const onlineCount=rows.filter(item=>online(item.status)).length;
  const degraded=rows.filter(item=>s(item.status).toLowerCase()==="degraded").length;
  const offlineCount=rows.filter(item=>!online(item.status)&&s(item.status).toLowerCase()!=="degraded").length;

  const act=async(key:string,label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(key);setError("");setOk("");
    try{
      await fn();
      setOk(label);
      await load(true);
      if(selected){
        const current=(await legacyControlApi.tunnels()).find(item=>item.id===selected.id);
        if(current)setSelected(current);
      }
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  const openCreate=()=>{
    setError("");setOk("");setCreateStep("");
    setDraft({iran_node_id:iranNodes[0]?.id||0,exit_node_id:exitNodes[0]?.id||0,priority:100});
    setCreateOpen(true);
  };

  const create=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;
    if(!draft.iran_node_id||!draft.exit_node_id){
      setError(pick("نود ایران و خروج را انتخاب کنید","Select Iran and exit nodes"));
      return;
    }

    setBusy("create");setError("");setOk("");
    setCreateStep(pick("در حال ساخت مسیر هوشمند…","Creating managed route…"));

    try{
      const managed=await legacyControlApi.createManagedTunnel({
        iran_node_id:draft.iran_node_id,
        exit_node_id:draft.exit_node_id,
        transport:"kcp_2027",
        priority:draft.priority,
        is_active:true,
      });

      if(!managed?.tunnel?.id){
        throw new Error(pick("پاسخ ساخت تانل معتبر نبود.","Managed tunnel creation returned no tunnel."));
      }

      await load(true);
      setCreateOpen(false);
      setOk(managed.operational===false
        ?pick("تانل ثبت شد اما هنوز مسیر سالم ندارد.","Tunnel was registered but has no healthy path yet.")
        :pick("تانل ساخته شد و مدیریت مسیرها خودکار است.","Tunnel created with automatic path management."));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setCreateStep("");
      setBusy("");
    }
  };

  const openManage=async(item:AdminTunnel)=>{
    setSelected(item);setManageOpen(true);setHealth(null);setError("");setOk("");
    setBusy("health");
    try{setHealth(await legacyControlApi.tunnelHealth(item.id));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const toggle=async(item:AdminTunnel)=>{
    const action=item.is_active?pick("غیرفعال","disable"):pick("فعال","enable");
    if(!window.confirm(pick(`تانل #${item.id} ${action} شود؟`,`Change enabled state for tunnel #${item.id}?`)))return;
    await act(`toggle-${item.id}`,pick("وضعیت تانل تغییر کرد","Tunnel state updated"),()=>legacyControlApi.toggleTunnel(item.id));
  };

  const repair=async(item:AdminTunnel)=>{
    if(!window.confirm(pick(`تعمیر خودکار تانل #${item.id} اجرا شود؟`,`Run automatic repair for tunnel #${item.id}?`)))return;
    await act(`repair-${item.id}`,pick("تعمیر خودکار اجرا شد","Automatic repair finished"),()=>tunnelTransportApi.managedRepair(item.id));
    try{setHealth(await legacyControlApi.tunnelHealth(item.id));}catch{}
  };

  const remove=async(item:AdminTunnel)=>{
    if(!window.confirm(pick(`تانل #${item.id} حذف شود؟`,`Delete tunnel #${item.id}?`)))return;
    await act(`delete-${item.id}`,pick("تانل حذف شد","Tunnel deleted"),()=>legacyControlApi.deleteTunnel(item.id));
    setManageOpen(false);setSelected(null);setHealth(null);
  };

  const healthTunnel=(health?.tunnel&&typeof health.tunnel==="object"?health.tunnel:{}) as RuntimeRow;

  return <Shell active="/admin/tunnels"><div className="page legacy-control-page">
    <div className="page-head"><div><h1>{pick("تانل‌ها","Tunnels")}</h1><small>{pick("هر نود ایران می‌تواند هم‌زمان به چند نود خارج متصل شود؛ انتخاب مسیر داخلی کاملاً خودکار است.","Each Iran node can connect to multiple Exit nodes simultaneously; internal path selection is automatic.")}</small></div><div className="action-row"><Link className="ghost" href="/admin/tunnel-transports">{pick("ترانسپورت‌ها","Transports")}</Link><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={openCreate}>＋ {pick("تانل جدید","New tunnel")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats"><Stat label={pick("کل تانل‌ها","Total tunnels")} value={rows.length.toLocaleString("fa-IR")}/><Stat label={pick("آنلاین","Online")} value={onlineCount.toLocaleString("fa-IR")}/><Stat label={pick("Degraded","Degraded")} value={degraded.toLocaleString("fa-IR")}/><Stat label={pick("آفلاین","Offline")} value={offlineCount.toLocaleString("fa-IR")}/></div>

    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("نام نود، IP یا شناسه…","Node, IP or ID…")}/></label></div>
      <div className="table"><table><thead><tr><th>{pick("مسیر","Path")}</th><th>{pick("Ping","Ping")}</th><th>{pick("اولویت","Priority")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("اجرا","Enabled")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(item=>{const iran=nodeMap.get(item.iran_node_id);const exit=nodeMap.get(item.exit_node_id);return <tr key={item.id}><td><div className="user-cell"><b>{iran?.name||`#${item.iran_node_id}`} → {exit?.name||`#${item.exit_node_id}`}</b><small dir="ltr">{iran?.public_ip||"—"} → {exit?.public_ip||"—"}</small></div></td><td dir="ltr">{item.latency_ms==null?"—":`${item.latency_ms} ms`}</td><td>{n(item.priority).toLocaleString("fa-IR")}</td><td><Badge tone={online(item.status)?"ok":s(item.status).toLowerCase()==="degraded"?"warn":"bad"}>{s(item.status)||"—"}</Badge></td><td><Badge tone={item.is_active?"ok":"warn"}>{item.is_active?pick("فعال","Active"):pick("خاموش","Disabled")}</Badge></td><td><div className="row-actions"><button className="primary-soft" onClick={()=>void openManage(item)}>{pick("مدیریت","Manage")}</button><button disabled={!!busy} onClick={()=>void repair(item)}>{busy===`repair-${item.id}`?"…":pick("تعمیر","Repair")}</button><button disabled={!!busy} onClick={()=>void toggle(item)}>{item.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button><button className="danger" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button></div></td></tr>;})}</tbody></table>{!filtered.length&&!loading&&<div className="runtime-empty">{pick("تانلی پیدا نشد","No tunnels found")}</div>}</div>
    </Card>

    {createOpen&&<Modal title={pick("ساخت تانل","Create tunnel")} sub={pick("یک ایران را می‌توانید برای چند خروجی مختلف دوباره انتخاب کنید.","The same Iran node can be reused for multiple different Exit nodes.")} onClose={()=>!busy&&setCreateOpen(false)}>
      <form onSubmit={create}>
        {(!iranNodes.length||!exitNodes.length)&&<div className="runtime-warning">{pick("برای ساخت تانل حداقل یک نود ایران و یک نود خروجی لازم است.","At least one Iran node and one Exit node are required.")}</div>}
        <div className="setting-grid">
          <label className="field"><span>{pick("نود ایران","Iran node")}</span><select value={draft.iran_node_id} onChange={e=>setDraft(d=>({...d,iran_node_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب","Select")}</option>{iranNodes.map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select></label>
          <label className="field"><span>{pick("نود خروج","Exit node")}</span><select value={draft.exit_node_id} onChange={e=>setDraft(d=>({...d,exit_node_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب","Select")}</option>{exitNodes.map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select></label>
          <label className="field"><span>{pick("اولویت مسیر","Route priority")}</span><input type="number" min={1} value={draft.priority} onChange={e=>setDraft(d=>({...d,priority:Math.max(1,Number(e.target.value)||1)}))}/></label>
        </div>
        {createStep&&<div className="runtime-warning">{createStep}</div>}
        <div className="modalActions"><button type="button" className="ghost" disabled={!!busy} onClick={()=>setCreateOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="create"||!draft.iran_node_id||!draft.exit_node_id}>{busy==="create"?pick("در حال ساخت…","Creating…"):pick("ساخت تانل","Create tunnel")}</button></div>
      </form>
    </Modal>}

    {manageOpen&&selected&&<Modal title={pick("مدیریت تانل","Tunnel management")} sub={`#${selected.id} · ${nodeMap.get(selected.iran_node_id)?.name||selected.iran_node_id} → ${nodeMap.get(selected.exit_node_id)?.name||selected.exit_node_id}`} onClose={()=>!busy&&setManageOpen(false)}>
      <div className="manage-card-section">
        <div className="manage-section-head"><div><b>{pick("وضعیت مسیر","Route status")}</b><small>{pick("جزئیات فنی ترانسپورت‌ها در صفحه جدا نگهداری می‌شود.","Transport internals are kept on the separate advanced page.")}</small></div><button className="ghost" disabled={!!busy} onClick={async()=>{setBusy("health");try{setHealth(await legacyControlApi.tunnelHealth(selected.id));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}}}>{busy==="health"?"…":pick("بررسی سلامت","Check health")}</button></div>
        <div className="legacy-detail-grid"><div><small>{pick("وضعیت","Status")}</small><b>{s(healthTunnel.status||selected.status)||"—"}</b></div><div><small>{pick("Ping","Ping")}</small><b dir="ltr">{n(healthTunnel.latency_ms||selected.latency_ms)?`${n(healthTunnel.latency_ms||selected.latency_ms)} ms`:"—"}</b></div><div><small>{pick("حالت مدیریت","Management")}</small><b>{pick("خودکار","Automatic")}</b></div><div><small>{pick("شناسه","ID")}</small><b>#{selected.id}</b></div></div>
      </div>
      <div className="action-row"><button className="primary-soft" disabled={!!busy} onClick={()=>void repair(selected)}>{busy===`repair-${selected.id}`?"…":pick("تعمیر خودکار","Auto repair")}</button><Link className="ghost" href={`/admin/tunnel-transports?tunnel=${selected.id}`}>{pick("جزئیات ترانسپورت‌ها","Transport details")}</Link></div>
      <div className="modalActions"><button className="ghost" onClick={()=>setManageOpen(false)}>{pick("بستن","Close")}</button><button disabled={!!busy} onClick={()=>void toggle(selected)}>{selected.is_active?pick("غیرفعال کردن","Disable"):pick("فعال کردن","Enable")}</button><button className="danger" disabled={!!busy} onClick={()=>void remove(selected)}>{pick("حذف کامل تانل","Delete tunnel")}</button></div>
    </Modal>}
  </div></Shell>;
}
