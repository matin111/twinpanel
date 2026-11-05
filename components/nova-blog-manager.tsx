"use client";
import Link from "next/link";
import {useEffect,useRef,useState} from "react";
import {Shell} from "./ui";
import {NOVA_ARTICLES,novaEditableEntries,novaBlogImageMarker,safeNovaBlogImage,type NovaBlogEntry} from "../lib/nova-articles";
import {loadAdminStoreTemplateSettings,saveNovaBlogArticles,uploadStoreTemplateMedia} from "../lib/store-template-settings-api";
import styles from "./nova-blog-manager.module.css";

const TEMPLATE="nova-multipage-2027";
const blank=():NovaBlogEntry=>({slug:"",title:"",description:"",body:"",updated:new Date().toISOString().slice(0,10),published:false,coverImage:""});
function slugOf(input:string){return input.toLowerCase().normalize("NFKD").replace(/[^a-z0-9\s-]/g,"").trim().replace(/\s+/g,"-").replace(/-+/g,"-").slice(0,80).replace(/-$/,"");}
export function NovaBlogManager(){
 const [entries,setEntries]=useState<NovaBlogEntry[]>([]);
 const [current,setCurrent]=useState<NovaBlogEntry>(blank);
 const [originalSlug,setOriginalSlug]=useState("");
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState(false);
 const [uploading,setUploading]=useState<"cover"|"inline"|null>(null);
 const bodyRef=useRef<HTMLTextAreaElement|null>(null);
 const coverInputRef=useRef<HTMLInputElement|null>(null);
 const inlineInputRef=useRef<HTMLInputElement|null>(null);
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
 const uploadImage=async(file:File|undefined,target:"cover"|"inline")=>{
  if(!file)return;
  if(!["image/jpeg","image/png","image/webp"].includes(file.type)||file.size>8*1024*1024||file.size===0){
   setError("فرمت تصویر باید JPG، PNG یا WebP و حجم آن حداکثر ۸ مگابایت باشد.");return;
  }
  setUploading(target);setError("");setSuccess("");
  try{
   const slot="blog-"+crypto.randomUUID().replace(/-/g,"");
   const result=await uploadStoreTemplateMedia(TEMPLATE,slot,file);
   const url=safeNovaBlogImage(result.url);
   if(!url)throw new Error("نشانی تصویر آپلودشده معتبر نیست.");
   if(target==="cover"){
    setCurrent(x=>({...x,coverImage:url}));
   }else{
    const field=bodyRef.current;
    const pos=field?.selectionStart??current.body.length;
    const marker=novaBlogImageMarker(file.name.replace(/\.[^.]+$/,""),url);
    setCurrent(x=>{
     const point=Math.min(pos,x.body.length);
     const before=x.body.slice(0,point).replace(/\s*$/,"");
     const after=x.body.slice(point).replace(/^\s*/,"");
     return {...x,body:before+"\n\n"+marker+"\n\n"+after};
    });
   }
   setSuccess(target==="cover"?"تصویر شاخص بارگذاری شد. مقاله را ذخیره کنید.":"عکس در متن درج شد. مقاله را ذخیره کنید.");
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setUploading(null);}
 };
 const save=async()=>{
  const slug=slugOf(current.slug);
  const title=current.title.trim();
  const body=current.body.trim();
  if(uploading){setError("آپلود تصویر هنوز تمام نشده است.");return;}
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
   <div className={styles.sidebar} role="region" aria-label="فهرست مقاله‌ها"><div className={styles.sidebarHead}><strong>مقاله‌ها</strong><button type="button" onClick={create} disabled={busy}>+ مقاله جدید</button></div>
    {loading?<p>در حال دریافت مقاله‌ها…</p>:entries.length===0?<p>هنوز مقاله‌ای ثبت نشده است.</p>:entries.map(entry=><button type="button" className={originalSlug===entry.slug?styles.activeEntry:styles.entry} key={entry.slug} onClick={()=>select(entry)} disabled={busy}>
     <b>{entry.title}</b><small>{entry.published?"منتشر شده":"پیش‌نویس"} · {entry.updated}</small>
    </button>)}
   </div>
   <section className={styles.editor}><h2>{originalSlug?"ویرایش مقاله":"نوشتن مقاله جدید"}</h2>
    <label>عنوان مقاله<input maxLength={180} value={current.title} onChange={e=>setCurrent(x=>({...x,title:e.target.value}))} placeholder="مثلاً: آموزش استفاده از IP ثابت"/></label>
    <label>شناسه لاتین در آدرس سایت (Slug)<input dir="ltr" maxLength={80} value={current.slug} onChange={e=>setCurrent(x=>({...x,slug:e.target.value.toLowerCase()}))} placeholder="static-ip-guide"/></label>
    <label>توضیح کوتاه برای لیست بلاگ و گوگل<textarea maxLength={400} rows={3} value={current.description} onChange={e=>setCurrent(x=>({...x,description:e.target.value}))} placeholder="موضوع این مقاله چیست؟"/></label>
    <div className={styles.imageToolbar}>
      <button type="button" disabled={busy||uploading!==null} onClick={()=>inlineInputRef.current?.click()}>{uploading==="inline"?"در حال بارگذاری عکس…":"＋ افزودن عکس داخل متن"}</button>
      <button type="button" disabled={busy||uploading!==null} onClick={()=>coverInputRef.current?.click()}>{uploading==="cover"?"در حال بارگذاری عکس شاخص…":"▧ انتخاب تصویر شاخص"}</button>
      <small>JPG، PNG یا WebP · حداکثر ۸ مگابایت · محل درج عکس: جای نشانگر متن</small>
      <input ref={inlineInputRef} aria-label="بارگذاری عکس داخل متن" type="file" accept="image/jpeg,image/png,image/webp" className={styles.hiddenFile} onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value="";void uploadImage(file,"inline");}}/>
      <input ref={coverInputRef} aria-label="بارگذاری تصویر شاخص" type="file" accept="image/jpeg,image/png,image/webp" className={styles.hiddenFile} onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value="";void uploadImage(file,"cover");}}/>
    </div>
    {safeNovaBlogImage(current.coverImage)&&<div className={styles.coverPreview}><img src={current.coverImage} alt="تصویر شاخص مقاله" loading="lazy"/><button type="button" onClick={()=>setCurrent(x=>({...x,coverImage:""}))}>حذف تصویر شاخص</button></div>}
    <label>متن مقاله<textarea ref={bodyRef} rows={15} maxLength={5000} value={current.body} onChange={e=>setCurrent(x=>({...x,body:e.target.value}))} placeholder="متن مقاله را بنویسید؛ نشانگر را در محل موردنظر قرار دهید و دکمه افزودن عکس داخل متن را بزنید."/></label>
    <div className={styles.caption}>متن امن و عکس‌های بارگذاری‌شده (بدون HTML) · {current.body.length.toLocaleString("fa-IR")} از ۵۰۰۰ کاراکتر</div>
    <label className={styles.publish}><input type="checkbox" checked={current.published} onChange={e=>setCurrent(x=>({...x,published:e.target.checked}))}/> انتشار در سایت (در صورت خاموش بودن، پیش‌نویس باقی می‌ماند)</label>
    <div className={styles.actions}><button type="button" className="primary" disabled={busy||loading||uploading!==null} onClick={()=>void save()}>{busy?"در حال ذخیره…":"ذخیره مقاله"}</button>
    {originalSlug&&<button type="button" className="ghost" disabled={busy} onClick={()=>void remove()}>حذف مقاله</button>}
    {originalSlug&&current.published&&<Link className="ghost" href={`/vpn-blog/${originalSlug}`} target="_blank">نمایش مقاله ↗</Link>}</div>
   </section>
  </div>
  <p className={styles.note}>برای درج عکس، نشانگر را در محل موردنظر متن بگذارید و «افزودن عکس داخل متن» را بزنید؛ می‌توانید تصویر شاخص هم انتخاب کنید. محتوا برای قالب چهارم ذخیره می‌شود. مقاله‌های منتشرشده در بخش «وبلاگ» نمایش داده می‌شوند. انتشار، تنظیمات اشتراک و پرداخت را تغییر نمی‌دهد.</p>
 </div></Shell>;
}
