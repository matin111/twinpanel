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

type Tab="templates"|"content"|"sections"|"contact"|"seo";
type TextField={key:string;fa:string;en:string;long?:boolean};
type ContentGroup={id:string;fa:string;en:string;fields:TextField[]};

const CONTENT_GROUPS:ContentGroup[]=[
  {id:"hero",fa:"بخش اصلی",en:"Hero",fields:[
    {key:"hero_kicker",fa:"متن بالای عنوان",en:"Kicker"},
    {key:"hero_title",fa:"عنوان",en:"Title"},
    {key:"hero_highlight",fa:"بخش برجسته عنوان",en:"Highlighted title"},
    {key:"hero_description",fa:"توضیحات",en:"Description",long:true},
    {key:"hero_primary_button",fa:"دکمه اصلی",en:"Primary button"},
    {key:"hero_secondary_button",fa:"دکمه دوم",en:"Secondary button"},
    {key:"hero_proof_1",fa:"نکته اعتماد ۱",en:"Proof item 1"},
    {key:"hero_proof_2",fa:"نکته اعتماد ۲",en:"Proof item 2"},
    {key:"hero_proof_3",fa:"نکته اعتماد ۳",en:"Proof item 3"},
  ]},
  {id:"plans",fa:"پلن‌ها",en:"Plans",fields:[
    {key:"plans_tag",fa:"برچسب",en:"Tag"},
    {key:"plans_title",fa:"عنوان",en:"Title"},
    {key:"plans_description",fa:"توضیحات",en:"Description",long:true},
    {key:"plan_feature_1",fa:"مزیت کارت پلن ۱",en:"Plan feature 1"},
    {key:"plan_feature_2",fa:"مزیت کارت پلن ۲",en:"Plan feature 2"},
    {key:"plan_feature_3",fa:"مزیت کارت پلن ۳",en:"Plan feature 3"},
  ]},
  {id:"protocols",fa:"پروتکل‌ها",en:"Protocols",fields:[
    {key:"protocols_tag",fa:"برچسب",en:"Tag"},
    {key:"protocols_title",fa:"عنوان",en:"Title"},
    {key:"protocols_description",fa:"توضیحات",en:"Description",long:true},
  ]},
  {id:"services",fa:"خدمات",en:"Services",fields:[
    {key:"services_tag",fa:"برچسب",en:"Tag"},
    {key:"services_title",fa:"عنوان",en:"Title"},
    {key:"services_description",fa:"توضیحات",en:"Description",long:true},
    {key:"service_1_title",fa:"کارت ۱ - عنوان",en:"Card 1 title"},
    {key:"service_1_description",fa:"کارت ۱ - توضیح",en:"Card 1 description",long:true},
    {key:"service_2_title",fa:"کارت ۲ - عنوان",en:"Card 2 title"},
    {key:"service_2_description",fa:"کارت ۲ - توضیح",en:"Card 2 description",long:true},
    {key:"service_3_title",fa:"کارت ۳ - عنوان",en:"Card 3 title"},
    {key:"service_3_description",fa:"کارت ۳ - توضیح",en:"Card 3 description",long:true},
    {key:"service_4_title",fa:"کارت ۴ - عنوان",en:"Card 4 title"},
    {key:"service_4_description",fa:"کارت ۴ - توضیح",en:"Card 4 description",long:true},
    {key:"service_5_title",fa:"کارت ۵ - عنوان",en:"Card 5 title"},
    {key:"service_5_description",fa:"کارت ۵ - توضیح",en:"Card 5 description",long:true},
    {key:"service_6_title",fa:"کارت ۶ - عنوان",en:"Card 6 title"},
    {key:"service_6_description",fa:"کارت ۶ - توضیح",en:"Card 6 description",long:true},
  ]},
  {id:"guides",fa:"آموزش اتصال",en:"Setup guides",fields:[
    {key:"guides_tag",fa:"برچسب",en:"Tag"},
    {key:"guides_title",fa:"عنوان",en:"Title"},
    {key:"guides_description",fa:"توضیحات",en:"Description",long:true},
  ]},
  {id:"account",fa:"پنل کاربری",en:"Customer panel",fields:[
    {key:"account_tag",fa:"برچسب",en:"Tag"},
    {key:"account_title",fa:"عنوان",en:"Title"},
    {key:"account_description",fa:"توضیحات",en:"Description",long:true},
    {key:"account_primary_button",fa:"دکمه اصلی",en:"Primary button"},
    {key:"account_secondary_button",fa:"دکمه پشتیبانی",en:"Support button"},
    {key:"account_item_1_title",fa:"آیتم ۱ - عنوان",en:"Item 1 title"},
    {key:"account_item_1_description",fa:"آیتم ۱ - توضیح",en:"Item 1 description"},
    {key:"account_item_2_title",fa:"آیتم ۲ - عنوان",en:"Item 2 title"},
    {key:"account_item_2_description",fa:"آیتم ۲ - توضیح",en:"Item 2 description"},
    {key:"account_item_3_title",fa:"آیتم ۳ - عنوان",en:"Item 3 title"},
    {key:"account_item_3_description",fa:"آیتم ۳ - توضیح",en:"Item 3 description"},
    {key:"account_item_4_title",fa:"آیتم ۴ - عنوان",en:"Item 4 title"},
    {key:"account_item_4_description",fa:"آیتم ۴ - توضیح",en:"Item 4 description"},
  ]},
  {id:"faq",fa:"سوالات متداول",en:"FAQ",fields:[
    {key:"faq_tag",fa:"برچسب",en:"Tag"},
    {key:"faq_title",fa:"عنوان",en:"Title"},
    {key:"faq_description",fa:"توضیحات",en:"Description",long:true},
    {key:"faq_1_question",fa:"سوال ۱",en:"Question 1"},{key:"faq_1_answer",fa:"پاسخ ۱",en:"Answer 1",long:true},
    {key:"faq_2_question",fa:"سوال ۲",en:"Question 2"},{key:"faq_2_answer",fa:"پاسخ ۲",en:"Answer 2",long:true},
    {key:"faq_3_question",fa:"سوال ۳",en:"Question 3"},{key:"faq_3_answer",fa:"پاسخ ۳",en:"Answer 3",long:true},
    {key:"faq_4_question",fa:"سوال ۴",en:"Question 4"},{key:"faq_4_answer",fa:"پاسخ ۴",en:"Answer 4",long:true},
    {key:"faq_5_question",fa:"سوال ۵",en:"Question 5"},{key:"faq_5_answer",fa:"پاسخ ۵",en:"Answer 5",long:true},
  ]},
  {id:"trust",fa:"نوار اعتماد",en:"Trust strip",fields:[
    {key:"trust_speed_title",fa:"سرعت - عنوان",en:"Speed title"},{key:"trust_speed_description",fa:"سرعت - توضیح",en:"Speed description"},
    {key:"trust_uptime_value",fa:"پایداری - مقدار",en:"Uptime value"},{key:"trust_uptime_description",fa:"پایداری - توضیح",en:"Uptime description"},
    {key:"trust_support_title",fa:"پشتیبانی - عنوان",en:"Support title"},{key:"trust_support_description",fa:"پشتیبانی - توضیح",en:"Support description"},
    {key:"trust_protocols_description",fa:"پروتکل‌ها - توضیح",en:"Protocols description"},
    {key:"trust_payment_title",fa:"پرداخت - عنوان",en:"Payment title"},{key:"trust_payment_description",fa:"پرداخت - توضیح",en:"Payment description"},
    {key:"trust_activation_title",fa:"فعال‌سازی - عنوان",en:"Activation title"},{key:"trust_activation_description",fa:"فعال‌سازی - توضیح",en:"Activation description"},
  ]},
  {id:"final",fa:"دعوت نهایی به خرید",en:"Final CTA",fields:[
    {key:"final_cta_tag",fa:"برچسب",en:"Tag"},
    {key:"final_cta_title",fa:"عنوان",en:"Title"},
    {key:"final_cta_description",fa:"توضیحات",en:"Description",long:true},
    {key:"final_cta_button",fa:"متن دکمه",en:"Button text"},
  ]},
];

