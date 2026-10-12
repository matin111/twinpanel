"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {BrandMark} from "../lib/branding";

const menuGroups=[
  {fa:"مدیریت",en:"Management",items:[
    ["داشبورد","Dashboard","/admin","⌂"],
    ["کاربران","Users","/admin/users","♙"],
    ["اشتراک‌ها","Subscriptions","/admin/subscriptions","▱"],
    ["ابزار اشتراک","Subscription Tools","/admin/subscription-tools","⌘"],
    ["پلن‌ها","Plans","/admin/plans","◈"]
  ]},
  {fa:"زیرساخت",en:"Infrastructure",items:[
    ["نودها","Nodes","/admin/nodes","▦"],
    ["تانل‌ها","Tunnels","/admin/tunnels","⤨"],
    ["Transportها","Transport Manager","/admin/tunnel-transports","⇄"],
    ["راه‌اندازی نود","Provisioning","/admin/provision","⚡"],
    ["دامنه و SSL","Domains & SSL","/admin/domains","⌘"],
    ["دسترسی مادر","Mother Access","/admin/mother-access","⌁"]
  ]},
  {fa:"مالی و فروش",en:"Sales & Finance",items:[
    ["پرداخت‌ها","Payments","/admin/payments","◫"],
    ["کیف پول","Wallet","/admin/wallet","◉"],
    ["کد تخفیف","Discounts","/admin/discounts","％"],
    ["نمایندگی‌ها","Resellers","/admin/resellers","♜"],
    ["تنظیمات فروشگاه","Store Settings","/admin/store-settings","◇"]
  ]},
  {fa:"ارتباطات",en:"Communications",items:[
    ["ربات تلگرام","Telegram Bot","/admin/telegram","✈"],
    ["مدیریت تلگرام","Telegram Manager","/admin/telegram-manager","◈"],
    ["SMS Reader","SMS Reader","/admin/sms-reader","▤"],
    ["پشتیبانی","Support","/admin/support","◌"],
    ["اعلان‌ها","Notifications","/admin/notifications","◎"]
  ]},
  {fa:"تحویل و سرویس",en:"Delivery & Service",items:[
    ["تحویل اکانت","Account Delivery","/admin/account-delivery","⇲"],
    ["فایل‌های دانلود","Download Files","/admin/downloads","⇩"],
    ["تنظیمات VPN","VPN Settings","/admin/vpn-settings","⌁"],
    ["L2TP / IPsec","L2TP / IPsec","/admin/l2tp","◎"],
    ["برندینگ","Branding","/admin/branding","✦"]
  ]},
  {fa:"سیستم",en:"System",items:[
    ["سلامت و امنیت","Health & Security","/admin/system-health","⌾"],
    ["بکاپ و بازیابی","Backup & Restore","/admin/backups","⟲"],
    ["تنظیمات","Settings","/admin/settings","⚙"]
  ]}
] as const;

export function Shell({children,active="/admin"}:{children:React.ReactNode;active?:string}){
  const {pick}=useI18n();
  const [collapsed,setCollapsed]=useState(false);
  const [mobileOpen,setMobileOpen]=useState(false);

  useEffect(()=>{
    try{setCollapsed(localStorage.getItem("twinpanel.sidebar.collapsed")==="1");}catch{}
  },[]);

  const toggleCollapsed=()=>{
    setCollapsed(prev=>{
      const next=!prev;
      try{localStorage.setItem("twinpanel.sidebar.collapsed",next?"1":"0");}catch{}
      return next;
    });
  };

  return <div className={`shell admin-shell ${collapsed?"sidebar-collapsed":""} ${mobileOpen?"mobile-menu-open":""}`}>
    <aside className="sidebar" aria-label={pick("منوی اصلی","Main navigation")}>
      <div className="sidebar-head">
        <BrandMark/>
        <button className="sidebar-collapse" type="button" onClick={toggleCollapsed} aria-label={pick("باز و بسته کردن منو","Toggle sidebar")} title={pick("باز و بسته کردن منو","Toggle sidebar")}>↔</button>
        <button className="mobile-menu-close" type="button" onClick={()=>setMobileOpen(false)} aria-label={pick("بستن منو","Close menu")}>×</button>
      </div>

      <nav className="sidebar-nav">{menuGroups.map(group=><div className="nav-group" key={group.en}>
        <div className="nav-group-title">{pick(group.fa,group.en)}</div>
        {group.items.map(([fa,en,h,i])=>{
          const label=pick(fa,en);
          return <Link key={h} href={h} title={collapsed?label:undefined} className={active===h?"active":""} onClick={()=>setMobileOpen(false)}>
            <i>{i}</i><span className="nav-label">{label}</span>
          </Link>;
        })}
      </div>)}</nav>

      <div className="profile">
        <span className="avatar">M</span>
        <div className="profile-copy"><b>{pick("مدیر سیستم","System Admin")}</b><small>Administrator</small></div>
      </div>
    </aside>

    <main>
      <header>
        <button className="mobile-menu-toggle" type="button" onClick={()=>setMobileOpen(v=>!v)} aria-expanded={mobileOpen} aria-label={pick("نمایش منو","Show menu")}>☰</button>
        <div className="search">⌕ <input placeholder={pick("جستجو در پنل...","Search panel...")}/></div>
        <div className="head-actions"><LanguageSwitch compact/><ThemeSwitch compact/><button className="notify" type="button" title={pick("اعلان‌ها","Notifications")}>◉</button><span className="avatar">M</span></div>
      </header>
      {children}
    </main>
  </div>;
}

export function PageHead({title,sub:_sub,action}:{title:string;sub?:string;action?:string}){
  return <div className="page-head"><div><h1>{title}</h1></div>{action&&<button className="primary">＋ {action}</button>}</div>;
}

export function Card({children,className=""}:{children:React.ReactNode;className?:string}){
  return <section className={`card ${className}`}>{children}</section>;
}

export function Stat({label,value,delta,icon="◈"}:{label:string;value:string;delta?:string;icon?:string}){
  return <Card className="stat"><span className="stat-icon">{icon}</span><div><small>{label}</small><b>{value}</b>{delta&&<em>{delta}</em>}</div></Card>;
}

export function Badge({children,tone="ok"}:{children:React.ReactNode;tone?:"ok"|"warn"|"bad"|"violet"}){
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Toolbar(){
  const {pick}=useI18n();
  return <div className="toolbar"><label>⌕ <input placeholder={pick("جستجو...","Search...")}/></label><button>{pick("همه وضعیت‌ها","All statuses")}⌄</button><button>{pick("فیلترها","Filters")}⌄</button></div>;
}

export const names=[
  ["علی رضایی","Ali Rezaei"],
  ["سارا محمدی","Sara Mohammadi"],
  ["محمد کریمی","Mohammad Karimi"],
  ["نگار حسینی","Negar Hosseini"],
  ["رضا احمدی","Reza Ahmadi"]
] as const;