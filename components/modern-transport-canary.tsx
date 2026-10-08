"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,AdminTunnel} from "../lib/admin-api";
import {
  ModernTransportName,
  ModernTransportState,
  TunnelTransportRow,
  tunnelTransportApi,
} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";

const labels:Record<ModernTransportName,string>={
  kernel_gre:"Kernel GRE",
  gost_tun:"GOST TUN / WSS",
  amneziawg:"AmneziaWG 3.1",
  netrix:"Netrix TUN",
};

const families:Record<ModernTransportName,string>={
  kernel_gre:"Kernel L3 / GRE",
  gost_tun:"TCP + WSS/TLS + TUN",
  amneziawg:"Obfuscated UDP / L3",
  netrix:"Licensed Multi-Path / L3",
};

const order:ModernTransportName[]=["kernel_gre","gost_tun","amneziawg","netrix"];
const value=(v:unknown)=>v===null||v===undefined||v===""?"—":String(v);
const online=(v:unknown)=>String(v??"").toLowerCase()==="online";
const pending=(v:unknown)=>["installing","testing","pending","not_installed"].includes(String(v??"").toLowerCase());
const tone=(v:unknown):"ok"|"warn"|"bad"=>online(v)?"ok":pending(v)?"warn":"bad";

function nodeLabel(node:AdminNode){
  const name=node.name||`#${node.id}`;
  const ip=node.public_ip?` · ${node.public_ip}`:"";
  return `${name}${ip}`;
}