const CONTACT_GROUPS:ContentGroup[]=[
  {id:"contact",fa:"بخش ارتباط",en:"Contact section",fields:[
    {key:"contact_tag",fa:"برچسب",en:"Tag"},
    {key:"contact_title",fa:"عنوان",en:"Title"},
    {key:"contact_description",fa:"توضیحات",en:"Description",long:true},
    {key:"chat_title",fa:"عنوان چت آنلاین",en:"Live chat title"},
    {key:"chat_description",fa:"توضیح چت آنلاین",en:"Live chat description",long:true},
  ]},
  {id:"telegram",fa:"تلگرام",en:"Telegram",fields:[
    {key:"telegram_title",fa:"عنوان",en:"Title"},
    {key:"telegram_description",fa:"توضیح",en:"Description",long:true},
  ]},
  {id:"instagram",fa:"اینستاگرام",en:"Instagram",fields:[
    {key:"instagram_title",fa:"عنوان",en:"Title"},
    {key:"instagram_description",fa:"توضیح",en:"Description",long:true},
  ]},
  {id:"whatsapp",fa:"واتس‌اپ",en:"WhatsApp",fields:[
    {key:"whatsapp_title",fa:"عنوان",en:"Title"},
    {key:"whatsapp_description",fa:"توضیح",en:"Description",long:true},
  ]},
  {id:"footer",fa:"فوتر",en:"Footer",fields:[
    {key:"footer_tagline",fa:"زیرعنوان برند",en:"Brand tagline",long:true},
    {key:"footer_quick_title",fa:"عنوان لینک‌های سریع",en:"Quick links heading"},
    {key:"footer_support_title",fa:"عنوان خدمات و پشتیبانی",en:"Support heading"},
    {key:"footer_social_title",fa:"عنوان شبکه‌های اجتماعی",en:"Social heading"},
    {key:"footer_rights",fa:"متن حقوق",en:"Rights text"},
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
  const localeBar=<Card className="storeLocaleBar"><div><b>{pick("زبان محتوای فروشگاه","Storefront content language")}</b><small>{pick("متن فارسی و انگلیسی مستقل ذخیره می‌شوند.","Persian and English storefront copy are saved independently.")}</small></div><div className="storeLocaleSwitch"><button className={contentLocale==="fa"?"active":""} onClick={()=>setContentLocale("fa")}>FA</button><button className={contentLocale==="en"?"active":""} onClick={()=>setContentLocale("en")}>EN</button></div></Card>;
  const renderGroups=(groups:ContentGroup[])=><div className="storeContentGrid">{groups.map(group=><Card key={group.id}><div className="card-head"><b>{pick(group.fa,group.en)}</b></div>{group.fields.map(field=><label className="field" key={field.key}><span>{pick(field.fa,field.en)}</span>{field.long?<textarea rows={3} value={textValue(field.key)} onChange={event=>setText(field.key,event.target.value)}/>:<input value={textValue(field.key)} onChange={event=>setText(field.key,event.target.value)}/>}</label>)}</Card>)}</div>;

  return <Shell active="/admin/store-settings"><div className="page storeAdminManager">
    <div className="page-head"><div><h1>{pick("مدیریت فروشگاه","Storefront Manager")}</h1><small>{pick("محتوا، شبکه‌های اجتماعی، فوتر، چیدمان، SEO و قالب فروشگاه عمومی را از همین بخش مدیریت کنید.","Manage public storefront content, social links, footer, layout, SEO and the active template from one place.")}</small></div><div className="action-row"><Link className="ghost" href="/store" target="_blank">{pick("مشاهده فروشگاه","Open storefront")} ↗</Link><button className="ghost" onClick={()=>void load()} disabled={loading||busy}>{pick("بازخوانی","Reload")}</button><button className="primary" onClick={()=>void save()} disabled={busy}>{busy?"…":pick("ذخیره تغییرات","Save changes")}</button></div></div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="storeAdminTabs" role="tablist">
      <button className={tab==="templates"?"active":""} onClick={()=>setTab("templates")}>{pick("قالب‌ها","Templates")}</button>
      <button className={tab==="content"?"active":""} onClick={()=>setTab("content")}>{pick("محتوا","Content")}</button>
      <button className={tab==="sections"?"active":""} onClick={()=>setTab("sections")}>{pick("بخش‌ها و ترتیب","Sections & order")}</button>
      <button className={tab==="contact"?"active":""} onClick={()=>setTab("contact")}>{pick("ارتباط و فوتر","Contact & footer")}</button>
      <button className={tab==="seo"?"active":""} onClick={()=>setTab("seo")}>SEO</button>
    </div>

    {loading?<div className="runtime-loading">{pick("در حال دریافت تنظیمات فروشگاه...","Loading storefront settings...")}</div>:null}

    {!loading&&tab==="templates"&&<>
      <Card className="storeAdminIntro"><div><b>{pick("معماری قالب قابل ارتقا","Update-friendly template architecture")}</b><p>{pick("قالب‌ها همراه آپدیت نصب می‌شوند اما محتوای فروشگاه و قالب انتخابی داخل دیتابیس باقی می‌ماند.","Templates ship with product updates while storefront content and the selected template remain persisted in the database.")}</p></div><Badge tone="violet">{STORE_TEMPLATE_CATALOG.length} {pick("قالب نصب‌شده","installed")}</Badge></Card>
      {unknownTemplate&&<div className="runtime-warning">{pick(`قالب ذخیره‌شده «${settings.active_template}» در این نسخه نصب نیست؛ فروشگاه از قالب پیش‌فرض استفاده می‌کند.`,`Saved template “${settings.active_template}” is not installed in this version; the storefront falls back to the default template.`)}</div>}
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

    {!loading&&tab==="content"&&<>{localeBar}{renderGroups(CONTENT_GROUPS)}</>}

    {!loading&&tab==="sections"&&<div className="storeContentGrid">
      <Card><div className="card-head"><div><b>{pick("نمایش و ترتیب بخش‌ها","Section visibility & order")}</b><small>{pick("ترتیب این لیست مستقیماً ترتیب بخش‌های اصلی فروشگاه است.","This list directly controls the order of the main storefront sections.")}</small></div></div><div className="storeSectionList">{sectionRows.map((section,index)=>{
        const labels=SECTION_LABELS[section];const visible=Boolean((settings as unknown as Record<string,unknown>)[`show_${section}`]);
        return <div className="storeSectionRow" key={section}><span className="storeSectionIndex">{index+1}</span><div className="grow"><b>{pick(labels.fa,labels.en)}</b><small>#{section}</small></div><label className="toggle module-toggle"><span>{visible?pick("نمایش","Visible"):pick("مخفی","Hidden")}</span><input type="checkbox" checked={visible} onChange={event=>setSettings(current=>({...current,[`show_${section}`]:event.target.checked} as StorefrontSettings))}/><i/></label><div className="row-actions"><button className="mini-btn" disabled={index===0} onClick={()=>moveSection(section,-1)}>↑</button><button className="mini-btn" disabled={index===sectionRows.length-1} onClick={()=>moveSection(section,1)}>↓</button></div></div>;
      })}</div></Card>
      <Card><div className="card-head"><b>{pick("بخش‌های تکمیلی","Extra sections")}</b></div>
        <label className="toggle module-toggle"><span>{pick("دعوت نهایی به خرید","Final purchase CTA")}</span><input type="checkbox" checked={settings.show_final_cta} onChange={e=>setSettings(s=>({...s,show_final_cta:e.target.checked}))}/><i/></label>
        <label className="toggle module-toggle"><span>{pick("بخش ارتباط","Contact section")}</span><input type="checkbox" checked={settings.show_contact} onChange={e=>setSettings(s=>({...s,show_contact:e.target.checked}))}/><i/></label>
      </Card>
    </div>}

    {!loading&&tab==="contact"&&<>
      {localeBar}
      <div className="storeSeoGrid"><Card><div className="card-head"><b>{pick("لینک شبکه‌های اجتماعی","Social links")}</b></div>
        <label className="field"><span>Telegram URL</span><input dir="ltr" value={settings.telegram_url} onChange={e=>setSettings(s=>({...s,telegram_url:e.target.value}))}/></label>
        <label className="field"><span>Instagram URL</span><input dir="ltr" value={settings.instagram_url} onChange={e=>setSettings(s=>({...s,instagram_url:e.target.value}))}/></label>
        <label className="field"><span>WhatsApp URL</span><input dir="ltr" value={settings.whatsapp_url} onChange={e=>setSettings(s=>({...s,whatsapp_url:e.target.value}))}/></label>
      </Card><Card><div className="card-head"><b>{pick("نمایش شبکه‌ها","Social visibility")}</b></div>
        <label className="toggle module-toggle"><span>Telegram</span><input type="checkbox" checked={settings.show_telegram} onChange={e=>setSettings(s=>({...s,show_telegram:e.target.checked}))}/><i/></label>
        <label className="toggle module-toggle"><span>Instagram</span><input type="checkbox" checked={settings.show_instagram} onChange={e=>setSettings(s=>({...s,show_instagram:e.target.checked}))}/><i/></label>
        <label className="toggle module-toggle"><span>WhatsApp</span><input type="checkbox" checked={settings.show_whatsapp} onChange={e=>setSettings(s=>({...s,show_whatsapp:e.target.checked}))}/><i/></label>
      </Card></div>
      {renderGroups(CONTACT_GROUPS)}
    </>}

    {!loading&&tab==="seo"&&<div className="storeSeoGrid"><Card><div className="card-head"><b>{pick("متادیتای جستجو","Search metadata")}</b></div><label className="field"><span>SEO Title</span><input value={settings.seo_title} onChange={e=>setSettings(s=>({...s,seo_title:e.target.value}))}/></label><label className="field"><span>SEO Description</span><textarea rows={4} value={settings.seo_description} onChange={e=>setSettings(s=>({...s,seo_description:e.target.value}))}/></label><label className="field"><span>Keywords</span><textarea rows={3} value={settings.seo_keywords} onChange={e=>setSettings(s=>({...s,seo_keywords:e.target.value}))}/></label><label className="field"><span>Canonical URL</span><input dir="ltr" value={settings.canonical_url} onChange={e=>setSettings(s=>({...s,canonical_url:e.target.value}))}/></label></Card><Card><div className="card-head"><b>Open Graph & Robots</b></div><label className="field"><span>OG Title</span><input value={settings.og_title} onChange={e=>setSettings(s=>({...s,og_title:e.target.value}))}/></label><label className="field"><span>OG Description</span><textarea rows={3} value={settings.og_description} onChange={e=>setSettings(s=>({...s,og_description:e.target.value}))}/></label><label className="field"><span>OG Image URL</span><input dir="ltr" value={settings.og_image} onChange={e=>setSettings(s=>({...s,og_image:e.target.value}))}/></label><label className="toggle module-toggle"><span>Robots index</span><input type="checkbox" checked={settings.robots_index} onChange={e=>setSettings(s=>({...s,robots_index:e.target.checked}))}/><i/></label><label className="toggle module-toggle"><span>Robots follow</span><input type="checkbox" checked={settings.robots_follow} onChange={e=>setSettings(s=>({...s,robots_follow:e.target.checked}))}/><i/></label></Card></div>}
  </div></Shell>;
}
