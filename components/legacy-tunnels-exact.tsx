"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {AdminNode,AdminTunnel,RuntimeRow} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const online=(value:unknown)=>s(value).toLowerCase()==="online";
const transportLabel=(value:unknown)=>({backhaul:"Backhaul",ssh_tun:"SSH TUN",ssh_relay:"SSH Relay",mtunnel:"MTunnel",wireguard:"WireGuard"} as Record<string,string>)[s(value).toLowerCase()]||s(value)||"—";

type TransportName="mtunnel"|"backhaul"|"ssh_tun";
const transportOrder:TransportName[]=["mtunnel","backhaul","ssh_tun"];
const transportPriority:Record<TransportName,number>={mtunnel:90,backhaul:100,ssh_tun:200};

function Modal({title,sub,onClose,children,wide=false}:{title:string;sub?:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){
  return <div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" aria-label="close" onClick={onClose}/><div className={`runtime-modal-card ${wide?"manage-card":""}`}><div className="card-head"><div><b>{title}</b>{sub&&<small>{sub}</small>}</div><button type="button" className="icon-button" onClick={onClose}>×</button></div>{children}</div></div>;
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
  const [draft,setDraft]=useState<Draft>(emptyDraft);
  const [health,setHealth]=useState<RuntimeRow|null>(null);
  const [transports,setTransports]=useState<RuntimeRow[]>([]);
  const [mode,setMode]=useState("manual");
  const [preferred,setPreferred]=useState<TransportName>("mtunnel");
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
      return `${item.id} ${item.transport||""} ${item.active_transport||""} ${item.status||""} ${iran?.name||""} ${iran?.public_ip||""} ${exit?.name||""} ${exit?.public_ip||""}`.toLowerCase().includes(q);
    });
  },[rows,query,nodeMap]);

  const onlineCount=rows.filter(item=>online(item.status)).length;
  const degraded=rows.filter(item=>s(item.status).toLowerCase()==="degraded").length;
  const offlineCount=rows.filter(item=>!online(item.status)&&s(item.status).toLowerCase()!=="degraded").length;

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,refreshDetail=false)=>{
    if(busy)return;
    setBusy(key);setError("");setOk("");
    try{
      await fn();
      setOk(label);
      await load(true);
      if(refreshDetail&&selected)await loadDetail(selected.id);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  const installTransport=async(tunnelId:number,name:TransportName)=>{
    if(name==="mtunnel")return legacyControlApi.installMtunnel(tunnelId);
    if(name==="backhaul")return legacyControlApi.installBackhaul(tunnelId);
    return legacyControlApi.installSshTunnel(tunnelId);
  };

  const installAll=async(tunnelId:number,withProgress=false)=>{
    const successes:TransportName[]=[];
    const failures:string[]=[];

    if(withProgress){
      setCreateStep(
        pick(
          "در حال نصب MTunnel + Backhaul + SSH TUN…",
          "Installing MTunnel + Backhaul + SSH TUN…",
        ),
      );
    }

    const settled=await Promise.allSettled(
      transportOrder.map(name=>installTransport(tunnelId,name)),
    );

    settled.forEach((result,index)=>{
      const name=transportOrder[index];

      if(result.status==="fulfilled"){
        successes.push(name);
        return;
      }

      const reason=result.reason;
      const message=reason instanceof Error?reason.message:String(reason);
      failures.push(`${transportLabel(name)}: ${message}`);
    });

    if(successes.length){
      const primary=successes[0];
      try{
        await legacyControlApi.setTunnelTransportMode(tunnelId,{mode:"manual",transport:primary});
        setMode("manual");
        setPreferred(primary);
      }catch(reason){
        const message=reason instanceof Error?reason.message:String(reason);
        failures.push(`${pick("انتخاب Transport اصلی","Primary transport selection")}: ${message}`);
      }
    }

    return {successes,failures};
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

    setBusy("create");setError("");setOk("");setCreateStep(pick("در حال ساخت و نصب MTunnel + Backhaul + SSH TUN…","Creating and installing MTunnel + Backhaul + SSH TUN…"));

    try{
      const created=await legacyControlApi.registerTunnel({
        iran_node_id:draft.iran_node_id,
        exit_node_id:draft.exit_node_id,
        transport:"ssh_tun",
        priority:draft.priority,
        is_active:true,
      });

      const tunnelId=Number(created.id);
      if(!tunnelId)throw new Error(pick("شناسه تونل بعد از ثبت دریافت نشد.","Tunnel ID was not returned after registration."));

      const result=await installAll(tunnelId,true);
      setCreateStep(pick("در حال بررسی وضعیت…","Checking status…"));

      await load(true);
      const latest=(await legacyControlApi.tunnels()).find(item=>item.id===tunnelId)||created;
      setSelected(latest);
      setCreateOpen(false);
      setManageOpen(true);
      await loadDetail(tunnelId);

      if(result.failures.length){
        setError(pick(
          `ساخت تونل کامل نشد: ${result.failures.join(" | ")}`,
          `Tunnel setup did not complete: ${result.failures.join(" | ")}`,
        ));
      }else{
        setOk(pick("تونل ساخته شد","Tunnel created"));
      }
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setCreateStep("");
      setBusy("");
    }
  };

  const loadDetail=async(id:number)=>{
    setHealth(null);
    const [h,t]=await Promise.allSettled([legacyControlApi.tunnelHealth(id),legacyControlApi.tunnelTransports(id)]);

    if(h.status==="fulfilled")setHealth(h.value);

    if(t.status==="fulfilled"){
      const items=Array.isArray(t.value.transports)?t.value.transports:[];
      setTransports(items);
      setMode(s(t.value.mode)||"manual");
      const current=s(t.value.preferred_transport||t.value.active_transport||"mtunnel") as TransportName;
      setPreferred(transportOrder.includes(current)?current:"mtunnel");
    }else{
      setTransports([]);
    }

    const errors:string[]=[];
    if(h.status==="rejected")errors.push(h.reason instanceof Error?h.reason.message:String(h.reason));
    if(t.status==="rejected")errors.push(t.reason instanceof Error?t.reason.message:String(t.reason));
    if(errors.length)setError(errors.join(" | "));
  };

  const openManage=async(item:AdminTunnel)=>{
    setSelected(item);setManageOpen(true);setBusy("detail");setError("");setOk("");
    try{await loadDetail(item.id);}finally{setBusy("");}
  };

  const toggle=async(item:AdminTunnel)=>{
    const action=item.is_active?pick("غیرفعال","disable"):pick("فعال","enable");
    if(!window.confirm(pick(`تونل #${item.id} ${action} شود؟`,`Change enabled state for tunnel #${item.id}?`)))return;
    await act(`toggle-${item.id}`,pick("وضعیت تونل تغییر کرد","Tunnel state updated"),()=>legacyControlApi.toggleTunnel(item.id),manageOpen);
  };

  const remove=async(item:AdminTunnel)=>{
    if(!window.confirm(pick(`تونل #${item.id} حذف شود؟`,`Delete tunnel #${item.id}?`)))return;
    await act(`delete-${item.id}`,pick("تونل حذف شد","Tunnel deleted"),()=>legacyControlApi.deleteTunnel(item.id));
    setManageOpen(false);setSelected(null);
  };

  const saveMode=()=>{
    if(!selected)return;
    void act("mode",pick("حالت Transport ذخیره شد","Transport mode saved"),()=>legacyControlApi.setTunnelTransportMode(selected.id,{mode,transport:mode==="manual"?preferred:null}),true);
  };

  const switchTransport=(name:TransportName)=>{
    if(!selected)return;
    const item=transports.find(row=>s(row.transport)===name);
    if(!item||!online(item.status)||!Boolean(item.enabled)){
      setError(pick(`${transportLabel(name)} آماده نیست.`,`${transportLabel(name)} is not ready.`));
      return;
    }
    void act(`switch-${name}`,pick(`Transport فعال به ${transportLabel(name)} تغییر کرد.`,`Active transport switched to ${transportLabel(name)}.`),async()=>{
      await legacyControlApi.setTunnelTransportMode(selected.id,{mode:"manual",transport:name});
      setMode("manual");setPreferred(name);
    },true);
  };

  const install=(name:TransportName)=>{
    if(!selected)return;
    if(!window.confirm(pick(`${transportLabel(name)} برای تونل #${selected.id} نصب/بازسازی شود؟`,`Install/rebuild ${transportLabel(name)} for tunnel #${selected.id}?`)))return;
    void act(`install-${name}`,pick(`${transportLabel(name)} نصب/بازسازی شد.`,`${transportLabel(name)} install/rebuild finished.`),()=>installTransport(selected.id,name),true);
  };

  const installAllFromManage=async()=>{
    if(!selected||busy)return;
    if(!window.confirm(pick(`هر سه Transport روی تونل #${selected.id} نصب/بازسازی شوند؟`,`Install/rebuild all three transports for tunnel #${selected.id}?`)))return;
    setBusy("install-all");setError("");setOk("");
    try{
      const result=await installAll(selected.id,false);
      await load(true);
      await loadDetail(selected.id);
      if(result.failures.length){
        setError(pick(`برخی Transportها کامل نشدند: ${result.failures.join(" | ")}`,`Some transports did not finish: ${result.failures.join(" | ")}`));
      }else{
        setOk(pick("هر سه Transport با موفقیت نصب/بازسازی شدند.","All three transports were installed/rebuilt successfully."));
      }
    }finally{
      setBusy("");
    }
  };

  const repairMtunnel=()=>{
    if(!selected)return;
    if(!window.confirm(pick(`MTunnel تونل #${selected.id} تعمیر شود؟`,`Repair MTunnel for tunnel #${selected.id}?`)))return;
    void act("repair-mtunnel",pick("تعمیر MTunnel انجام شد","MTunnel repair finished"),()=>legacyControlApi.repairMtunnel(selected.id),true);
  };

  const prepare=()=>{
    if(!selected)return;
    if(!window.confirm(pick(`آماده‌سازی پایه تونل #${selected.id} اجرا شود؟`,`Run base preparation for tunnel #${selected.id}?`)))return;
    void act("prepare",pick("آماده‌سازی تونل انجام شد","Tunnel preparation finished"),()=>legacyControlApi.prepareTunnel(selected.id),true);
  };

  const healthTunnel=(health?.tunnel&&typeof health.tunnel==="object"?health.tunnel:{}) as RuntimeRow;
  const normalizedTransports=transportOrder.map(name=>{
    const found=transports.find(item=>s(item.transport).toLowerCase()===name);
    return found||({transport:name,priority:transportPriority[name],enabled:false,status:"not_installed",latency_ms:null,last_error:null} as RuntimeRow);
  });

  return <Shell active="/admin/tunnels"><div className="page legacy-control-page">
    <div className="page-head"><div><h1>{pick("تانل‌ها","Tunnels")}</h1><small>{pick("هر مسیر ایران → خروج شامل MTunnel، Backhaul و SSH TUN با امکان تغییر دستی است","Every Iran → Exit route includes MTunnel, Backhaul and SSH TUN with manual switching")}</small></div><div className="action-row"><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={openCreate}>＋ {pick("تونل جدید","New tunnel")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats"><Stat label={pick("کل تانل‌ها","Total tunnels")} value={rows.length.toLocaleString("fa-IR")}/><Stat label={pick("آنلاین","Online")} value={onlineCount.toLocaleString("fa-IR")}/><Stat label={pick("Degraded","Degraded")} value={degraded.toLocaleString("fa-IR")}/><Stat label={pick("آفلاین","Offline")} value={offlineCount.toLocaleString("fa-IR")}/></div>

    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("نام نود، IP، Transport یا شناسه…","Node, IP, transport or ID…")}/></label></div>
      <div className="table"><table><thead><tr><th>{pick("مسیر","Path")}</th><th>{pick("Transport فعال","Active transport")}</th><th>{pick("Ping","Ping")}</th><th>{pick("اولویت","Priority")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("اجرا","Enabled")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(item=>{const iran=nodeMap.get(item.iran_node_id);const exit=nodeMap.get(item.exit_node_id);return <tr key={item.id}><td><div className="user-cell"><b>{iran?.name||`#${item.iran_node_id}`} → {exit?.name||`#${item.exit_node_id}`}</b><small dir="ltr">{iran?.public_ip||"—"} → {exit?.public_ip||"—"}</small></div></td><td><b dir="ltr">{transportLabel(item.active_transport||item.transport)}</b></td><td dir="ltr">{item.latency_ms==null?"—":`${item.latency_ms} ms`}</td><td>{n(item.priority).toLocaleString("fa-IR")}</td><td><Badge tone={online(item.status)?"ok":s(item.status).toLowerCase()==="degraded"?"warn":"bad"}>{s(item.status)||"—"}</Badge></td><td><Badge tone={item.is_active?"ok":"warn"}>{item.is_active?pick("فعال","Active"):pick("خاموش","Disabled")}</Badge></td><td><div className="row-actions"><button className="primary-soft" onClick={()=>void openManage(item)}>{pick("مدیریت کامل","Full management")}</button><button disabled={!!busy} onClick={()=>void toggle(item)}>{item.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button><button className="danger" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button></div></td></tr>;})}</tbody></table>{!filtered.length&&!loading&&<div className="runtime-empty">{pick("تانلی پیدا نشد","No tunnels found")}</div>}</div>
    </Card>

    {createOpen&&<Modal title={pick("ساخت تانل","Create tunnel")} onClose={()=>!busy&&setCreateOpen(false)}>
      <form onSubmit={create}>
        {(!iranNodes.length||!exitNodes.length)&&<div className="runtime-warning">{pick("برای ساخت تونل حداقل یک نود ایران و یک نود خروجی لازم است.","At least one Iran node and one exit node are required.")}</div>}
        <div className="setting-grid">
          <label className="field"><span>{pick("نود ایران","Iran node")}</span><select value={draft.iran_node_id} onChange={e=>setDraft(d=>({...d,iran_node_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب","Select")}</option>{iranNodes.map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select></label>
          <label className="field"><span>{pick("نود خروج","Exit node")}</span><select value={draft.exit_node_id} onChange={e=>setDraft(d=>({...d,exit_node_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب","Select")}</option>{exitNodes.map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select></label>
          <label className="field"><span>{pick("اولویت","Priority")}</span><input type="number" min={1} value={draft.priority} onChange={e=>setDraft(d=>({...d,priority:Math.max(1,Number(e.target.value)||1)}))}/></label>
        </div>
        {createStep&&<div className="runtime-warning">{createStep}</div>}
        <div className="modalActions"><button type="button" className="ghost" disabled={!!busy} onClick={()=>setCreateOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="create"||!draft.iran_node_id||!draft.exit_node_id}>{busy==="create"?pick("در حال ساخت…","Creating…"):pick("ساخت تانل","Create tunnel")}</button></div>
      </form>
    </Modal>}

    {manageOpen&&selected&&<Modal title={pick("مدیریت کامل تونل","Full tunnel management")} sub={`#${selected.id} · ${nodeMap.get(selected.iran_node_id)?.name||selected.iran_node_id} → ${nodeMap.get(selected.exit_node_id)?.name||selected.exit_node_id}`} onClose={()=>!busy&&setManageOpen(false)} wide>
      <div className="manage-card-section">
        <div className="manage-section-head"><div><b>{pick("وضعیت مسیر","Route status")}</b><small>{pick("وضعیت واقعی Backend و Transport فعال","Live backend status and active transport")}</small></div><button className="ghost" disabled={!!busy} onClick={()=>void act("health",pick("سلامت بروزرسانی شد","Health refreshed"),async()=>setHealth(await legacyControlApi.tunnelHealth(selected.id)))}>{busy==="health"?"…":pick("بررسی سلامت","Check health")}</button></div>
        <div className="legacy-detail-grid"><div><small>{pick("وضعیت","Status")}</small><b>{s(healthTunnel.status||selected.status)||"—"}</b></div><div><small>{pick("Ping","Ping")}</small><b dir="ltr">{n(healthTunnel.latency_ms||selected.latency_ms)?`${n(healthTunnel.latency_ms||selected.latency_ms)} ms`:"—"}</b></div><div><small>{pick("Transport فعال","Active transport")}</small><b dir="ltr">{transportLabel(healthTunnel.active_transport||selected.active_transport||selected.transport)}</b></div><div><small>{pick("حالت","Mode")}</small><b>{mode||"—"}</b></div></div>
      </div>

      <div className="manage-card-section">
        <div className="manage-section-head"><div><b>{pick("سه Transport تونل","Three tunnel transports")}</b><small>{pick("هر سه مستقل نصب می‌شوند؛ انتخاب دستی یکی، بقیه را حذف نمی‌کند","All three are installed independently; manual switching does not remove the others")}</small></div><button className="primary-soft" disabled={!!busy} onClick={()=>void installAllFromManage()}>{busy==="install-all"?"…":pick("نصب/بازسازی هر سه","Install/rebuild all")}</button></div>
        <div className="module-grid three">
          {normalizedTransports.map(item=>{
            const name=s(item.transport).toLowerCase() as TransportName;
            const isActive=s(healthTunnel.active_transport||selected.active_transport).toLowerCase()===name;
            const isPreferred=preferred===name;
            const usable=online(item.status)&&Boolean(item.enabled);
            return <div className="setting-box transport-runtime-card" key={name}>
              <div className="card-head"><div><b>{transportLabel(name)}</b><small>Priority {n(item.priority||transportPriority[name]).toLocaleString("fa-IR")}</small></div><Badge tone={online(item.status)?"ok":s(item.status).toLowerCase()==="installing"?"warn":"bad"}>{s(item.status)||"—"}</Badge></div>
              <div className="runtime-info-list"><div><span>{pick("نصب/فعال","Enabled")}</span><b>{Boolean(item.enabled)?pick("بله","Yes"):pick("خیر","No")}</b></div><div><span>{pick("Ping","Ping")}</span><b dir="ltr">{item.latency_ms==null?"—":`${n(item.latency_ms)} ms`}</b></div><div><span>{pick("فعال فعلی","Active")}</span><b>{isActive?pick("بله","Yes"):pick("خیر","No")}</b></div><div><span>{pick("ترجیحی","Preferred")}</span><b>{isPreferred?pick("بله","Yes"):pick("خیر","No")}</b></div></div>
              {s(item.last_error)&&<div className="runtime-error compact" dir="ltr">{s(item.last_error)}</div>}
              <div className="action-row"><button className={isActive?"primary":"primary-soft"} disabled={!!busy||!usable||isActive} onClick={()=>switchTransport(name)}>{busy===`switch-${name}`?"…":isActive?pick("در حال استفاده","In use"):pick("انتخاب دستی","Use manually")}</button><button className="ghost" disabled={!!busy} onClick={()=>install(name)}>{busy===`install-${name}`?"…":usable?pick("نصب مجدد","Reinstall"):pick("نصب","Install")}</button>{name==="mtunnel"&&<button className="ghost" disabled={!!busy} onClick={repairMtunnel}>{busy==="repair-mtunnel"?"…":pick("تعمیر","Repair")}</button>}</div>
            </div>;
          })}
        </div>
      </div>

      <div className="manage-card-section">
        <div className="manage-section-head"><div><b>{pick("حالت انتخاب Transport","Transport selection mode")}</b><small>{pick("Manual برای انتخاب دستی؛ Auto برای Failover خودکار بین Transportهای سالم","Manual for explicit selection; Auto for failover across healthy transports")}</small></div></div>
        <div className="setting-grid"><label className="field"><span>{pick("حالت","Mode")}</span><select value={mode} onChange={e=>setMode(e.target.value)}><option value="manual">Manual</option><option value="auto">Auto Failover</option></select></label><label className="field"><span>{pick("Transport دستی","Manual transport")}</span><select value={preferred} disabled={mode!=="manual"} onChange={e=>setPreferred(e.target.value as TransportName)}>{transportOrder.map(name=><option key={name} value={name}>{transportLabel(name)}</option>)}</select></label></div>
        <div className="action-row"><button className="primary-soft" disabled={!!busy} onClick={saveMode}>{busy==="mode"?"…":pick("ذخیره حالت","Save mode")}</button><button className="ghost" disabled={!!busy} onClick={prepare}>{busy==="prepare"?"…":pick("آماده‌سازی پایه","Base prepare")}</button></div>
      </div>

      <div className="modalActions"><button className="ghost" onClick={()=>setManageOpen(false)}>{pick("بستن","Close")}</button><button disabled={!!busy} onClick={()=>void toggle(selected)}>{selected.is_active?pick("غیرفعال کردن","Disable"):pick("فعال کردن","Enable")}</button><button className="danger" disabled={!!busy} onClick={()=>void remove(selected)}>{pick("حذف کامل تونل","Delete tunnel")}</button></div>
    </Modal>}
  </div></Shell>;
}