export function ModernTransportCanaryPage(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [iranNodeId,setIranNodeId]=useState(0);
  const [exitNodeId,setExitNodeId]=useState(0);
  const [selected,setSelected]=useState(0);
  const [state,setState]=useState<ModernTransportState|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  const iranNodes=useMemo(
    ()=>nodes.filter(item=>String(item.node_type||"").toLowerCase()==="iran"),
    [nodes],
  );
  const exitNodes=useMemo(
    ()=>nodes.filter(item=>String(item.node_type||"").toLowerCase()==="exit"),
    [nodes],
  );

  const matchingTunnels=useMemo(
    ()=>tunnels.filter(item=>item.iran_node_id===iranNodeId&&item.exit_node_id===exitNodeId),
    [tunnels,iranNodeId,exitNodeId],
  );

  const selectedTunnel=useMemo(
    ()=>tunnels.find(item=>item.id===selected)||null,
    [tunnels,selected],
  );

  const loadData=async()=>{
    const [nodeRows,tunnelRows]=await Promise.all([adminApi.nodes(),adminApi.tunnels()]);
    setNodes(nodeRows);
    setTunnels(tunnelRows);

    const current=tunnelRows.find(item=>item.id===selected)||tunnelRows[0];
    if(current){
      setIranNodeId(current.iran_node_id);
      setExitNodeId(current.exit_node_id);
      setSelected(current.id);
      return;
    }

    const firstIran=nodeRows.find(item=>String(item.node_type||"").toLowerCase()==="iran");
    const firstExit=nodeRows.find(item=>String(item.node_type||"").toLowerCase()==="exit");
    setIranNodeId(firstIran?.id||0);
    setExitNodeId(firstExit?.id||0);
    setSelected(0);
  };

  const load=async(id:number,spinner=true)=>{
    if(!id){
      setState(null);
      if(spinner)setLoading(false);
      return;
    }
    if(spinner)setLoading(true);
    setError("");
    try{
      setState(await tunnelTransportApi.modernTransports(id));
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      if(spinner)setLoading(false);
    }
  };

  useEffect(()=>{
    (async()=>{
      setLoading(true);
      setError("");
      try{await loadData();}
      catch(e){setError(e instanceof Error?e.message:String(e));setLoading(false);}
    })();
  },[]);

  useEffect(()=>{
    if(!iranNodeId||!exitNodeId)return;
    const currentStillMatches=matchingTunnels.some(item=>item.id===selected);
    if(currentStillMatches)return;
    setSelected(matchingTunnels[0]?.id||0);
    setState(null);
  },[iranNodeId,exitNodeId,matchingTunnels,selected]);

  useEffect(()=>{void load(selected);},[selected]);

  const rows=useMemo(()=>{
    const source=Array.isArray(state?.transports)?state!.transports!:[];
    const map=new Map(source.map(item=>[String(item.transport),item]));
    return order.map(name=>map.get(name)||({
      transport:name,
      status:"not_installed",
      enabled:false,
      label:labels[name],
      family:families[name],
    } as TunnelTransportRow));
  },[state]);

  const onlineCount=rows.filter(row=>online(row.status)).length;

  const run=async(name:ModernTransportName,action:"install"|"remove")=>{
    if(!selected||busy)return;
    const key=`${action}-${name}`;
    const title=labels[name];
    const confirmText=action==="install"
      ?pick(
        `${title} روی تونل #${selected} نصب و تست شود؟ مسیر فعال کاربران تغییر نمی‌کند.`,
        `Install and test ${title} on tunnel #${selected}? The active user route will not change.`,
      )
      :pick(`${title} از تونل #${selected} پاک شود؟`,`Remove ${title} from tunnel #${selected}?`);
    if(!window.confirm(confirmText))return;

    setBusy(key);
    setError("");
    setMessage("");
    try{
      if(action==="install")await tunnelTransportApi.installModern(selected,name);
      else await tunnelTransportApi.removeModern(selected,name);
      await load(selected,false);
      setMessage(action==="install"
        ?pick(`${title} تست شد. وضعیت Online فقط بعد از عبور واقعی ترافیک ثبت می‌شود.`,`${title} was tested. Online is set only after real traffic passes.`)
        :pick(`${title} پاک شد.`,`${title} removed.`));
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
      await load(selected,false);
    }finally{
      setBusy("");
    }
  };

  const refresh=async()=>{
    if(busy)return;
    setLoading(true);
    setError("");
    try{
      await loadData();
      if(selected)await load(selected,false);
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      setLoading(false);
    }
  };

  return <Shell active="/admin/tunnels"><div className="page legacy-control-page modern-canary-page">
    <div className="page-head">
      <div>
        <h1>{pick("تست مسیرهای جایگزین تونل","Tunnel fallback tests")}</h1>
        <small>{pick("نود ایران و نود خروج را انتخاب کنید؛ تست‌ها روی همان جفت نود اجرا می‌شوند.","Choose Iran and exit nodes; tests run only on that node pair.")}</small>
      </div>
      <div className="action-row">
        <button className="ghost" disabled={loading||!!busy} onClick={()=>void refresh()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
        <button className="primary-soft" onClick={()=>window.location.href="/admin/tunnels"}>{pick("مدیریت تونل‌ها","Tunnel management")}</button>
      </div>
    </div>

    {error&&<div className="runtime-error" dir="auto">{error}</div>}
    {message&&<div className="runtime-success">{message}</div>}

    <Card>
      <div className="card-head">
        <div><b>{pick("مسیر تست","Test path")}</b><small>{pick("انتخاب نودها مستقل است و فقط تونل موجود بین همان دو نود تست می‌شود.","Node selection is independent and only an existing tunnel for that pair is tested.")}</small></div>
      </div>

      <div className="modern-canary-node-grid">
        <label className="field">
          <span>{pick("نود ایران","Iran node")}</span>
          <select value={iranNodeId} onChange={e=>setIranNodeId(Number(e.target.value))}>
            <option value={0}>{pick("انتخاب نود ایران","Select Iran node")}</option>
            {iranNodes.map(item=><option key={item.id} value={item.id}>{nodeLabel(item)}</option>)}
          </select>
        </label>

        <label className="field">
          <span>{pick("نود خروج","Exit node")}</span>
          <select value={exitNodeId} onChange={e=>setExitNodeId(Number(e.target.value))}>
            <option value={0}>{pick("انتخاب نود خروج","Select exit node")}</option>
            {exitNodes.map(item=><option key={item.id} value={item.id}>{nodeLabel(item)}</option>)}
          </select>
        </label>

        <label className="field">
          <span>{pick("تونل موجود","Existing tunnel")}</span>
          <select value={selected} onChange={e=>setSelected(Number(e.target.value))} disabled={!matchingTunnels.length}>
            {!matchingTunnels.length&&<option value={0}>{pick("تونلی برای این جفت نود وجود ندارد","No tunnel for this node pair")}</option>}
            {matchingTunnels.map(item=><option key={item.id} value={item.id}>#{item.id} · {item.status||"—"}</option>)}
          </select>
        </label>
      </div>

      {!matchingTunnels.length&&iranNodeId>0&&exitNodeId>0&&<div className="runtime-warning modern-canary-pair-warning">
        <span>{pick("بین این نود ایران و نود خروج هنوز تونلی ساخته نشده است.","No tunnel exists between these Iran and exit nodes yet.")}</span>
        <button className="ghost" onClick={()=>window.location.href="/admin/tunnels"}>{pick("ساخت تونل","Create tunnel")}</button>
      </div>}
    </Card>

    <div className="stats dashboard-stats modern-canary-stats">
      <Stat label={pick("مسیر Production","Production route")} value="Backhaul"/>
      <Stat label={pick("Transport فعال","Active transport")} value={value(state?.active_transport||selectedTunnel?.active_transport||selectedTunnel?.transport)}/>
      <Stat label={pick("تست موفق","Passed")} value={String(onlineCount)}/>
      <Stat label={pick("کاندیدا","Candidates")} value={String(order.length)}/>
    </div>

    <Card>
      <div className="card-head">
        <div>
          <b>{pick("Transportهای آزمایشی","Test transports")}</b>
          <small>{pick("Online فقط وقتی ثبت می‌شود که Interface، Peer Ping، TCP و UDP همگی عبور کنند.","Online is set only when interface, peer ping, TCP and UDP all pass.")}</small>
        </div>
        <Badge tone="warn">CANARY</Badge>
      </div>

      {!selected?<div className="runtime-empty">{pick("ابتدا نود ایران و نود خروج را انتخاب کنید و یک تونل موجود داشته باشید.","Select Iran and exit nodes and choose an existing tunnel first.")}</div>:
      loading?<div className="runtime-loading">{pick("در حال خواندن وضعیت…","Loading status…")}</div>:
      <div className="modern-canary-transport-grid">{rows.map(row=>{
        const name=String(row.transport) as ModernTransportName;
        const status=String(row.status||"not_installed");
        const runtime=(row.runtime&&typeof row.runtime==="object"?row.runtime:{}) as Record<string,unknown>;
        const installed=status!=="not_installed";
        return <article className="modern-canary-transport-card" key={name}>
          <div className="modern-canary-card-head">
            <div><b>{labels[name]}</b><small dir="ltr">{value(row.family||families[name])}</small></div>
            <Badge tone={tone(status)}>{status}</Badge>
          </div>

          <div className="modern-canary-meta">
            <div><span>{pick("Interface","Interface")}</span><b dir="ltr">{value(runtime.interface)}</b></div>
            <div><span>{pick("اولویت تست","Test priority")}</span><b>{value(row.priority)}</b></div>
            <div><span>{pick("Latency","Latency")}</span><b dir="ltr">{row.latency_ms==null?"—":`${row.latency_ms} ms`}</b></div>
            <div><span>{pick("Production","Production")}</span><b>{pick("خیر","No")}</b></div>
          </div>

          {row.last_error&&<div className="runtime-error compact modern-canary-error" dir="ltr">{String(row.last_error)}</div>}

          <div className="modern-canary-actions">
            <button className="primary-soft" disabled={!selected||!!busy} onClick={()=>void run(name,"install")}>{busy===`install-${name}`?"…":installed?pick("نصب مجدد و تست","Reinstall & test"):pick("نصب و تست","Install & test")}</button>
            <button className="ghost" disabled={!selected||!!busy||!installed} onClick={()=>void run(name,"remove")}>{busy===`remove-${name}`?"…":pick("پاک‌سازی","Remove")}</button>
          </div>

          {name==="netrix"&&<small className="muted modern-canary-note">{pick("نیازمند باینری و لایسنس معتبر Netrix است.","Requires a valid licensed Netrix binary.")}</small>}
        </article>;
      })}</div>}
    </Card>
  </div></Shell>;
}
