"use client";

import {createContext,useContext,useEffect,useMemo,useState} from "react";
import {usePathname} from "next/navigation";

export type Lang="fa"|"en";
type LangScope="admin"|"reseller"|"customer"|"public";

type I18nValue={
  lang:Lang;
  setLang:(lang:Lang)=>void;
  toggle:()=>void;
  pick:(fa:string,en:string)=>string;
  dir:"rtl"|"ltr";
};

const I18nContext=createContext<I18nValue|null>(null);

const exactEnglishUi:Record<string,string>={
  "تومان":"Toman",
  "گیگ":"GB",
  "روز":"days",
  "فعال":"Active",
  "غیرفعال":"Inactive",
  "خاموش":"Disabled",
  "آنلاین":"Online",
  "آفلاین":"Offline",
  "در انتظار":"Pending",
  "در انتظار پرداخت":"Pending payment",
  "پرداخت ثبت شده":"Payment submitted",
  "پرداخت ثبت‌شده":"Payment submitted",
  "در انتظار بررسی":"Awaiting review",
  "تأیید شده":"Approved",
  "تایید شده":"Approved",
  "تأیید خودکار":"Auto verified",
  "تایید خودکار":"Auto verified",
  "رد شده":"Rejected",
  "پرداخت شده":"Paid",
  "منقضی":"Expired",
  "معلق":"Suspended",
  "تعلیق":"Suspended",
  "لغوشده":"Canceled",
  "لغو شده":"Canceled",
  "نامشخص":"Unknown",
  "ناشناخته":"Unknown",
  "نامحدود":"Unlimited",
  "کارت به کارت":"Card to card",
  "حجم اولیه نمایندگی":"Initial reseller traffic",
  "بدون رزرو حجم نمایندگی":"without reseller traffic reservation",
  "بدون رزرو حجم":"without traffic reservation",
};

const trafficTypeEnglish:Record<string,string>={
  admin_initial_traffic:"Initial reseller traffic",
  subscription_created:"Subscription created without reseller traffic reservation",
  subscription_period_change:"Subscription period changed without reseller traffic reservation",
  traffic_package_purchase:"Traffic recharge package purchased",
  traffic_recharge:"Traffic recharged",
  admin_adjustment:"Administrator traffic adjustment",
  reseller_adjustment:"Reseller traffic adjustment",
};

function scopeForPath(pathname:string):LangScope{
  if(pathname==="/admin"||pathname.startsWith("/admin/"))return "admin";
  if(pathname==="/reseller"||pathname.startsWith("/reseller/"))return "reseller";
  if(pathname==="/panel"||pathname.startsWith("/panel/"))return "customer";
  return "public";
}

function savedLanguage(scope:LangScope):Lang{
  const scoped=window.localStorage.getItem(`twinpanel.lang.${scope}`);
  if(scoped==="fa"||scoped==="en")return scoped;

  // Reseller is deliberately isolated from the legacy global key. Previously,
  // changing the admin panel to English also forced the reseller portal into
  // English. A reseller with no explicit preference must start in Persian.
  if(scope==="reseller")return "fa";

  const legacy=window.localStorage.getItem("twinpanel.lang");
  return legacy==="en"?"en":"fa";
}

function latinDigits(value:string){
  const fa="۰۱۲۳۴۵۶۷۸۹";
  const ar="٠١٢٣٤٥٦٧٨٩";
  return value
    .replace(/[۰-۹]/g,char=>String(fa.indexOf(char)))
    .replace(/[٠-٩]/g,char=>String(ar.indexOf(char)))
    .replace(/٬/g,",")
    .replace(/٪/g,"%");
}

function preserveWhitespace(original:string,replacement:string){
  const lead=original.match(/^\s*/)?.[0]||"";
  const tail=original.match(/\s*$/)?.[0]||"";
  return `${lead}${replacement}${tail}`;
}

function trafficHistoryEnglish(parent:HTMLElement,text:string){
  const row=parent.closest("tr");
  if(!row)return null;
  const rowText=row.textContent||"";
  for(const [type,label] of Object.entries(trafficTypeEnglish)){
    if(rowText.includes(type)&&/[\u0600-\u06ff]/.test(text))return label;
  }
  return null;
}

