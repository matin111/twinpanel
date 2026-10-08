"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode} from "../lib/admin-api";
import {l2tpApi,L2tpSettings} from "../lib/l2tp-api";
import {useI18n} from "../lib/i18n";

function statusTone(status?:string):"ok"|"warn"|"bad"|"violet"{
  const value=String(status||"").toLowerCase();
  if(value==="online")return "ok";
  if(value==="maintenance")return "warn";
  return "bad";
}

export function L2tpSettingsPage(){
  const {pick}=useI18n();
  const [settings,setSettings]=useState<L2tpSettings|null>(null);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [psk,setPsk]=useState("");
  const [showPsk,setShowPsk]=useState(false);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [health,setHealth]=useState("");

  const load=async()=>{
    setError("");
    try{
      const [vpn,nodeRows]=await Promise.all([l2tpApi.settings(),adminApi.nodes()]);
      setSettings(vpn);
      setPsk(vpn.psk||"");
      setNodes(nodeRows);
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }
  };

  useEffect(()=>{void load();},[]);

  const l2tpNodes=useMemo(
    ()=>nodes.filter(node=>node.node_type==="exit"&&Boolean(node.enable_l2tp)),
    [nodes],
  );
  const onlineNodes=l2tpNodes.filter(node=>String(node.status||"").toLowerCase()==="online");
  const changed=Boolean(settings&&psk!==settings.psk);

  const generate=async()=>{
    if(busy)return;
    setBusy("generate");setError("");setOk("");
    try{
      const result=await l2tpApi.generate();
      setPsk(result.psk);
      setShowPsk(true);
      setOk(pick("Secret جدید ساخته شد؛ برای اعمال روی نودها ذخیره کنید.","A new secret was generated. Save it to sync enabled nodes."));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const save=async()=>{
    if(busy||!psk.trim())return;
    if(!window.confirm(pick("IPsec Secret روی تمام نودهای خروجی فعال L2TP همگام شود؟","Sync this IPsec secret to all L2TP-enabled exit nodes?")))return;
    setBusy("save");setError("");setOk("");
    try{
      const result=await l2tpApi.update(psk.trim());
      const count=result.synced_nodes?.length||0;
      setOk(result.changed
        ?pick(`Secret ذخیره و روی ${count.toLocaleString("fa-IR")} نود همگام شد.`,`Secret saved and synced to ${count} nodes.`)
        :pick("Secret تغییری نکرد.","Secret was unchanged."));
      await load();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const checkNode=async(node:AdminNode)=>{
    if(busy)return;
    setBusy(`health-${node.id}`);setError("");setOk("");setHealth("");
    try{
      const result=await adminApi.nodeProtocols(node.id);
      setHealth(JSON.stringify({node:{id:node.id,name:node.name,ip:node.public_ip},result},null,2));
      setOk(pick(`وضعیت پروتکل‌های ${node.name} دریافت شد.`,`Protocol status for ${node.name} loaded.`));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/l2tp"><div className="page">
    <div className="page-head"><div><h1>L2TP / IPsec</h1></div><button className="ghost" disabled={Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("نود L2TP","L2TP nodes")} value={String(l2tpNodes.length)} icon="▦"/>
      <Stat label={pick("آنلاین","Online")} value={String(onlineNodes.length)} icon="◉"/>
      <Stat label={pick("Secret","Secret")} value={settings?`${settings.length} ${pick("کاراکتر","chars")}`:"—"} icon="◎"/>
      <Stat label={pick("وضعیت","Status")} value={l2tpNodes.length?pick("آماده","Ready"):pick("بدون نود","No node")} icon="⌁"/>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("IPsec Secret","IPsec Secret")}</b><small>{pick("کلید مشترک واقعی تمام نودهای خروجی فعال L2TP","Shared secret used by all L2TP-enabled exit nodes")}</small></div>{changed?<Badge tone="warn">{pick("ذخیره نشده","Unsaved")}</Badge>:<Badge>{pick("همگام","Synced")}</Badge>}</div>

        <label className="field">
          <span>PSK</span>
          <div className="secret-field">
            <input
              dir="ltr"
              type={showPsk?"text":"password"}
              autoComplete="new-password"
              value={psk}
              maxLength={64}
              onChange={event=>setPsk(event.target.value)}
            />
            <button type="button" onClick={()=>setShowPsk(value=>!value)}>{showPsk?pick("مخفی","Hide"):pick("نمایش","Show")}</button>
          </div>
        </label>

        <div className="action-row">
          <button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void generate()}>{busy==="generate"?"…":pick("ساخت Secret امن","Generate secure secret")}</button>
          <button type="button" className="primary" disabled={Boolean(busy)||!psk.trim()||!changed} onClick={()=>void save()}>{busy==="save"?"…":pick("ذخیره و همگام‌سازی","Save & sync")}</button>
        </div>

        <div className="runtime-note">
          {pick("ذخیره Secret فقط زمانی موفق می‌شود که اعمال آن روی همه نودهای فعال L2TP موفق باشد؛ در خطا، Backend تغییر را Rollback می‌کند.","The secret is committed only if every enabled L2TP node is updated successfully; the backend rolls back on failure.")}
        </div>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("مدیریت سرویس","Service management")}</b><small>{pick("فعال یا غیرفعال کردن L2TP برای هر نود از بخش نودها انجام می‌شود.","Enable or disable L2TP per node from Nodes.")}</small></div></div>
        <div className="runtime-info-list">
          <div><span>{pick("نودهای Backend","Backend enabled nodes")}</span><b>{settings?.exit_count??0}</b></div>
          <div><span>{pick("نودهای پنل","Panel enabled nodes")}</span><b>{l2tpNodes.length}</b></div>
          <div><span>{pick("نود آنلاین","Online nodes")}</span><b>{onlineNodes.length}</b></div>
        </div>
        <div className="action-row"><Link className="primary" href="/admin/nodes">{pick("مدیریت نودها","Manage nodes")}</Link></div>
      </Card>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("وضعیت L2TP روی نودها","L2TP node status")}</b><small>{pick("فقط نودهای خروجی که L2TP برای آن‌ها فعال است نمایش داده می‌شوند.","Only exit nodes with L2TP enabled are shown.")}</small></div></div>
      {l2tpNodes.length?l2tpNodes.map(node=><div className="module-row" key={node.id}>
        <span className="module-icon">◎</span>
        <div className="grow"><b>{node.name}</b><small dir="ltr">{node.public_ip||"—"} · {node.country_code||"—"}</small></div>
        <Badge tone={statusTone(node.status)}>{node.status||"—"}</Badge>
        <button type="button" className="mini-btn" disabled={Boolean(busy)} onClick={()=>void checkNode(node)}>{busy===`health-${node.id}`?"…":pick("بررسی","Check")}</button>
      </div>):<div className="runtime-empty">{pick("هنوز روی هیچ نود خروجی L2TP فعال نشده است.","L2TP is not enabled on any exit node yet.")}</div>}
    </Card>

    {health&&<Card><div className="card-head"><b>{pick("نتیجه بررسی پروتکل","Protocol check result")}</b><button className="mini-btn" type="button" onClick={()=>setHealth("")}>×</button></div><pre className="runtime-log" dir="ltr">{health}</pre></Card>}
  </div></Shell>;
}
