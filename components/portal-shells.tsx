"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {BrandMark} from "../lib/branding";
import {CustomerSessionProvider,useCustomerSession} from "../lib/customer-session";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {getResellerProfile} from "../lib/role-router";
import {CustomerNotificationCenter} from "./customer-notification-center";

type IconName="home"|"cart"|"subscription"|"orders"|"wallet"|"payments"|"bell"|"profile";
type MenuItem=readonly [string,string,string,IconName];
type PortalShellProps={children:React.ReactNode;active?:string;type:"customer"|"reseller"};

const customerMenu:MenuItem[]=[
  ["داشبورد","Dashboard","/panel","home"],
  ["خرید اشتراک","Buy Subscription","/panel/buy","cart"],
  ["اشتراک من","My Subscription","/panel/subscription","subscription"],
  ["سفارش‌ها","Orders","/panel/orders","orders"],
  ["کیف پول","Wallet","/panel/wallet","wallet"],
  ["پرداخت‌ها","Payments","/panel/payments","payments"],
  ["اعلان‌ها","Notifications","/panel/notifications","bell"],
  ["پروفایل و امنیت","Profile & Security","/panel/profile","profile"]
];

const resellerMenu:MenuItem[]=[
  ["داشبورد","Dashboard","/reseller","home"],
  ["مشتریان","Customers","/reseller/customers","profile"],
  ["اشتراک‌ها","Subscriptions","/reseller/subscriptions","subscription"],
  ["فروش","Sales","/reseller/sales","payments"],
  ["کیف پول","Wallet","/reseller/wallet","wallet"],
  ["سفارش‌ها","Orders","/reseller/orders","orders"],
  ["کدهای تخفیف","Discounts","/reseller/discounts","payments"],
  ["بسته‌های ترافیک","Traffic Packages","/reseller/traffic","cart"],
  ["ربات نمایندگی","Reseller Bot","/reseller/bot","bell"],
  ["اعلان‌ها","Notifications","/reseller/notifications","bell"],
  ["تنظیمات","Settings","/reseller/settings","profile"]
];

function PortalIcon({name}:{name:IconName}){
  const common={width:20,height:20,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:1.8,strokeLinecap:"round" as const,strokeLinejoin:"round" as const,"aria-hidden":true};
  if(name==="home")return <svg {...common}><path d="M3.5 10.5 12 3.7l8.5 6.8"/><path d="M5.5 9.7v10h13v-10"/><path d="M9.4 19.7v-6h5.2v6"/></svg>;
  if(name==="cart")return <svg {...common}><path d="M4 5h2l1.5 9h9.7l2-6.5H7"/><circle cx="9" cy="18.5" r="1.2"/><circle cx="17" cy="18.5" r="1.2"/><path d="M15 3.5v5M12.5 6h5"/></svg>;
  if(name==="subscription")return <svg {...common}><rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="M7 9h10M7 13h6"/><circle cx="17" cy="14.5" r="1.5"/></svg>;
  if(name==="orders")return <svg {...common}><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>;
  if(name==="wallet")return <svg {...common}><path d="M4 7.5h14a2 2 0 0 1 2 2v8H6a2 2 0 0 1-2-2z"/><path d="M4 8V6a2 2 0 0 1 2-2h10v3.5"/><path d="M16 11.5h4v3h-4a1.5 1.5 0 0 1 0-3Z"/></svg>;
  if(name==="payments")return <svg {...common}><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 9h18M7 15h4"/></svg>;
  if(name==="bell")return <svg {...common}><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7"/><path d="M10 20h4"/></svg>;
  return <svg {...common}><circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/></svg>;
}

function CustomerIdentity(){
  const {pick}=useI18n();
  const {user,logout}=useCustomerSession();
  const initial=(user?.full_name||user?.email||"U").trim().charAt(0).toUpperCase();
  return <div className="customer-portal-identity">
    <div className="customer-portal-user"><span className="customer-portal-avatar">{initial}</span><div className="customer-portal-user-copy"><b>{user?.full_name||pick("کاربر","Customer")}</b><small>{user?.email||"Customer"}</small></div></div>
    <button type="button" className="customer-portal-logout" onClick={logout} title={pick("خروج از حساب","Sign out")}><span>↪</span><em>{pick("خروج","Sign out")}</em></button>
  </div>;
}

function CustomerAccessGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [ready,setReady]=useState(false);
  const [error,setError]=useState("");

  useEffect(()=>{
    let alive=true;

    const run=async()=>{
      const token=getCustomerToken();
      if(!token){
        window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
        return;
      }

      let account;
      try{
        account=await customerApi.me(token);
      }catch{
        clearCustomerToken();
        window.location.replace("/login");
        return;
      }

      if(!alive)return;

      if(!account.is_active){
        clearCustomerToken();
        window.location.replace("/login");
        return;
      }

      if(String(account.role||"").toLowerCase()==="admin"){
        window.location.replace("/admin");
        return;
      }

      try{
        const reseller=await getResellerProfile(token);
        if(!alive)return;

        if(reseller){
          window.location.replace("/reseller");
          return;
        }

        setReady(true);
      }catch(reason){
        if(alive)setError(reason instanceof Error?reason.message:String(reason));
      }
    };

    void run();
    return()=>{alive=false};
  },[]);

  if(error)return <div className="auth-gate"><div className="auth-gate-card"><b>{pick("بررسی نوع حساب ناموفق بود","Could not verify account type")}</b><small>{error}</small><button className="ghost" onClick={()=>window.location.reload()}>{pick("تلاش دوباره","Retry")}</button></div></div>;

  if(!ready)return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>{pick("در حال بررسی نوع حساب...","Checking account type...")}</b></div></div>;

  return <>{children}</>;
}

function ResellerAccessGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [ready,setReady]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);return;}
      let account;
      try{account=await customerApi.me(token);}catch{clearCustomerToken();window.location.replace("/login");return;}
      if(!alive)return;
      if(!account.is_active){clearCustomerToken();window.location.replace("/login");return;}
      if(account.role==="admin"){window.location.replace("/admin");return;}
      try{
        const reseller=await getResellerProfile(token);
        if(!alive)return;
        if(!reseller){window.location.replace("/panel");return;}
        setReady(true);
      }catch(reason){if(alive)setError(reason instanceof Error?reason.message:String(reason));}
    };
    void run();
    return()=>{alive=false};
  },[]);
  if(error)return <div className="auth-gate"><div className="auth-gate-card"><b>{pick("بررسی دسترسی نمایندگی ناموفق بود","Could not verify reseller access")}</b><small>{error}</small><button className="ghost" onClick={()=>window.location.reload()}>{pick("تلاش دوباره","Retry")}</button></div></div>;
  if(!ready)return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>{pick("در حال بررسی دسترسی نمایندگی...","Checking reseller access...")}</b></div></div>;
  return <>{children}</>;
}

function CustomerSidebar({active,collapsed,toggle,closeMobile}:{active:string;collapsed:boolean;toggle:()=>void;closeMobile:()=>void}){
  const {pick}=useI18n();
  return <aside className="customer-portal-sidebar">
    <div className="customer-portal-brand-row"><div className="customer-portal-brand"><BrandMark/></div><button className="customer-portal-collapse" type="button" onClick={toggle} aria-label={pick("جمع کردن منو","Collapse menu")}>‹</button><button className="customer-portal-mobile-close" type="button" onClick={closeMobile} aria-label={pick("بستن منو","Close menu")}>×</button></div>
    <div className="customer-portal-section-label">{pick("حساب کاربری","Customer account")}</div>
    <nav className="customer-portal-nav" aria-label={pick("منوی حساب کاربری","Customer navigation")}>
      {customerMenu.map(([fa,en,href,icon])=><Link key={href} href={href} className={active===href?"active":""} title={collapsed?pick(fa,en):undefined} onClick={closeMobile}><span className="customer-portal-nav-icon"><PortalIcon name={icon}/></span><span className="customer-portal-nav-label">{pick(fa,en)}</span>{active===href&&<span className="customer-portal-active-dot"/>}</Link>)}
    </nav>
    <CustomerIdentity/>
  </aside>;
}

function PortalFrame({children,active="",type}:PortalShellProps){
  const {pick}=useI18n();
  const [collapsed,setCollapsed]=useState(false);
  const [mobileOpen,setMobileOpen]=useState(false);
  const menu=type==="customer"?customerMenu:resellerMenu;
  const storageKey=`twinpanel.${type}.sidebar.collapsed`;

  useEffect(()=>{try{setCollapsed(localStorage.getItem(storageKey)==="1");}catch{}},[storageKey]);

  const toggle=()=>setCollapsed(v=>{
    const n=!v;
    try{localStorage.setItem(storageKey,n?"1":"0");}catch{}
    return n;
  });

  if(type==="customer")return <div className={`customer-portal-shell ${collapsed?"is-collapsed":""} ${mobileOpen?"is-mobile-open":""}`}>
    <CustomerSidebar active={active} collapsed={collapsed} toggle={toggle} closeMobile={()=>setMobileOpen(false)}/>
    <main className="customer-portal-main"><header className="customer-portal-header"><button className="customer-portal-mobile-toggle" type="button" onClick={()=>setMobileOpen(v=>!v)} aria-expanded={mobileOpen}>☰</button><div className="customer-portal-search"><span>⌕</span><input placeholder={pick("جستجو در حساب...","Search account...")}/></div><div className="customer-portal-header-actions"><CustomerNotificationCenter/><LanguageSwitch compact/><ThemeSwitch compact/></div></header>{children}</main>
  </div>;

  return <div className={`shell portal-shell portal-${type} ${collapsed?"sidebar-collapsed":""} ${mobileOpen?"mobile-menu-open":""}`}>
    <aside className="sidebar">
      <div className="sidebar-head"><BrandMark/><button className="sidebar-collapse" type="button" onClick={toggle}>↔</button><button className="mobile-menu-close" type="button" onClick={()=>setMobileOpen(false)}>×</button></div>
      <nav className="sidebar-nav"><div className="nav-group"><div className="nav-group-title">{pick("مرکز نمایندگی","Reseller Center")}</div>{menu.map(([fa,en,href,icon])=><Link key={href} href={href} className={active===href?"active":""} title={collapsed?pick(fa,en):undefined} onClick={()=>setMobileOpen(false)}><i><PortalIcon name={icon}/></i><span className="nav-label">{pick(fa,en)}</span></Link>)}</div></nav>
      <div className="profile"><span className="avatar">R</span><div className="profile-copy"><b>{pick("نماینده فروش","Reseller")}</b><small>Partner</small></div></div>
    </aside>
    <main><header><button className="mobile-menu-toggle" type="button" onClick={()=>setMobileOpen(v=>!v)} aria-expanded={mobileOpen}>☰</button><div className="search">⌕ <input placeholder={pick("جستجو...","Search...")}/></div><div className="head-actions"><LanguageSwitch compact/><ThemeSwitch compact/></div></header>{children}</main>
  </div>;
}

export function PortalShell(props:PortalShellProps){
  if(props.type==="customer")return <CustomerSessionProvider><CustomerAccessGuard><PortalFrame {...props}/></CustomerAccessGuard></CustomerSessionProvider>;
  return <ResellerAccessGuard><PortalFrame {...props}/></ResellerAccessGuard>;
}