function normalizeEnglishUiText(raw:string,parent:HTMLElement,scope:LangScope){
  let value=latinDigits(raw);
  const trimmed=value.trim();
  const exact=exactEnglishUi[trimmed];
  if(exact)return preserveWhitespace(value,exact);

  if(scope==="reseller"){
    const traffic=trafficHistoryEnglish(parent,value);
    if(traffic)return preserveWhitespace(value,traffic);
  }

  // Currency/unit output is UI formatting, not user-entered content. Keep
  // arbitrary Persian names/descriptions untouched while fixing known suffixes.
  value=value
    .replace(/\b([0-9][0-9,.]*)\s*گیگ\b/g,"$1 GB")
    .replace(/\b([0-9][0-9,.]*)\s*روز\b/g,"$1 days")
    .replace(/تومان/g,"Toman")
    .replace(/کارت\s*به\s*کارت/g,"Card to card")
    .replace(/\(قدیمی\)/g,"(Legacy)");

  // Known reseller ledger descriptions are backend-generated Persian text.
  // Convert only those patterns; never translate free-form reseller/customer data.
  value=value
    .replace(/حجم اولیه نمایندگی/g,"Initial reseller traffic")
    .replace(/تغییر دوره اشتراک\s*#?([0-9]+)/g,"Subscription #$1 period changed")
    .replace(/(?:ساخت|ایجاد) اشتراک\s*#?([0-9]+)/g,"Subscription #$1 created")
    .replace(/از پلن نماینده\s*#?([0-9]+)/g,"from reseller plan #$1")
    .replace(/با پلن\s*#?([0-9]+)/g,"with plan #$1")
    .replace(/بدون رزرو حجم نمایندگی/g,"without reseller traffic reservation")
    .replace(/بدون رزرو حجم/g,"without traffic reservation");

  return value;
}

function EnglishParityGuard({lang,scope}:{lang:Lang;scope:LangScope}){
  useEffect(()=>{
    if(lang!=="en"||!(scope==="admin"||scope==="reseller"))return;

    const blockedSelector="input,textarea,select,option,code,pre,[data-i18n-preserve='true']";

    const normalizeNode=(node:Node)=>{
      if(node.nodeType!==Node.TEXT_NODE)return;
      const parent=node.parentElement;
      const raw=node.nodeValue;
      if(!parent||raw==null||parent.closest(blockedSelector))return;
      if(!/[\u0600-\u06ff۰-۹٠-٩٬٪]/.test(raw))return;
      const next=normalizeEnglishUiText(raw,parent,scope);
      if(next!==raw)node.nodeValue=next;
    };

    const scan=(root:Node)=>{
      if(root.nodeType===Node.TEXT_NODE){normalizeNode(root);return;}
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
      let current=walker.nextNode();
      while(current){normalizeNode(current);current=walker.nextNode();}
    };

    scan(document.body);

    const observer=new MutationObserver(records=>{
      for(const record of records){
        if(record.type==="characterData")normalizeNode(record.target);
        for(const node of Array.from(record.addedNodes))scan(node);
      }
    });
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});
    return()=>observer.disconnect();
  },[lang,scope]);

  return null;
}

export function I18nProvider({children}:{children:React.ReactNode}){
  const pathname=usePathname()||"/";
  const scope=useMemo(()=>scopeForPath(pathname),[pathname]);
  const [lang,setLangState]=useState<Lang>("fa");
  const [readyScope,setReadyScope]=useState<LangScope|null>(null);

  useEffect(()=>{
    const initial=savedLanguage(scope);
    setLangState(initial);
    setReadyScope(scope);
    document.documentElement.lang=initial;
    document.documentElement.dir=initial==="fa"?"rtl":"ltr";
  },[scope]);

  useEffect(()=>{
    if(readyScope!==scope)return;
    document.documentElement.lang=lang;
    document.documentElement.dir=lang==="fa"?"rtl":"ltr";
    window.localStorage.setItem(`twinpanel.lang.${scope}`,lang);
  },[lang,scope,readyScope]);

  const value=useMemo<I18nValue>(()=>({
    lang,
    setLang:(next)=>setLangState(next),
    toggle:()=>setLangState(v=>v==="fa"?"en":"fa"),
    pick:(fa,en)=>lang==="fa"?fa:en,
    dir:lang==="fa"?"rtl":"ltr"
  }),[lang]);

  return <I18nContext.Provider value={value}><EnglishParityGuard lang={lang} scope={scope}/>{children}</I18nContext.Provider>;
}

export function useI18n(){
  const ctx=useContext(I18nContext);
  if(!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}

export function LanguageSwitch({compact=false}:{compact?:boolean}){
  const {lang,setLang}=useI18n();
  return <div className={`lang-switch ${compact?"compact":""}`} aria-label="Language selector">
    <button className={lang==="fa"?"active":""} onClick={()=>setLang("fa")} type="button">FA</button>
    <button className={lang==="en"?"active":""} onClick={()=>setLang("en")} type="button">EN</button>
  </div>;
}
