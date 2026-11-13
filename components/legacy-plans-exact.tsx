"use client";

/*
 * Plan snapshot contract (kept explicit for compatibility guards):
 * Iran nodes are tunnel-only.
 * Exit nodes remain part of tunnel routing and customer account selection.
 * Plan create/update selected node ids are snapshotted onto subscriptions.
 * Selected protocols are snapshotted onto subscriptions.
 */

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import styles from "./compact-plan-modal.module.css";
import {Badge,Card,Shell} from "./ui";
import {adminApi,RuntimeRow} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const parsed=Number(value??0);return Number.isFinite(parsed)?parsed:0;};
const stringList=(value:unknown)=>Array.isArray(value)?value.map(item=>String(item)).filter(Boolean):[];
const numberList=(value:unknown)=>Array.isArray(value)?value.map(item=>Number(item)).filter(item=>Number.isFinite(item)&&item>0):[];

const PROTOCOLS=[
  ["cisco","Cisco / OpenConnect"],["openvpn","OpenVPN"],["wireguard","WireGuard"],["l2tp","L2TP / IPsec"],["v2ray","V2Ray / Xray"],
  ["hysteria2","Hysteria2"],["tuic","TUIC"],["anytls","AnyTLS"],["naive","NaiveProxy"],["shadowtls","ShadowTLS"],
  ["snell","Snell"],["mieru","Mieru"],["trusttunnel","TrustTunnel"],["amneziawg","AmneziaWG"],["sudoku","Sudoku"],["socks5","SOCKS5 Proxy"],
] as const;
const ALL_PROTOCOLS=PROTOCOLS.map(([key])=>key);

type PlanDraft={name:string;category:string;subscription_type:string;description:string;duration_days:number;traffic_gb:number;device_limit:number;price_toman:number;is_active:boolean;protocols:string[];node_ids:number[];};
const EMPTY_DRAFT:PlanDraft={name:"",category:"",subscription_type:"اشتراک عمومی",description:"",duration_days:30,traffic_gb:50,device_limit:1,price_toman:0,is_active:true,protocols:[...ALL_PROTOCOLS],node_ids:[]};

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Check({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}){return <label className="toggle module-toggle compact-toggle"><span>{label}</span><input type="checkbox" checked={checked} onChange={event=>onChange(event.target.checked)}/><i/></label>;}

