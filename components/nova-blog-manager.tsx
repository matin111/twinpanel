"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {Shell} from "./ui";
import {NOVA_ARTICLES,novaEditableEntries,type NovaBlogEntry} from "../lib/nova-articles";
import {loadAdminStoreTemplateSettings,saveNovaBlogArticles} from "../lib/store-template-settings-api";
import styles from "./nova-blog-manager.module.css";

const TEMPLATE="nova-multipage-2027";
const blank=():NovaBlogEntry=>({slug:"",title:"",description:"",body:"",updated:new Date().toISOString().slice(0,10),published:false});
function slugOf(input:string){return input.toLowerCase().normalize("NFKD").replace(/[^a-z0-9\s-]/g,"").trim().replace(/\s+/g,"-").replace(/-+/g,"-").slice(0,80).replace(/-$/,"");}
export function NovaBlogManager(){
 const [entries,setEntries]=useState<NovaBlogEntry[]>([]);
 const [current,setCurrent]=useState<NovaBlogEntry>(blank);
 const [originalSlug,setOriginalSlug]=useState("");
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [success,setSuccess]=useState("");
 const reload=async()=>{
  setLoading(true);setError("");
  try{
   const x=await loadAdminStoreTemplateSettings();
   setEntries(novaEditableEntries(x.templates?.[TEMPLATE]?.nova_articles));
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setLoading(false);}
 };
 useEffect(()=>{void reload();},[]);
 const select=(entry:NovaBlogEntry)=>{setCurrent({...entry});setOriginalSlug(entry.slug);setError("");setSuccess("");};
 const create=()=>{setCurrent(blank());setOriginalSlug("");setError("");setSuccess("");};
 const write=async(next:NovaBlogEntry[],message:string)=>{
  setBusy(true);setError("");setSuccess("");
  try{
   // Keep just explicit edits; original articles are included as editable entries
   // and saved as overrides only after the first editor save.
   await saveNovaBlogArticles(next);
   setEntries(next);
   setSuccess(message);
   return true;
  }catch(e){setError(e instanceof Error?e.message:String(e));return false;}
  finally{setBusy(false);}
 };
 const save=async()=>{
  const slug=slugOf(current.slug);
  const title=current.title.trim();
  const body=current.body.trim();
  if(!slug||!title||!body){setError("عنوان، شناسه لاتین مقاله و متن مقاله الزامی هستند.");return;}
  if(body.length>5000){setError("متن هر مقاله حداکثر ۵۰۰۰ کاراکتر است.");return;}
  if(entries.some(x=>x.slug===slug&&x.slug!==originalSlug)){setError("این شناسه مقاله قبلاً استفاده شده است.");return;}
  const updated={...current,slug,title,body,description:current.description.trim(),updated:new Date().toISOString().slice(0,10)};
  const next=entries.filter(x=>x.slug!==originalSlug).concat(updated);
  if(await write(next,updated.published?"مقاله منتشر و ذخیره شد.":"مقاله به‌عنوان پیش‌نویس ذخیره شد.")){
   setCurrent(updated);setOriginalSlug(updated.slug);
  }
 };
 const remove=async()=>{
  if(!originalSlug||!window.confirm("این نوشته حذف شود؟ این عملیات قابل بازگشت نیست."))return;
  const original=NOVA_ARTICLES.some(x=>x.slug===originalSlug);
  const next=original?entries.map(x=>x.slug===originalSlug?{...x,published:false}:x):entries.filter(x=>x.slug!==originalSlug);
  if(await write(next,original?"مقاله اولیه از سایت مخفی شد.":"مقاله حذف شد."))create();
 };
 return <Shell active="/admin/store-blog"><div className="page" dir="rtl">
  <div className="page-head"><div><h1>مدیریت بلاگ فروشگاه</h1><small>ثبت، ویرایش، پیش‌نویس و انتشار مقاله برای قالب چهارم</small></div>
  <div className="action-row"><Link className="ghost" href="/vpn-blog" target="_blank">مشاهده بلاگ ↗</Link><Link className="ghost" href="/admin/store-settings">تنظیمات فروشگاه</Link></div></div>
  {error&&<div className="runtime-error" role="alert">{error}</div>}
  {success&&<div className="runtime-success" role="status">{success}</div>}
  <div className={styles.layout}>
   <aside className={styles.sidebar}><div className={styles.sidebarHead}><strong>مقاله‌ها</strong><button type="button" onClick={create} disabled={busy}>+ مقاله جدید</button></div>
    {loading?<p>در حال دریافت مقاله‌ها…</p>:entries.length===0?<p>هنوز مقاله‌ای ثبت نشده است.</p>:entries.map(entry=><button type="button" className={originalSlug===entry.slug?styles.activeEntry:styles.entry} key={entry.slug} onClick={()=>select(entry)} disabled={busy}>
     <b>{entry.title}</b><small>{entry.published?"منتشر شده":"پیش‌نویس"} · {entry.updated}</small>
    </button>)}
   </aside>
   <section className={styles.editor}><h2>{originalSlug?"ویرایش مقاله":"نوشتن مقاله جدید"}</h2>
    <label>عنوان مقاله<input maxLength={180} value={current.title} onChange={e=>setCurrent(x=>({...x,title:e.target.value}))} placeholder="مثلاً: آموزش استفاده از IP ثابت"/></label>
    <label>شناسه لاتین در آدرس سایت (Slug)<input dir="ltr" maxLength={80} value={current.slug} onChange={e=>setCurrent(x=>({...x,slug:e.target.value.toLowerCase()}))} placeholder="static-ip-guide"/></label>
    <label>توضیح کوتاه برای لیست بلاگ و گوگل<textarea maxLength={400} rows={3} value={current.description} onChange={e=>setCurrent(x=>({...x,description:e.target.value}))} placeholder="موضوع این مقاله چیست؟"/></label>
    <label>متن مقاله<textarea rows={15} maxLength={5000} value={current.body} onChange={e=>setCurrent(x=>({...x,body:e.target.value}))} placeholder="متن کامل مقاله را بنویسید. برای پاراگراف جدید یک خط خالی بگذارید."/></label>
    <div className={styles.caption}>متن ساده و امن (بدون HTML) · {current.body.length.toLocaleString("fa-IR")} از ۵۰۰۰ کاراکتر</div>
    <label className={styles.publish}><input type="checkbox" checked={current.published} onChange={e=>setCurrent(x=>({...x,published:e.target.checked}))}/> انتشار در سایت (در صورت خاموش بودن، پیش‌نویس باقی می‌ماند)</label>
    <div className={styles.actions}><button type="button" className="primary" disabled={busy||loading} onClick={()=>void save()}>{busy?"در حال ذخیره…":"ذخیره مقاله"}</button>
    {originalSlug&&<button type="button" className="ghost" disabled={busy} onClick={()=>void remove()}>حذف مقاله</button>}
    {originalSlug&&current.published&&<Link className="ghost" href={`/vpn-blog/${originalSlug}`} target="_blank">نمایش مقاله ↗</Link>}</div>
   </section>
  </div>
  <p className={styles.note}>محتوای جدید برای قالب چهارم ذخیره می‌شود. مقاله‌های منتشرشده در بخش «وبلاگ» نمایش داده می‌شوند. انتشار، تنظیمات اشتراک و پرداخت را تغییر نمی‌دهد.</p>
 </div></Shell>;
}
