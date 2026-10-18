"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {BrandMark} from "../lib/branding";
import {CustomerSessionProvider,useCustomerSession} from "../lib/customer-session";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {getResellerProfile} from "../lib/role-router";
import {readPortalAccess,writePortalAccess} from "../lib/access-cache";
import {resellerApi,ResellerRow} from "../lib/reseller-runtime-api";
import {CustomerNotificationCenter} from "./customer-notification-center";
import {ResellerNotificationCenter} from "./reseller-notification-center";

type IconName="home"|"cart"|"subscription"|"orders"|"wallet"|"payments"|"bell"|"profile";
type MenuItem=readonly [string,string,string,IconName];
type MenuGroup={fa:string;en:string;items:MenuItem[]};
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
  ["ساخت اشتراک","Create Subscription","/reseller/subscriptions","subscription"],
  ["پلن‌های ربات","Bot Plans","/reseller/sales","payments"],
  ["کیف پول و شارژ","Wallet & Top-up","/reseller/wallet","wallet"],
  ["کیف پول ربات","Bot Wallet","/reseller/bot-wallet","wallet"],
  ["خرید و شارژ حجم","Traffic Recharge","/reseller/traffic","cart"],
  ["سفارش‌ها","Orders","/reseller/orders","orders"],
  ["کدهای تخفیف","Discounts","/reseller/discounts","payments"],
  ["ربات نمایندگی","Reseller Bot","/reseller/bot","bell"],
  ["اعلان‌ها","Notifications","/reseller/notifications","bell"],
  ["تنظیمات","Settings","/reseller/settings","profile"]
];

const customerGroups:MenuGroup[]=[
  {fa:"اشتراک",en:"Subscription",items:customerMenu.slice(0,3)},
  {fa:"مالی",en:"Finance",items:customerMenu.slice(3,6)},
  {fa:"حساب",en:"Account",items:customerMenu.slice(6)}
];

const resellerGroups:MenuGroup[]=[
  {fa:"مدیریت",en:"Management",items:[resellerMenu[0],resellerMenu[1],resellerMenu[5]]},
  {fa:"مالی",en:"Finance",items:[resellerMenu[3],resellerMenu[4],resellerMenu[6]]},
  {fa:"فروش و ربات",en:"Sales & Bot",items:[resellerMenu[2],resellerMenu[7],resellerMenu[8]]},
  {fa:"حساب",en:"Account",items:[resellerMenu[9],resellerMenu[10]]}
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

function ResellerIdentity(){
  const {pick}=useI18n();
  const [profile,setProfile]=useState<ResellerRow>({});
  useEffect(()=>{let alive=true;resellerApi.me().then(value=>{if(alive)setProfile(value);}).catch(()=>{});return()=>{alive=false};},[]);
  const name=String(profile.brand_name||profile.name||pick("نماینده فروش","Reseller"));
  const secondary=String(profile.email||profile.code||"Partner");
  const initial=name.trim().charAt(0).toUpperCase()||"R";
  const logout=()=>{clearCustomerToken();window.location.replace("/login");};
  return <div className="customer-portal-identity reseller-portal-identity">
    <div className="customer-portal-user"><span className="customer-portal-avatar">{initial}</span><div className="customer-portal-user-copy"><b>{name}</b><small dir="ltr">{secondary}</small></div></div>
    <button type="button" className="customer-portal-logout" onClick={logout} title={pick("خروج از حساب","Sign out")}><span>↪</span><em>{pick("خروج","Sign out")}</em></button>
  </div>;
}

function AccessSkeleton({label}:{label:string}){
  return <div className="page portal-content-skeleton" aria-busy="true" aria-live="polite">
    <div className="portal-skeleton-head"><span/><span/></div>
    <div className="portal-skeleton-stats"><span/><span/><span/><span/></div>
    <div className="portal-skeleton-card"><span/><span/><span/></div>
    <small>{label}</small>
  </div>;
}

function CustomerAccessGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [ready,setReady]=useState(()=>{const token=getCustomerToken();return Boolean(token&&readPortalAccess(token)?.portal==="customer");});
  const [error,setError]=useState("");
  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);return;}
      const hadCache=readPortalAccess(token)?.portal==="customer";
      try{
        const [account,reseller]=await Promise.all([customerApi.me(token),getResellerProfile(token)]);
        if(!alive)return;
        if(!account.is_active){clearCustomerToken();window.location.replace("/login");return;}
        const portal=String(account.role||"").toLowerCase()==="admin"?"admin":reseller?"reseller":"customer";
        writePortalAccess(token,portal,account);
        if(portal!=="customer"){window.location.replace(portal==="admin"?"/admin":"/reseller");return;}
        setError("");setReady(true);
      }catch(reason){if(!alive)return;if(hadCache)return;setError(reason instanceof Error?reason.message:String(reason));}
    };
    void run();return()=>{alive=false};
  },[]);
  if(error)return <div className="page"><div className="auth-gate-card"><b>{pick("بررسی نوع حساب ناموفق بود","Could not verify account type")}</b><small>{error}</small><button className="ghost" onClick={()=>window.location.reload()}>{pick("تلاش دوباره","Retry")}</button></div></div>;
  if(!ready)return <AccessSkeleton label={pick("در حال آماده‌سازی حساب...","Preparing account...")}/>;
  return <>{children}</>;
}

function ResellerAccessGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [ready,setReady]=useState(()=>{const token=getCustomerToken();return Boolean(token&&readPortalAccess(token)?.portal==="reseller");});
  const [error,setError]=useState("");
  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);return;}
      const hadCache=readPortalAccess(token)?.portal==="reseller";
      try{
        const [account,reseller]=await Promise.all([customerApi.me(token),getResellerProfile(token)]);
        if(!alive)return;
        if(!account.is_active){clearCustomerToken();window.location.replace("/login");return;}
        const portal=String(account.role||"").toLowerCase()==="admin"?"admin":reseller?"reseller":"customer";
        writePortalAccess(token,portal,account);
        if(portal!=="reseller"){window.location.replace(portal==="admin"?"/admin":"/panel");return;}
        setError("");setReady(true);
      }catch(reason){if(!alive)return;if(hadCache)return;setError(reason instanceof Error?reason.message:String(reason));}
    };
    void run();return()=>{alive=false};
  },[]);
  if(error)return <div className="page"><div className="auth-gate-card"><b>{pick("بررسی دسترسی نمایندگی ناموفق بود","Could not verify reseller access")}</b><small>{error}</small><button className="ghost" onClick={()=>window.location.reload()}>{pick("تلاش دوباره","Retry")}</button></div></div>;
  if(!ready)return <AccessSkeleton label={pick("در حال آماده‌سازی نمایندگی...","Preparing reseller panel...")}/>;
  return <>{children}</>;
}

function PortalMenuLink({item,active,onClick}:{item:MenuItem;active:string;onClick?:()=>void}){
  const {pick}=useI18n();
  const [fa,en,href,icon]=item;
  return <Link prefetch href={href} className={active===href?"active":""} onClick={onClick}>
    <span className="customer-portal-nav-icon"><PortalIcon name={icon}/></span>
    <span className="customer-portal-nav-label">{pick(fa,en)}</span>
    {active===href&&<span className="customer-portal-active-dot"/>}
  </Link>;
}

function PortalTopNav({active,type}:{active:string;type:"customer"|"reseller"}){
  const {pick}=useI18n();
  const groups=type==="customer"?customerGroups:resellerGroups;
  return <nav className="customer-portal-topnav" aria-label={type==="customer"?pick("منوی حساب کاربری","Customer navigation"):pick("منوی نمایندگی","Reseller navigation")}>
    {groups.map(group=>{
      const groupActive=group.items.some(([, ,href])=>href===active);
      return <details className={`customer-portal-topnav-group ${groupActive?"active":""}`} key={group.fa}>
        <summary>{pick(group.fa,group.en)} <span>⌄</span></summary>
        <div className="customer-portal-topnav-menu">
          {group.items.map(item=><PortalMenuLink key={item[2]} item={item} active={active}/>)}
        </div>
      </details>;
    })}
  </nav>;
}

function PortalMobileDrawer({active,type,open,close}:{active:string;type:"customer"|"reseller";open:boolean;close:()=>void}){
  const {pick}=useI18n();
  const menu=type==="customer"?customerMenu:resellerMenu;
  return <>
    <button type="button" aria-label={pick("بستن منو","Close menu")} className={`customer-portal-mobile-backdrop ${open?"open":""}`} onClick={close}/>
    <aside className={`customer-portal-sidebar ${open?"open":""} ${type==="reseller"?"reseller-portal-sidebar":""}`}>
      <div className="customer-portal-brand-row"><div className="customer-portal-brand"><BrandMark/></div><button className="customer-portal-mobile-close" type="button" onClick={close} aria-label={pick("بستن منو","Close menu")}>×</button></div>
      <div className="customer-portal-section-label">{type==="customer"?pick("حساب کاربری","Customer account"):pick("مرکز نمایندگی","Reseller center")}</div>
      <nav className="customer-portal-nav">{menu.map(item=><PortalMenuLink key={item[2]} item={item} active={active} onClick={close}/>)}</nav>
      {type==="customer"?<CustomerIdentity/>:<ResellerIdentity/>}
    </aside>
  </>;
}

function PortalFrame({children,active="",type}:PortalShellProps){
  const {pick}=useI18n();
  const [mobileOpen,setMobileOpen]=useState(false);
  return <div className={`customer-portal-shell ${type==="reseller"?"reseller-portal-shell":""}`}>
    <main className="customer-portal-main">
      <header className="customer-portal-header">
        <div className="customer-portal-primarybar">
          <div className="customer-portal-header-brand"><BrandMark/></div>
          <PortalTopNav active={active} type={type}/>
          <div className="customer-portal-header-actions">
            {type==="customer"?<CustomerNotificationCenter/>:<ResellerNotificationCenter/>}
            <LanguageSwitch compact/>
            <ThemeSwitch compact/>
            <button className="customer-portal-mobile-toggle" type="button" onClick={()=>setMobileOpen(true)} aria-expanded={mobileOpen} aria-label={pick("باز کردن منو","Open menu")}>☰</button>
          </div>
        </div>
        <div className="customer-portal-utilitybar">
          <div className="customer-portal-search"><span>⌕</span><input placeholder={type==="customer"?pick("جستجو در حساب...","Search account..."):pick("جستجو در نمایندگی...","Search reseller panel...")}/></div>
          <div className="customer-portal-top-identity">{type==="customer"?<CustomerIdentity/>:<ResellerIdentity/>}</div>
        </div>
        <PortalMobileDrawer active={active} type={type} open={mobileOpen} close={()=>setMobileOpen(false)}/>
      </header>
      {children}
    </main>
  </div>;
}

export function PortalShell(props:PortalShellProps){
  if(props.type==="customer")return <CustomerSessionProvider><PortalFrame {...props}><CustomerAccessGuard>{props.children}</CustomerAccessGuard></PortalFrame></CustomerSessionProvider>;
  return <PortalFrame {...props}><ResellerAccessGuard>{props.children}</ResellerAccessGuard></PortalFrame>;
}
