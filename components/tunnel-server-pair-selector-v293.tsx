"use client";

import {type FormEvent,useMemo,useState} from "react";

import styles from "./tunnel-control-center-v1.module.css";
import type {AdminNode,AdminTunnel} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {tunnelServerPairApi} from "../lib/tunnel-server-pair-api";
import {useI18n} from "../lib/i18n";

// TWINPANEL_SERVER_PAIR_SELECTOR_UI_V293
// Select/reuse a logical server pair without provisioning any transport.

type Draft={iran_node_id:number;exit_node_id:number;priority:number};

const normalized=(value:unknown)=>String(value??"").trim().toLowerCase();
const nodeLabel=(node:AdminNode)=>`${node.name} · ${node.public_ip||"—"}`;

export function TunnelServerPairSelectorV293({disabled=false,onSelected}:{disabled?:boolean;onSelected:(tunnel:AdminTunnel)=>void}){
  const {pick}=useI18n();
  const [open,setOpen]=useState(false);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [draft,setDraft]=useState<Draft>({iran_node_id:0,exit_node_id:0,priority:100});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");

  const iranNodes=useMemo(()=>nodes.filter(node=>normalized(node.node_type)==="iran"),[nodes]);
  const exitNodes=useMemo(()=>nodes.filter(node=>normalized(node.node_type)==="exit"),[nodes]);

  const openSelector=async()=>{
    if(disabled||busy)return;
    setBusy(true);setError("");
    try{
      const rows=await legacyControlApi.nodes();
      setNodes(rows);
      const iran=rows.find(node=>normalized(node.node_type)==="iran"&&normalized(node.status)==="online")||rows.find(node=>normalized(node.node_type)==="iran");
      const exit=rows.find(node=>normalized(node.node_type)==="exit"&&normalized(node.status)==="online")||rows.find(node=>normalized(node.node_type)==="exit");
      setDraft({iran_node_id:iran?.id||0,exit_node_id:exit?.id||0,priority:100});
      setOpen(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy||!draft.iran_node_id||!draft.exit_node_id)return;
    setBusy(true);setError("");
    try{
      const tunnel=await tunnelServerPairApi.select(draft);
      if(!Number(tunnel?.id||0))throw new Error(pick("پاسخ انتخاب سرور معتبر نبود.","Server pair selection returned no tunnel ID."));
      onSelected(tunnel);
      setOpen(false);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  return <>
    <button type="button" className={styles.secondaryButton} disabled={disabled||busy} onClick={()=>void openSelector()}>{busy?"…":`⇄ ${pick("انتخاب سرور","Select servers")}`}</button>
    {open&&<div className={styles.modal} role="dialog" aria-modal="true">
      <button type="button" className={styles.modalBackdrop} aria-label="close" onClick={()=>!busy&&setOpen(false)}/>
      <div className={styles.modalCard}>
        <div className={styles.modalHead}><b>{pick("انتخاب سرور بدون نصب مجدد","Select servers without reinstall")}</b><button type="button" className={styles.iconButton} disabled={busy} onClick={()=>setOpen(false)}>×</button></div>
        <form className={styles.createForm} onSubmit={submit}>
          <div className={styles.createIntro}>
            <b>{pick("فقط انتخاب Pair منطقی","Logical pair selection only")}</b>
            <p>{pick("این عملیات فقط سرور ایران و خروجی را ثبت یا Pair موجود را انتخاب می‌کند. هیچ Tunnel/Transport، Agent، WireGuard، SSH یا Firewall نصب یا بازسازی نمی‌شود.","This only registers the Iran/Exit logical pair or reuses the existing pair. It does not install or rebuild any tunnel, transport, agent, WireGuard, SSH, or firewall runtime.")}</p>
          </div>
          {error&&<div className={`${styles.notice} ${styles.noticeBad}`}>{error}</div>}
          <label><span>{pick("سرور ایران","Iran server")}</span><select value={draft.iran_node_id} onChange={event=>setDraft(value=>({...value,iran_node_id:Number(event.target.value)}))}>{iranNodes.map(node=><option key={node.id} value={node.id}>{nodeLabel(node)} · {node.status||"—"}</option>)}</select></label>
          <div className={styles.flowArrow}>↓</div>
          <label><span>{pick("سرور خروجی","Exit server")}</span><select value={draft.exit_node_id} onChange={event=>setDraft(value=>({...value,exit_node_id:Number(event.target.value)}))}>{exitNodes.map(node=><option key={node.id} value={node.id}>{nodeLabel(node)} · {node.status||"—"}</option>)}</select></label>
          <label><span>{pick("اولویت","Priority")}</span><input type="number" min={1} max={9999} value={draft.priority} onChange={event=>setDraft(value=>({...value,priority:Number(event.target.value)||100}))}/></label>
          <div className={styles.createFooter}><button type="button" className={styles.secondaryButton} disabled={busy} onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button><button type="submit" className={styles.primaryButton} disabled={busy||!draft.iran_node_id||!draft.exit_node_id}>{busy?pick("در حال انتخاب...","Selecting..."):pick("انتخاب / ثبت Pair","Select / register pair")}</button></div>
        </form>
      </div>
    </div>}
  </>;
}
