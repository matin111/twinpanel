"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {AdminNode,AdminTunnel} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const online=(value:unknown)=>s(value).toLowerCase()==="online";
const nodeType=(node:AdminNode)=>s(node.node_type).toLowerCase();

export function LegacyNetworkExactPage(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [selectedId,setSelectedId]=useState<number|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [nodeRows,tunnelRows]=await Promise.all([legacyControlApi.nodes(),legacyControlApi.tunnels()]);
      setNodes(nodeRows);setTunnels(tunnelRows);
      setSelectedId(current=>current&&tunnelRows.some(item=>item.id===current)?current:(tunnelRows[0]?.id??null));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),15000);return()=>window.clearInterval(timer);},[]);

  const nodeMap=useMemo(()=>new Map(nodes.map(item=>[item.id,item])),[nodes]);
  const iranNodes=nodes.filter(item=>nodeType(item)==="iran");
  const exitNodes=nodes.filter(item=>nodeType(item)==="exit");
  const onlineNodes=nodes.filter(item=>online(item.status)).length;
  const onlineTunnels=tunnels.filter(item=>online(item.status)).length;
  const selected=tunnels.find(item=>item.id===selectedId)||null;
  const selectedIran=selected?nodeMap.get(selected.iran_node_id):undefined;
  const selectedExit=selected?nodeMap.get(selected.exit_node_id):undefined;

  return <Shell active="/admin/network"><div className="page legacy-control-page">
    <div className="page-head"><div><h1>{pick("شبکه زنده","Live Network")}</h1><small>{pick("مسیرهای واقعی ایران به خروج و وضعیت لحظه‌ای آنها","Live Iran-to-exit paths and tunnel status")}</small></div><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("نودهای ایران","Iran nodes")} value={iranNodes.length.toLocaleString("fa-IR")}/>
      <Stat label={pick("نودهای خروج","Exit nodes")} value={exitNodes.length.toLocaleString("fa-IR")}/>
      <Stat label={pick("نود آنلاین","Online nodes")} value={`${onlineNodes.toLocaleString("fa-IR")} / ${nodes.length.toLocaleString("fa-IR")}`}/>
      <Stat label={pick("تانل آنلاین","Online tunnels")} value={`${onlineTunnels.toLocaleString("fa-IR")} / ${tunnels.length.toLocaleString("fa-IR")}`}/>
    </div>

    <div className="legacy-network-layout">
      <Card className="legacy-network-topology">
        <div className="card-head"><div><b>{pick("مسیرها","Paths")}</b><small>{pick("برای مشاهده جزئیات روی یک مسیر بزنید","Select a path to inspect it")}</small></div></div>
        <div className="legacy-path-list">
          {tunnels.map(tunnel=>{
            const iran=nodeMap.get(tunnel.iran_node_id);const exit=nodeMap.get(tunnel.exit_node_id);const active=tunnel.id===selectedId;
            return <button type="button" key={tunnel.id} className={`legacy-path-card ${active?"active":""}`} onClick={()=>setSelectedId(tunnel.id)}>
              <div className="legacy-path-node"><span className={`status-dot ${online(iran?.status)?"online":"offline"}`}/><div><b>{iran?.name||`Iran #${tunnel.iran_node_id}`}</b><small dir="ltr">{iran?.public_ip||"—"}</small></div></div>
              <div className="legacy-path-line"><span>{tunnel.transport||"—"}</span><i>→</i><small>{tunnel.latency_ms==null?"—":`${tunnel.latency_ms} ms`}</small></div>
              <div className="legacy-path-node"><span className={`status-dot ${online(exit?.status)?"online":"offline"}`}/><div><b>{exit?.name||`Exit #${tunnel.exit_node_id}`}</b><small dir="ltr">{exit?.public_ip||"—"}</small></div></div>
              <Badge tone={online(tunnel.status)?"ok":"warn"}>{s(tunnel.status)||"—"}</Badge>
            </button>;
          })}
          {!tunnels.length&&!loading&&<div className="runtime-empty">{pick("تانلی ثبت نشده است","No tunnels registered")}</div>}
        </div>
      </Card>

      <Card className="legacy-network-detail">
        <div className="card-head"><div><b>{pick("جزئیات مسیر","Path details")}</b><small>{selected?`#${selected.id}`:"—"}</small></div>{selected&&<Badge tone={online(selected.status)?"ok":"warn"}>{s(selected.status)||"—"}</Badge>}</div>
        {!selected?<div className="runtime-empty">{pick("یک مسیر انتخاب کنید","Select a path")}</div>:<>
          <div className="legacy-detail-grid">
            <div><small>{pick("نود ایران","Iran node")}</small><b>{selectedIran?.name||`#${selected.iran_node_id}`}</b><code dir="ltr">{selectedIran?.public_ip||"—"}</code></div>
            <div><small>{pick("نود خروج","Exit node")}</small><b>{selectedExit?.name||`#${selected.exit_node_id}`}</b><code dir="ltr">{selectedExit?.public_ip||"—"}</code></div>
            <div><small>{pick("Transport","Transport")}</small><b dir="ltr">{selected.transport||"—"}</b></div>
            <div><small>{pick("Ping","Ping")}</small><b dir="ltr">{selected.latency_ms==null?"—":`${selected.latency_ms} ms`}</b></div>
            <div><small>{pick("اولویت","Priority")}</small><b>{n(selected.priority).toLocaleString("fa-IR")}</b></div>
            <div><small>{pick("وضعیت اجرا","Enabled")}</small><b>{selected.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</b></div>
          </div>
          <div className="legacy-node-pair">
            <div className="setting-box"><div className="card-head"><b>{selectedIran?.name||pick("نود ایران","Iran node")}</b><Badge tone={online(selectedIran?.status)?"ok":"bad"}>{s(selectedIran?.status)||"—"}</Badge></div><small>{pick("کاربران فعلی","Current users")}</small><b>{n(selectedIran?.current_users).toLocaleString("fa-IR")} / {n(selectedIran?.capacity_users).toLocaleString("fa-IR")}</b></div>
            <div className="setting-box"><div className="card-head"><b>{selectedExit?.name||pick("نود خروج","Exit node")}</b><Badge tone={online(selectedExit?.status)?"ok":"bad"}>{s(selectedExit?.status)||"—"}</Badge></div><small>{pick("کاربران فعلی","Current users")}</small><b>{n(selectedExit?.current_users).toLocaleString("fa-IR")} / {n(selectedExit?.capacity_users).toLocaleString("fa-IR")}</b></div>
          </div>
        </>}
      </Card>
    </div>
  </div></Shell>;
}
