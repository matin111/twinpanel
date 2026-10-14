"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {AnyRow,parityApi} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";
import {
  DEFAULT_STOREFRONT_SETTINGS,
  STOREFRONT_SECTION_IDS,
  StorefrontLocale,
  StorefrontSectionId,
  StorefrontSettings,
  normalizeStorefrontSettings,
} from "../lib/storefront-config";
import {
  STORE_TEMPLATE_CATALOG,
  installedStoreTemplate,
} from "../lib/store-template-registry";

type Tab="templates"|"content"|"sections"|"seo";
type TextField={key:string;fa:string;en:string;long?:boolean};

const CONTENT_GROUPS:{id:string;fa:string;en:string;fields:TextField[]}[]=[
  {id:"hero",fa:"بخش اصلی",en:"Hero",fields:[
    {key:"hero_kicker",fa:"متن بالای عنوان",en:"Kicker"},
    {key:"hero_title",fa:"عنوان",en:"Title"},
    {key:"hero_highlight",fa:"بخش برجسته عنوان",en:"Highlighted title"},
    {key:"hero_description",fa:"توضیحات",en:"Description",long:true},
    {key:"hero_primary_button",fa:"دکمه اصلی",en:"Primary button"},
    {key:"hero_secondary_button",fa:"دکمه دوم",en:"Secondary button"},
  ]},
  {id:"plans",fa:"پلن‌ها",en:"Plans",fields:[
    {key:"plans_tag",fa:"برچسب",en:"Tag"},{key:"plans_title",fa:"عنوان",en:"Title"},{key:"plans_description",fa:"توضیحات",en:"Description",long:true},
  ]},
  {id:"protocols",fa:"پروتکل‌ها",en:"Protocols",fields:[
    {key:"protocols_tag",fa:"برچسب",en:"Tag"},{key:"protocols_title",fa:"عنوان",en:"Title"},{key:"protocols_description",fa:"توضیحات",en:"Description",long:true},
  ]},
  {id:"services",fa:"خدمات",en:"Services",fields:[
    {key:"services_tag",fa:"برچسب",en:"Tag"},{key:"services_title",fa:"عنوان",en:"Title"},{key:"services_description",fa:"توضیحات",en:"Description",long:true},
  ]},
  {id:"guides",fa:"آموزش اتصال",en:"Setup guides",fields:[
    {key:"guides_tag",fa:"برچسب",en:"Tag"},{key:"guides_title",fa:"عنوان",en:"Title"},{key:"guides_description",fa:"توضیحات",en:"Description",long:true},
  ]},
  {id:"account",fa:"پنل کاربری",en:"Customer panel",fields:[
    {key:"account_tag",fa:"برچسب",en:"Tag"},{key:"account_title",fa:"عنوان",en:"Title"},{key:"account_description",fa:"توضیحات",en:"Description",long:true},
  ]},
  {id:"faq",fa:"سوالات متداول",en:"FAQ",fields:[
    {key:"faq_tag",fa:"برچسب",en:"Tag"},{key:"faq_title",fa:"عنوان",en:"Title"},{key:"faq_description",fa:"توضیحات",en:"Description",long:true},
  ]},
];

const SECTION_LABELS:Record<StorefrontSectionId,{fa:string;en:string}>={
  plans:{fa:"پلن‌ها",en:"Plans"},
  protocols:{fa:"پروتکل‌ها",en:"Protocols"},
  services:{fa:"خدمات",en:"Services"},
  guides:{fa:"آموزش اتصال",en:"Setup guides"},
  account:{fa:"پنل کاربری",en:"Customer panel"},
  faq:{fa:"سوالات متداول",en:"FAQ"},
};

function payloadOf(settings:StorefrontSettings){
  const {updated_at:_,...payload}=settings;
  return payload as unknown as AnyRow;
}

