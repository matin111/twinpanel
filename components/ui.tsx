"use client";

import Link from "next/link";
import {useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {BrandMark} from "../lib/branding";
import {PaymentReviewBadge} from "./payment-review-badge";
import {AdminNotificationCenter} from "./admin-notification-center";
import {SupportUnreadBadge} from "./support-unread-badge";
import {SystemReleaseFooter} from "./system-release-footer";

const menuGroups=[
  {fa:"مدیریت",en:"Management",items:[
    ["داشبورد","Dashboard","/admin","⌂"],
    ["کاربران","Users","/admin/users","♙"],
    ["اشتراک‌ها","Subscriptions","/admin/subscriptions","▱"],
    ["پلن‌ها","Plans","/admin/plans","◈"]
  ]},
  {fa:"شبکه و زیرساخت",en:"Network & Infrastructure",items:[
    ["نودها","Nodes","/admin/nodes","▦"],
    ["تانل‌ها","Tunnels","/admin/tunnels","⤨"],
    ["راه‌اندازی نود","Provision Node","/admin/provision","⚡"],
    ["دامنه و SSL","Domains & SSL","/admin/domains","⌘"]
  ]},
  {fa:"فروش و مالی",en:"Sales & Finance",items:[
    ["پرداخت‌ها","Payments","/admin/payments","◫"],
    ["تنظیمات پرداخت","Payment Settings","/admin/payment-settings","⌁"],
    ["تأیید خودکار کارت","Auto Payment Verification","/admin/sms-reader","▤"],
    ["کدهای تخفیف","Discount Codes","/admin/discounts","％"],
    ["نمایندگی‌ها","Resellers","/admin/resellers","♜"],
    ["پلن‌های شارژ حجم","Traffic Recharge Plans","/admin/reseller-traffic-plans","▣"],
    ["تنظیمات فروشگاه","Store Settings","/admin/store-settings","◇"]
  ]},
  {fa:"ارتباطات و پشتیبانی",en:"Communications & Support",items:[
    ["ربات تلگرام","Telegram Bot","/admin/telegram","✈"],
    ["پشتیبانی","Support","/admin/support","◌"],
    ["اعلان‌ها","Notifications","/admin/notifications","◎"]
  ]},
  {fa:"محتوا و برند",en:"Content & Brand",items:[
    ["فایل‌های دانلود","Downloads","/admin/downloads","⇩"],
    ["برندینگ","Branding","/admin/branding","✦"]
  ]},
  {fa:"سیستم و نگهداری",en:"System & Maintenance",items:[
    ["امنیت","Security","/admin/system-health","⌾"],
    ["بکاپ و بازیابی","Backup & Restore","/admin/backups","⟲"],
    ["تنظیمات","Settings","/admin/settings","⚙"]
  ]}
] as const;

export function Shell({children,active="/admin"}:{children:React.ReactNode;active?:string}){
  const {pick}=useI18n();
  const [mobileOpen,setMobileOpen]=useState(false);
  const navCenterStyle:React.CSSProperties=mobileOpen
    ? {position:"static",maxWidth:"none"}
    : {position:"absolute",left:"50%",top:"50%",transform:"translate(-50%,-50%)",maxWidth:"calc(100% - 320px)"};

  return <div className={`shell admin-shell admin-top-shell ${mobileOpen?"mobile-menu-open":""}`}>
    <div className="admin-topbar">
      <div className="admin-topbar-inner">
        <div className="admin-topbar-brand"><BrandMark/></div>

        <div style={navCenterStyle}>
          <nav className="admin-topnav" aria-label={pick("منوی اصلی","Main navigation")}>{menuGroups.map(group=>{
            const groupActive=group.items.some(([, ,href])=>active===href);
            return <details className={`topnav-group ${groupActive?"active":""}`} key={group.en}>
              <summary className="topnav-group-trigger">
                <span>{pick(group.fa,group.en)}</span>
                <span className="topnav-chevron" aria-hidden="true">⌄</span>
              </summary>
              <div className="topnav-menu">
                <div className="topnav-menu-head">{pick(group.fa,group.en)}</div>
                <div className="topnav-menu-grid">
                  {group.items.map(([fa,en,h,i])=>{
                    const label=pick(fa,en);
                    return <Link key={h} href={h} className={active===h?"active":""} onClick={()=>setMobileOpen(false)}>
                      <i>{i}</i><span className="nav-label">{label}</span>{h==="/admin/support"&&<SupportUnreadBadge active={active===h}/>}{h==="/admin/payments"&&<PaymentReviewBadge/>}
                    </Link>;
                  })}
                </div>
                {group.en==="System & Maintenance"&&<div className="topnav-release"><SystemReleaseFooter/></div>}
              </div>
            </details>;
          })}</nav>
        </div>

        <button className="admin-mobile-menu-toggle" type="button" onClick={()=>setMobileOpen(v=>!v)} aria-expanded={mobileOpen} aria-label={pick("نمایش منو","Show menu")}>☰</button>
      </div>
    </div>

    <main>
      <header className="admin-commandbar">
        <div className="search">⌕ <input placeholder={pick("جستجو در پنل...","Search panel...")}/></div>
        <div className="head-actions"><LanguageSwitch compact/><ThemeSwitch compact/><AdminNotificationCenter/><span className="avatar">M</span></div>
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
