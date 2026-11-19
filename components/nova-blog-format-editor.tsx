"use client";

import {useState,type RefObject,type KeyboardEvent} from "react";
import {NOVA_BLOG_BODY_LIMIT,NOVA_FONT_SIZES,NOVA_TEXT_COLORS,safeNovaBlogAnchor,safeNovaBlogHref} from "../lib/nova-blog-rich-text";
import {NovaBlogRichText} from "./nova-blog-rich-text";
import styles from "./nova-blog-format-editor.module.css";

type View="write"|"split"|"preview";
type Props={body:string;onChange:(value:string)=>void;textareaRef:RefObject<HTMLTextAreaElement|null>;disabled?:boolean};
const paletteLabels:Record<string,string>={default:"رنگ عادی",blue:"آبی",purple:"بنفش",green:"سبز",orange:"نارنجی",red:"قرمز"};

export function NovaBlogFormatEditor({body,onChange,textareaRef,disabled=false}:Props){
 const [view,setView]=useState<View>("split");
 const [tool,setTool]=useState<"link"|"anchor"|null>(null);
 const [linkText,setLinkText]=useState("");
 const [linkHref,setLinkHref]=useState("");
 const [anchor,setAnchor]=useState("");
 const [hint,setHint]=useState("");

 const range=()=>{
  const node=textareaRef.current;
  const start=node?.selectionStart??body.length;
  const end=node?.selectionEnd??start;
  return {start,end,selected:body.slice(start,end)};
 };
 const changeAt=(start:number,end:number,content:string,selectionStart:number,selectionEnd:number=selectionStart)=>{
  if(disabled)return;
  onChange(body.slice(0,start)+content+body.slice(end));
  setHint("");
  requestAnimationFrame(()=>{const node=textareaRef.current;if(!node)return;node.focus();node.setSelectionRange(selectionStart,selectionEnd);});
 };
 const wrap=(open:string,close:string,placeholder:string)=>{
  const {start,end,selected}=range();const value=selected||placeholder;
  changeAt(start,end,open+value+close,start+open.length,start+open.length+value.length);
 };
 const line=(prefix:string,placeholder:string)=>{
  const {start,end,selected}=range();
  const value=selected||placeholder;
  const item=prefix+value.split("\n").join("\n"+prefix);
  changeAt(start,end,item,start+prefix.length,start+item.length);
 };
 const insertBlock=(value:string)=>{const {start,end}=range();const prefix=start>0&&!body.slice(0,start).endsWith("\n\n")?"\n\n":"";const suffix=end<body.length&&!body.slice(end).startsWith("\n\n")?"\n\n":"";changeAt(start,end,prefix+value+suffix,start+prefix.length+value.length);};
 const startLink=()=>{setHint("");setLinkText(range().selected||"متن لینک");setLinkHref("");setTool("link");};
 const submitLink=()=>{const safe=safeNovaBlogHref(linkHref);if(!safe){setHint("نشانی لینک باید با https:// یا http:// شروع شود؛ برای لنگر از #anchor استفاده کنید.");return;}const label=linkText.trim().replace(/[\]\r\n]/g,"").slice(0,180)||"مشاهده لینک";const {start,end}=range();changeAt(start,end,`[${label}](${safe})`,start+label.length+safe.length+4);setTool(null);};
 const submitAnchor=()=>{const id=safeNovaBlogAnchor(anchor);if(!id){setHint("شناسه لنگر باید با حرف لاتین شروع شود و تنها شامل حروف، عدد، - یا _ باشد.");return;}insertBlock(`[anchor:${id}]`);setTool(null);};
 const keyDown=(event:KeyboardEvent<HTMLTextAreaElement>)=>{
  if(!(event.ctrlKey||event.metaKey)||event.altKey)return;
  if(event.key.toLowerCase()==="b"){event.preventDefault();wrap("**","**","متن پررنگ");}
  if(event.key.toLowerCase()==="i"){event.preventDefault();wrap("*","*","متن کج");}
  if(event.key.toLowerCase()==="k"){event.preventDefault();startLink();}
 };
 const words=body.trim()?body.trim().split(/\s+/).length:0;
 return <section className={styles.frame} aria-label="ویرایشگر پیشرفته مقاله">
  <div className={styles.topline}><div><strong>ویرایشگر حرفه‌ای مقاله</strong><span>قالب‌بندی امن · پشتیبانی از فارسی و انگلیسی</span></div><div className={styles.viewTabs} role="group" aria-label="حالت نمایش">
   <button type="button" aria-pressed={view==="write"} onClick={()=>setView("write")}>✎ نوشتن</button>
   <button type="button" aria-pressed={view==="split"} onClick={()=>setView("split")}>◫ کنار هم</button>
   <button type="button" aria-pressed={view==="preview"} onClick={()=>setView("preview")}>◉ پیش‌نمایش</button>
  </div></div>
  {view!=="preview"&&<div className={styles.toolbar} role="toolbar" aria-label="ابزارهای قالب‌بندی متن">
   <div className={styles.group}><select aria-label="قالب پاراگراف" defaultValue="" onChange={e=>{const value=e.target.value;if(value==="h1")line("# ","عنوان اصلی");if(value==="h2")line("## ","عنوان فرعی");if(value==="h3")line("### ","عنوان کوچک");if(value==="quote")line("> ","متن نقل‌قول");e.target.value="";}} disabled={disabled}><option value="">قالب متن</option><option value="h1">عنوان بزرگ</option><option value="h2">عنوان متوسط</option><option value="h3">عنوان کوچک</option><option value="quote">نقل‌قول</option></select>
    <select aria-label="اندازه فونت" defaultValue="" onChange={e=>{if(e.target.value)wrap(`[size:${e.target.value}]`,"[/size]","متن با اندازه دلخواه");e.target.value="";}} disabled={disabled}><option value="">اندازه متن</option>{NOVA_FONT_SIZES.map(size=><option key={size} value={size}>{size} پیکسل</option>)}</select>
    <select aria-label="رنگ متن" defaultValue="" onChange={e=>{if(e.target.value)wrap(`[color:${e.target.value}]`,"[/color]","متن رنگی");e.target.value="";}} disabled={disabled}><option value="">رنگ متن</option>{NOVA_TEXT_COLORS.map(color=><option key={color} value={color}>{paletteLabels[color]}</option>)}</select></div>
   <div className={styles.group}><button type="button" title="پررنگ (Ctrl+B)" aria-label="پررنگ" disabled={disabled} onClick={()=>wrap("**","**","متن پررنگ")}><b>B</b></button><button type="button" title="کج (Ctrl+I)" aria-label="کج" disabled={disabled} onClick={()=>wrap("*","*","متن کج")}><i>I</i></button><button type="button" title="زیرخط" aria-label="زیرخط" disabled={disabled} onClick={()=>wrap("[u]","[/u]","متن زیرخط‌دار")}><u>U</u></button><button type="button" title="خط‌خورده" aria-label="خط‌خورده" disabled={disabled} onClick={()=>wrap("~~","~~","متن خط‌خورده")}><s>S</s></button><button type="button" title="کد کوتاه" aria-label="کد کوتاه" disabled={disabled} onClick={()=>wrap("`","`","code")}>⌘</button></div>
   <div className={styles.group}><button type="button" title="درج لینک" disabled={disabled} onClick={startLink}>🔗 لینک</button><button type="button" title="لنگر داخلی" disabled={disabled} onClick={()=>{setTool("anchor");setAnchor("");setHint("");}}>⚓ لنگر</button><button type="button" title="فهرست بولت‌دار" disabled={disabled} onClick={()=>line("- ","مورد اول")}>☷ فهرست</button><button type="button" title="فهرست شماره‌دار" disabled={disabled} onClick={()=>line("1. ","مورد اول")}>1. 2. 3.</button></div>
   <div className={styles.group}><button type="button" title="راست‌چین" disabled={disabled} onClick={()=>wrap("[align:right]","[/align]","متن راست‌چین")}>⇥ راست</button><button type="button" title="وسط‌چین" disabled={disabled} onClick={()=>wrap("[align:center]","[/align]","متن وسط‌چین")}>≡ وسط</button><button type="button" title="چپ‌چین" disabled={disabled} onClick={()=>wrap("[align:left]","[/align]","متن چپ‌چین")}>⇤ چپ</button></div>
   <div className={styles.group}><button type="button" title="خط جداکننده" disabled={disabled} onClick={()=>insertBlock("---")}>― جداکننده</button><button type="button" title="جدول" disabled={disabled} onClick={()=>insertBlock("| ستون اول | ستون دوم |\n| --- | --- |\n| مقدار ۱ | مقدار ۲ |")}>▦ جدول</button></div>
  </div>}
  {tool&&view!=="preview"&&<div className={styles.popup} role="group" aria-label={tool==="link"?"افزودن لینک":"افزودن لنگر"}>
   {tool==="link"?<><label>متن نمایشی<input maxLength={180} value={linkText} onChange={e=>setLinkText(e.target.value)} placeholder="متن لینک"/></label><label>آدرس لینک<input dir="ltr" value={linkHref} onChange={e=>setLinkHref(e.target.value)} placeholder="https://example.com یا #section"/></label><button type="button" onClick={submitLink}>افزودن لینک</button></>:<><label>شناسه لنگر (لاتین)<input dir="ltr" maxLength={64} value={anchor} onChange={e=>setAnchor(e.target.value)} placeholder="my-section"/></label><button type="button" onClick={submitAnchor}>افزودن لنگر</button></>}
   <button type="button" onClick={()=>{setTool(null);setHint("");}}>انصراف</button>
  </div>}
  {hint&&<div className={styles.error} role="alert">{hint}</div>}
  <div className={`${styles.workarea} ${view==="split"?styles.split:""}`}>
   {view!=="preview"&&<div className={styles.editArea}><label htmlFor="nova-blog-content">متن مقاله</label><textarea id="nova-blog-content" ref={textareaRef} dir="rtl" spellCheck maxLength={NOVA_BLOG_BODY_LIMIT} rows={20} value={body} disabled={disabled} onChange={e=>onChange(e.target.value)} onKeyDown={keyDown} placeholder="متن مقاله را بنویسید. برای انتخاب عنوان، اندازه متن، لینک، لنگر و دیگر امکانات از نوار ابزار بالا استفاده کنید."/><div className={styles.help}>راهنما: برای لینک داخلی ابتدا لنگر بسازید، سپس لینک #شناسه را وارد کنید. برای تصویر، «افزودن عکس داخل متن» را بزنید.</div></div>}
   {view!=="write"&&<div className={styles.previewArea}><div className={styles.previewHeader}>👁 پیش‌نمایش مقاله در سایت</div>{body.trim()?<NovaBlogRichText source={body}/>:<p className={styles.empty}>پیش‌نمایش متن مقاله اینجا نمایش داده می‌شود.</p>}</div>}
  </div>
  <div className={styles.footer}><span>{words.toLocaleString("fa-IR")} واژه · حدود {Math.max(1,Math.ceil(words/200)).toLocaleString("fa-IR")} دقیقه مطالعه</span><span>{body.length.toLocaleString("fa-IR")} / {NOVA_BLOG_BODY_LIMIT.toLocaleString("fa-IR")} کاراکتر</span></div>
 </section>;
}