export function StoreSettingsManager(){
  const {pick}=useI18n();
  const [tab,setTab]=useState<Tab>("templates");
  const [contentLocale,setContentLocale]=useState<StorefrontLocale>("fa");
  const [settings,setSettings]=useState<StorefrontSettings>(DEFAULT_STOREFRONT_SETTINGS);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{setSettings(normalizeStorefrontSettings(await parityApi.storefrontSettings()));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const save=async(next:StorefrontSettings=settings,message=pick("تنظیمات فروشگاه ذخیره شد.","Store settings saved."))=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      const saved=await parityApi.saveStorefrontSettings(payloadOf(next));
      setSettings(normalizeStorefrontSettings(saved));
      setOk(message);
      window.setTimeout(()=>setOk(""),3000);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const activeTemplate=installedStoreTemplate(settings.active_template);
  const unknownTemplate=Boolean(settings.active_template&&!activeTemplate);

  const setText=(key:string,value:string)=>{
    const actual=contentLocale==="en"?`${key}_en`:key;
    setSettings(current=>({...current,[actual]:value} as StorefrontSettings));
  };
  const textValue=(key:string)=>String((settings as unknown as Record<string,unknown>)[contentLocale==="en"?`${key}_en`:key]??"");

  const moveSection=(section:StorefrontSectionId,delta:number)=>{
    setSettings(current=>{
      const order=[...current.section_order];
      const index=order.indexOf(section);const target=index+delta;
      if(index<0||target<0||target>=order.length)return current;
      [order[index],order[target]]=[order[target],order[index]];
      return {...current,section_order:order};
    });
  };

  const sectionRows=useMemo(()=>settings.section_order.filter(section=>STOREFRONT_SECTION_IDS.includes(section)),[settings.section_order]);

  return <Shell active="/admin/store-settings"><div className="page storeAdminManager">
    <div className="page-head"><div><h1>{pick("مدیریت فروشگاه","Storefront Manager")}</h1><small>{pick("محتوا، چیدمان و قالب فعال فروشگاه عمومی را از یک بخش مدیریت کنید.","Manage storefront content, section layout and the active installed template from one place.")}</small></div><div className="action-row"><Link className="ghost" href="/store" target="_blank">{pick("مشاهده فروشگاه","Open storefront")} ↗</Link><button className="ghost" onClick={()=>void load()} disabled={loading||busy}>{pick("بازخوانی","Reload")}</button><button className="primary" onClick={()=>void save()} disabled={busy}>{busy?"…":pick("ذخیره تغییرات","Save changes")}</button></div></div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="storeAdminTabs" role="tablist">
      <button className={tab==="templates"?"active":""} onClick={()=>setTab("templates")}>{pick("قالب‌ها","Templates")}</button>
      <button className={tab==="content"?"active":""} onClick={()=>setTab("content")}>{pick("محتوا","Content")}</button>
      <button className={tab==="sections"?"active":""} onClick={()=>setTab("sections")}>{pick("بخش‌ها و ترتیب","Sections & order")}</button>
      <button className={tab==="seo"?"active":""} onClick={()=>setTab("seo")}>SEO</button>
    </div>

    {loading?<div className="runtime-loading">{pick("در حال دریافت تنظیمات فروشگاه...","Loading storefront settings...")}</div>:null}

    {!loading&&tab==="templates"&&<>
      <Card className="storeAdminIntro"><div><b>{pick("معماری قالب قابل ارتقا","Update-friendly template architecture")}</b><p>{pick("قالب‌ها همراه آپدیت TwinPanel نصب می‌شوند؛ انتخاب مدیر داخل دیتابیس ذخیره می‌شود. بنابراین در آپدیت‌های آینده می‌توان قالب جدید اضافه کرد بدون اینکه تنظیمات فعلی فروشگاه از بین برود.","Templates are installed with TwinPanel updates while the administrator's selected template id is persisted in the database. Future updates can add templates without replacing storefront content.")}</p></div><Badge tone="violet">{STORE_TEMPLATE_CATALOG.length} {pick("قالب نصب‌شده","installed")}</Badge></Card>
      {unknownTemplate&&<div className="runtime-warning">{pick(`قالب ذخیره‌شده «${settings.active_template}» در این نسخه نصب نیست؛ فروشگاه به‌صورت امن از قالب پیش‌فرض استفاده می‌کند.`,`Saved template “${settings.active_template}” is not installed in this version; the storefront safely falls back to the default template.`)}</div>}
      <div className="storeTemplateGrid">{STORE_TEMPLATE_CATALOG.map(template=>{
        const active=settings.active_template===template.id||(!activeTemplate&&template.id==="conversion-2027");
        return <Card className={`storeTemplateCard ${active?"active":""}`} key={template.id}>
          <div className="storeTemplatePreview"><span>◈</span><small>{template.id}</small></div>
          <div className="card-head"><div><b>{pick(template.nameFa,template.nameEn)}</b><small>v{template.version} · {template.author}</small></div>{active?<Badge tone="ok">{pick("فعال","Active")}</Badge>:<Badge tone="violet">{pick("نصب‌شده","Installed")}</Badge>}</div>
          <p>{pick(template.descriptionFa,template.descriptionEn)}</p>
          <div className="storeTemplateMeta"><span>◐ {pick("دارک","Dark")}</span><span>☀ {pick("لایت","Light")}</span><span>{template.builtIn?pick("داخلی","Built-in"):pick("افزونه","Extension")}</span></div>
          <div className="action-row"><button className={active?"ghost":"primary"} disabled={active||busy} onClick={()=>{const next={...settings,active_template:template.id};setSettings(next);void save(next,pick("قالب فروشگاه فعال شد.","Storefront template activated."));}}>{active?pick("قالب فعال","Active template"):pick("فعال‌سازی قالب","Activate template")}</button><Link className="ghost" href="/store" target="_blank">{pick("پیش‌نمایش زنده","Live preview")}</Link></div>
        </Card>;
      })}</div>
    </>}

    {!loading&&tab==="content"&&<>
      <Card className="storeLocaleBar"><div><b>{pick("زبان محتوای فروشگاه","Storefront content language")}</b><small>{pick("متن فارسی و انگلیسی مستقل ذخیره می‌شوند.","Persian and English storefront copy are saved independently.")}</small></div><div className="storeLocaleSwitch"><button className={contentLocale==="fa"?"active":""} onClick={()=>setContentLocale("fa")}>FA</button><button className={contentLocale==="en"?"active":""} onClick={()=>setContentLocale("en")}>EN</button></div></Card>
      <div className="storeContentGrid">{CONTENT_GROUPS.map(group=><Card key={group.id}><div className="card-head"><b>{pick(group.fa,group.en)}</b></div>{group.fields.map(field=><label className="field" key={field.key}><span>{pick(field.fa,field.en)}</span>{field.long?<textarea rows={3} value={textValue(field.key)} onChange={event=>setText(field.key,event.target.value)}/>:<input value={textValue(field.key)} onChange={event=>setText(field.key,event.target.value)}/>}</label>)}</Card>)}</div>
    </>}

    {!loading&&tab==="sections"&&<Card><div className="card-head"><div><b>{pick("نمایش و ترتیب بخش‌ها","Section visibility & order")}</b><small>{pick("ترتیب این لیست مستقیماً ترتیب بخش‌های فروشگاه است.","This list directly controls storefront section order.")}</small></div></div><div className="storeSectionList">{sectionRows.map((section,index)=>{
      const labels=SECTION_LABELS[section];const visible=Boolean((settings as unknown as Record<string,unknown>)[`show_${section}`]);
      return <div className="storeSectionRow" key={section}><span className="storeSectionIndex">{index+1}</span><div className="grow"><b>{pick(labels.fa,labels.en)}</b><small>#{section}</small></div><label className="toggle module-toggle"><span>{visible?pick("نمایش","Visible"):pick("مخفی","Hidden")}</span><input type="checkbox" checked={visible} onChange={event=>setSettings(current=>({...current,[`show_${section}`]:event.target.checked} as StorefrontSettings))}/><i/></label><div className="row-actions"><button className="mini-btn" disabled={index===0} onClick={()=>moveSection(section,-1)}>↑</button><button className="mini-btn" disabled={index===sectionRows.length-1} onClick={()=>moveSection(section,1)}>↓</button></div></div>;
    })}</div></Card>}

    {!loading&&tab==="seo"&&<div className="storeSeoGrid"><Card><div className="card-head"><b>{pick("متادیتای جستجو","Search metadata")}</b></div><label className="field"><span>SEO Title</span><input value={settings.seo_title} onChange={e=>setSettings(s=>({...s,seo_title:e.target.value}))}/></label><label className="field"><span>SEO Description</span><textarea rows={4} value={settings.seo_description} onChange={e=>setSettings(s=>({...s,seo_description:e.target.value}))}/></label><label className="field"><span>Keywords</span><textarea rows={3} value={settings.seo_keywords} onChange={e=>setSettings(s=>({...s,seo_keywords:e.target.value}))}/></label><label className="field"><span>Canonical URL</span><input dir="ltr" value={settings.canonical_url} onChange={e=>setSettings(s=>({...s,canonical_url:e.target.value}))}/></label></Card><Card><div className="card-head"><b>Open Graph & Robots</b></div><label className="field"><span>OG Title</span><input value={settings.og_title} onChange={e=>setSettings(s=>({...s,og_title:e.target.value}))}/></label><label className="field"><span>OG Description</span><textarea rows={3} value={settings.og_description} onChange={e=>setSettings(s=>({...s,og_description:e.target.value}))}/></label><label className="field"><span>OG Image URL</span><input dir="ltr" value={settings.og_image} onChange={e=>setSettings(s=>({...s,og_image:e.target.value}))}/></label><label className="toggle module-toggle"><span>Robots index</span><input type="checkbox" checked={settings.robots_index} onChange={e=>setSettings(s=>({...s,robots_index:e.target.checked}))}/><i/></label><label className="toggle module-toggle"><span>Robots follow</span><input type="checkbox" checked={settings.robots_follow} onChange={e=>setSettings(s=>({...s,robots_follow:e.target.checked}))}/><i/></label></Card></div>}
  </div></Shell>;
}