export function LegacyPlansRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);const [nodes,setNodes]=useState<RuntimeRow[]>([]);const [q,setQ]=useState("");const [busy,setBusy]=useState("");const [error,setError]=useState("");const [ok,setOk]=useState("");const [editing,setEditing]=useState<RuntimeRow|null>(null);const [open,setOpen]=useState(false);const [draft,setDraft]=useState<PlanDraft>({...EMPTY_DRAFT});const basicRef=useRef<HTMLElement>(null);const pricingRef=useRef<HTMLElement>(null);const protocolsRef=useRef<HTMLElement>(null);const [activeSection,setActiveSection]=useState<"basic"|"pricing"|"protocols">("basic");
  const load=async()=>{setError("");try{const [planRows,nodeRows]=await Promise.all([adminApi.plans(),adminApi.nodes()]);setRows(planRows);setNodes(nodeRows as unknown as RuntimeRow[]);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  useEffect(()=>{void load();},[]);
  const exitNodes=useMemo(()=>nodes.filter(row=>s(row.node_type).trim().toLowerCase()==="exit"),[nodes]);const allNodeIds=useMemo(()=>exitNodes.map(row=>n(row.id)).filter(Boolean),[exitNodes]);const nodeNameById=useMemo(()=>new Map(exitNodes.map(row=>[n(row.id),s(row.name)||`#${n(row.id)}`])),[exitNodes]);const categoryOptions=useMemo(()=>Array.from(new Set(rows.map(row=>s(row.category).trim()).filter(Boolean))),[rows]);
  const subscriptionTypeOptions=useMemo(()=>Array.from(new Set(rows.map(row=>s(row.subscription_type).trim()).filter(Boolean))),[rows]);const filtered=useMemo(()=>{const value=q.trim().toLowerCase();return value?rows.filter(row=>`${row.id??""} ${row.name??""} ${row.category??""} ${row.subscription_type??""} ${row.description??""}`.toLowerCase().includes(value)):rows;},[rows,q]);
  const start=(row?:RuntimeRow)=>{if(row){setEditing(row);const protocols=stringList(row.protocols);const nodeIds=numberList(row.node_ids);const allowedNodeIds=nodeIds.filter(id=>allNodeIds.includes(id));setDraft({name:s(row.name),category:s(row.category),subscription_type:s(row.subscription_type)||"اشتراک عمومی",description:s(row.description),duration_days:n(row.duration_days)||30,traffic_gb:n(row.traffic_gb),device_limit:row.device_limit==null?1:n(row.device_limit),price_toman:n(row.price_toman),is_active:Boolean(row.is_active),protocols:protocols.length?protocols:[...ALL_PROTOCOLS],node_ids:allowedNodeIds.length?allowedNodeIds:[...allNodeIds]});}else{setEditing(null);setDraft({...EMPTY_DRAFT,protocols:[...ALL_PROTOCOLS],node_ids:[...allNodeIds]});}setActiveSection("basic");setOpen(true);};
  const toggleProtocol=(protocol:string,checked:boolean)=>setDraft(current=>({...current,protocols:checked?Array.from(new Set([...current.protocols,protocol])):current.protocols.filter(value=>value!==protocol)}));
  const toggleNode=(nodeId:number,checked:boolean)=>setDraft(current=>({...current,node_ids:checked?Array.from(new Set([...current.node_ids,nodeId])):current.node_ids.filter(value=>value!==nodeId)}));
  const movePlan=async(id:number,direction:-1|1)=>{if(busy||q.trim())return;const ordered=rows.map(row=>n(row.id)).filter(Boolean);const from=ordered.indexOf(id);const to=from+direction;if(from<0||to<0||to>=ordered.length)return;const next=[...ordered];[next[from],next[to]]=[next[to],next[from]];setBusy(`order:${id}`);setError("");setOk("");try{await adminApi.reorderPlans(next);setOk(pick("ترتیب نمایش ذخیره شد","Display order saved"));await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};
  const save=async(event:FormEvent)=>{event.preventDefault();if(busy)return;if(!draft.protocols.length){setError(pick("حداقل یک پروتکل را انتخاب کنید","Select at least one protocol"));return;}if(!draft.node_ids.length){setError(pick("حداقل یک سرور خارج را انتخاب کنید","Select at least one exit server"));return;}setBusy("save");setError("");setOk("");try{if(editing)await adminApi.updatePlan(n(editing.id),draft as unknown as RuntimeRow);else await adminApi.createPlan(draft as unknown as RuntimeRow);setOk(editing?pick("پلن ویرایش شد","Plan updated"):pick("پلن ساخته شد","Plan created"));setOpen(false);await load();}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};

  return <Shell active="/admin/plans"><div className="page legacy-plans-page">
    <div className="page-head"><div><h1>{pick("پلن‌ها","Plans")}</h1><small>{pick("مدیریت دسته‌بندی، چیدمان، پلن‌های فروش، پروتکل‌ها و سرورهای مجاز.","Manage categories, ordering, sales plans, protocols and allowed servers.")}</small></div><button className="primary" onClick={()=>start()}>＋ {pick("پلن جدید","New plan")}</button></div>
    <Notice error={error} ok={ok}/>
    <Card><div className="runtime-toolbar"><label>⌕ <input value={q} onChange={event=>setQ(event.target.value)} placeholder={pick("جستجوی پلن…","Search plans…")}/></label><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
      <div className="table"><table><thead><tr><th>{pick("چیدمان","Order")}</th><th>{pick("پلن","Plan")}</th><th>{pick("نوع اشتراک","Subscription type")}</th><th>{pick("دسته‌بندی","Category")}</th><th>{pick("مدت","Duration")}</th><th>{pick("حجم","Traffic")}</th><th>{pick("پروتکل‌ها","Protocols")}</th><th>{pick("سرورهای خارج","Exit servers")}</th><th>{pick("قیمت","Price")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(row=>{const id=n(row.id);const protocols=stringList(row.protocols);const nodeIds=numberList(row.node_ids);const rowIndex=rows.findIndex(item=>n(item.id)===id);return <tr key={s(row.id)}><td><div className="row-actions"><button type="button" disabled={!!q.trim()||rowIndex<=0||!!busy} title={pick("انتقال به بالا","Move up")} onClick={()=>void movePlan(id,-1)}>↑</button><button type="button" disabled={!!q.trim()||rowIndex<0||rowIndex>=rows.length-1||!!busy} title={pick("انتقال به پایین","Move down")} onClick={()=>void movePlan(id,1)}>↓</button></div></td><td><b>{s(row.name)}</b><small>{s(row.description)}</small></td><td><Badge tone="violet">{s(row.subscription_type)||pick("اشتراک عمومی","General subscription")}</Badge></td><td><Badge tone="violet">{s(row.category)||pick("سایر پلن‌ها","Other plans")}</Badge></td><td>{n(row.duration_days)} {pick("روز","days")}</td><td>{n(row.traffic_gb)} GB · {n(row.device_limit)===0?pick("کاربر نامحدود","Unlimited users"):`${n(row.device_limit)} ${pick("دستگاه","devices")}`}</td><td><b>{protocols.length||15}/15</b><small>{protocols.slice(0,4).join(" · ")}{protocols.length>4?" …":""}</small></td><td><b>{nodeIds.length||allNodeIds.length}</b><small>{nodeIds.slice(0,3).map(nodeId=>nodeNameById.get(nodeId)||`#${nodeId}`).join(" · ")}{nodeIds.length>3?" …":""}</small></td><td>{n(row.price_toman).toLocaleString("fa-IR")} {pick("تومان","Toman")}</td><td><Badge tone={row.is_active?"ok":"bad"}>{row.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td><td><div className="row-actions"><button onClick={()=>start(row)}>{pick("ویرایش","Edit")}</button><button className="danger" onClick={()=>{if(window.confirm(pick("پلن برای همیشه حذف شود؟","Delete this plan permanently?")))void adminApi.deletePlan(id).then(load).catch(reason=>setError(reason instanceof Error?reason.message:String(reason)));}}>{pick("حذف","Delete")}</button></div></td></tr>;})}</tbody></table></div>
    </Card>
    {open&&<div className={styles.overlay} dir="rtl">
      <button type="button" className={styles.scrim} aria-label={pick("بستن پنجره","Close dialog")} onClick={()=>setOpen(false)}/>
      <form className={styles.dialog} aria-label={editing?pick("ویرایش پلن","Edit plan"):pick("پلن جدید","New plan")} onSubmit={save}>
        <header className={styles.header}>
          <div className={styles.heading}><span className={styles.symbol} aria-hidden="true">▧</span><div>
            <b>{editing?pick("ویرایش پلن","Edit plan"):pick("پلن جدید","New plan")}</b>
            <small>{pick("اطلاعات، حجم و دسترسی‌های پلن را تنظیم کنید.","Configure plan details, pricing and access.")}</small>
          </div></div>
          <button type="button" className={styles.close} aria-label={pick("بستن","Close")} onClick={()=>setOpen(false)}>×</button>
        </header>
        <nav className={styles.steps} aria-label={pick("بخش‌های فرم","Form sections")}>
          {([
            ["basic",pick("ⓘ اطلاعات پایه","ⓘ Basic info"),basicRef],
            ["pricing",pick("▤ حجم و قیمت","▤ Volume & price"),pricingRef],
            ["protocols",pick("♧ پروتکل‌ها و نودها","♧ Protocols & nodes"),protocolsRef],
          ] as const).map(([key,title,ref])=><button key={key} type="button" className={`${styles.step} ${activeSection===key?styles.stepCurrent:""}`} onClick={()=>{setActiveSection(key);ref.current?.scrollIntoView({behavior:"smooth",block:"nearest"});}}>{title}</button>)}
        </nav>
        <div className={styles.body}>
          <section ref={basicRef} className={styles.section} aria-label={pick("اطلاعات پایه","Basic information")}>
            <div className={styles.sectionTop}><b className={styles.sectionTitle}>{pick("اطلاعات پایه","Basic information")}</b></div>
            <div className={styles.formGrid}>
              <label className={styles.field}><span>{pick("نام پلن *","Plan name *")}</span><input required maxLength={150} value={draft.name} onChange={event=>setDraft(current=>({...current,name:event.target.value}))} placeholder={pick("مثلاً اقتصادی، ویژه، گیمینگ","e.g. Economy, Premium, Gaming")}/></label>
              <label className={styles.field}><span>{pick("نوع اشتراک (مرحله اول خرید)","Subscription type (first choice)")}</span><input list="subscription-type-options" maxLength={120} value={draft.subscription_type} onChange={event=>setDraft(current=>({...current,subscription_type:event.target.value}))} placeholder={pick("اشتراک عمومی","General subscription")}/><datalist id="subscription-type-options">{subscriptionTypeOptions.map(type=><option key={type} value={type}/>)}</datalist></label>
              <label className={styles.field}><span>{pick("دسته‌بندی پلن","Plan category")}</span><input list="plan-category-options" maxLength={120} value={draft.category} onChange={event=>setDraft(current=>({...current,category:event.target.value}))} placeholder={pick("مثلاً اقتصادی، ویژه، گیمینگ","e.g. Economy, Premium, Gaming")}/><datalist id="plan-category-options">{categoryOptions.map(category=><option key={category} value={category}/>)}</datalist></label>
              <label className={styles.field}><span>{pick("توضیحات","Description")}</span><input value={draft.description} onChange={event=>setDraft(current=>({...current,description:event.target.value}))} placeholder={pick("توضیحات کوتاه اختیاری","Optional short description")}/></label>
            </div>
          </section>
          <section ref={pricingRef} className={styles.section} aria-label={pick("حجم و قیمت","Volume and pricing")}>
            <div className={styles.sectionTop}><b className={styles.sectionTitle}>{pick("▤ حجم و قیمت","▤ Volume & pricing")}</b></div>
            <div className={styles.moneyGrid}>
              <label className={styles.field}><span>{pick("مدت (روز)","Duration (days)")}</span><input type="number" min={1} required value={draft.duration_days} onChange={event=>setDraft(current=>({...current,duration_days:Number(event.target.value)}))}/></label>
              <label className={styles.field}><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={0} required value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:Number(event.target.value)}))}/></label>
              <label className={styles.field}><span>{pick("قیمت تومان","Price (Toman)")}</span><input type="number" min={0} required value={draft.price_toman} onChange={event=>setDraft(current=>({...current,price_toman:Number(event.target.value)}))}/></label>
              <label className={styles.field}><span>{pick("تعداد کاربر (۰ = نامحدود)","Users (0 = unlimited)")}</span><input type="number" min={0} required value={draft.device_limit} onChange={event=>setDraft(current=>({...current,device_limit:Number(event.target.value)}))}/></label>
            </div>
          </section>
          <section ref={protocolsRef} className={styles.section} aria-label={pick("پروتکل‌ها و نودهای مجاز","Allowed protocols and nodes")}>
            <div className={styles.sectionTop}>
              <div><b className={styles.sectionTitle}>{pick("پروتکل‌ها و نودهای مجاز","Allowed protocols and exit nodes")}</b>
              <div className={styles.sectionDescription}>{pick("پروتکل‌ها و سرورهای قابل استفاده در این پلن را جداگانه انتخاب کنید.","Choose enabled protocols and exit servers for this plan.")}</div></div>
            </div>
            <div className={styles.selectionLayout}>
              <div className={styles.selectionColumn}>
                <div className={styles.sectionTop}>
                  <b className={styles.sectionTitle}>{pick("پروتکل‌ها","Protocols")}</b>
                  <div className={styles.selectionActions}><span className={styles.selectionCount}>{draft.protocols.length}/{PROTOCOLS.length}</span>
                    <button type="button" className={styles.smallBtn} onClick={()=>setDraft(current=>({...current,protocols:[...ALL_PROTOCOLS]}))}>{pick("انتخاب همه","Select all")}</button>
                  </div>
                </div>
                <div className={styles.pills}>
                  {PROTOCOLS.map(([key,label])=><label key={key} className={`${styles.pill} ${draft.protocols.includes(key)?styles.pillSelected:""}`}><span>{label}</span><input type="checkbox" checked={draft.protocols.includes(key)} onChange={event=>toggleProtocol(key,event.target.checked)}/></label>)}
                </div>
              </div>
              <div className={styles.selectionColumn}>
                <div className={styles.sectionTop}>
                  <b className={styles.sectionTitle}>{pick("انتخاب نودهای خارج (Exit)","Select Exit nodes")}</b>
                  <div className={styles.selectionActions}><span className={styles.selectionCount}>{draft.node_ids.length}/{exitNodes.length}</span>
                    <button type="button" className={styles.smallBtn} onClick={()=>setDraft(current=>({...current,node_ids:[...allNodeIds]}))}>{pick("انتخاب همه","Select all")}</button>
                  </div>
                </div>
                {exitNodes.length>0
                  ?<div className={styles.pills} aria-label={pick("انتخاب نودها","Select nodes")}>
                    {exitNodes.map(row=>{const nodeId=n(row.id);return <label key={nodeId} className={`${styles.pill} ${draft.node_ids.includes(nodeId)?styles.pillSelected:""}`} title={s(row.name)}>
                      <span>{s(row.name)||`#${nodeId}`} · {s(row.country_code)}</span>
                      <input type="checkbox" checked={draft.node_ids.includes(nodeId)} onChange={event=>toggleNode(nodeId,event.target.checked)}/>
                    </label>;})}
                   </div>
                  :<div className={styles.emptyNodes}>{pick("نود خروجی موجود نیست؛ فهرست نودها را بررسی کنید.","No Exit nodes available. Check the node inventory.")}</div>}
                <small className={styles.nodeHint}>{pick("تنها نودهای خروجی انتخاب‌شده به اشتراک اضافه می‌شوند.","Only selected Exit nodes are snapshotted onto subscriptions.")}</small>
              </div>
            </div>
          </section>
          <label className={styles.activeCheck}><input type="checkbox" checked={draft.is_active} onChange={event=>setDraft(current=>({...current,is_active:event.target.checked}))}/>{pick("پلن فعال و منتشر شده باشد","Keep plan active and published")}</label>
        </div>
        <footer className={styles.footer}>
          <div className={styles.buttons}><button type="submit" className={styles.save} disabled={!!busy}>{busy?pick("در حال ذخیره…","Saving…"):pick("✓ ذخیره پلن","✓ Save plan")}</button><button type="button" className={styles.cancel} onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button></div>
          {error&&<div className={styles.error} role="alert">{error}</div>}
        </footer>
      </form>
    </div>}
  </div></Shell>;
}