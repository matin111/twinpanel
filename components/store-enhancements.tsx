"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";
import {useI18n} from "../lib/i18n";

type Platform="windows"|"android"|"ios"|"macos"|"linux";
type Protocol="cisco"|"openvpn"|"wireguard"|"l2tp"|"xray";

type Guide={client:string;credential:string;image?:string;download?:string;downloadLabel:string;warning?:string;steps:string[];fixes:string[]};

const platforms:[Platform,string][]=[["windows","Windows"],["android","Android"],["ios","iPhone / iPad"],["macos","macOS"],["linux","Linux"]];
const protocols:[Protocol,string][]=[["cisco","Cisco / OpenConnect"],["openvpn","OpenVPN"],["wireguard","WireGuard"],["l2tp","L2TP / IPsec"],["xray","V2Ray / Xray"]];

const commonFixes=["اطلاعات Server، Username، Password، PSK یا Subscription را فقط از پنل خودت کپی کن.","اگر اتصال قدیمی داری آن را حذف کن و کانفیگ جدید را دوباره وارد کن.","در صورت خطا، یک بار شبکه را عوض کن و دوباره تست کن."];

const guides:Record<Protocol,Record<Platform,Guide>>={
  cisco:{
    windows:{client:"OpenConnect GUI / Cisco Secure Client",credential:"Server + Username + Password",image:"/learning/apps/openconnect.png",download:"/downloads/apps/windows/cisco/",downloadLabel:"دانلود کلاینت Windows",steps:["کلاینت OpenConnect یا Cisco Secure Client را نصب کن.","از پنل کاربری آدرس Server، Username و Password را بردار.","یک Profile جدید بساز و Server را وارد کن.","Connect را بزن و Username/Password حساب را وارد کن."],fixes:commonFixes},
    android:{client:"OpenConnect",credential:"Server + Username + Password",image:"/learning/apps/openconnect.png",download:"/downloads/apps/android/openconnect/OpenConnect-1.12-Android.apk",downloadLabel:"دانلود آفلاین OpenConnect 1.12",steps:["APK را از همین سایت دانلود و نصب کن.","داخل برنامه یک Profile جدید بساز.","Server، Username و Password را از پنل کپی کن.","Profile را ذخیره و اتصال را فعال کن."],fixes:commonFixes},
    ios:{client:"Cisco Secure Client",credential:"Server + Username + Password",image:"/learning/apps/cisco.png",download:"https://apps.apple.com/us/app/cisco-secure-client/id1135064690",downloadLabel:"دریافت از App Store",steps:["Cisco Secure Client را نصب کن.","Connection جدید بساز و Server را وارد کن.","Username و Password حساب را وارد کن.","اجازه ساخت VPN را تأیید و اتصال را فعال کن."],fixes:commonFixes},
    macos:{client:"Cisco Secure Client / OpenConnect",credential:"Server + Username + Password",image:"/learning/apps/cisco.png",download:"/downloads/apps/macos/cisco/",downloadLabel:"دانلود کلاینت macOS",steps:["کلاینت را نصب کن.","Server را از پنل بردار و Connection بساز.","Username و Password را وارد کن.","اتصال را فعال و IP را بررسی کن."],fixes:commonFixes},
    linux:{client:"OpenConnect",credential:"Server + Username + Password",image:"/learning/apps/openconnect.png",download:"https://www.infradead.org/openconnect/",downloadLabel:"راهنمای OpenConnect",steps:["openconnect را از Package Manager نصب کن.","Server را از پنل کپی کن.","با openconnect به Server وصل شو.","Username و Password حساب را وارد کن."],fixes:commonFixes}
  },
  openvpn:{
    windows:{client:"OpenVPN Connect / Community",credential:"OVPN file + Username/Password",image:"/learning/apps/openvpn.png",download:"/downloads/apps/windows/openvpn/OpenVPN-2.7.6-Windows-amd64.msi",downloadLabel:"دانلود آفلاین OpenVPN 2.7.6",steps:["OpenVPN را از همین سایت نصب کن.","فایل OVPN اشتراک را از بخش اتصال دانلود کن.","فایل را Import کن.","در صورت درخواست، Username و Password حساب را وارد و Connect کن."],fixes:commonFixes},
    android:{client:"OpenVPN Connect",credential:"OVPN file + Username/Password",image:"/learning/apps/openvpn.png",download:"/downloads/apps/android/openvpn/",downloadLabel:"دانلود OpenVPN Android",steps:["OpenVPN Connect را نصب کن.","فایل OVPN را از پنل دانلود کن.","Import Profile را بزن و فایل را انتخاب کن.","Profile را فعال کن."],fixes:commonFixes},
    ios:{client:"OpenVPN Connect",credential:"OVPN file + Username/Password",image:"/learning/apps/openvpn.png",download:"https://apps.apple.com/us/app/openvpn-connect/id590379981",downloadLabel:"دریافت از App Store",steps:["OpenVPN Connect را نصب کن.","فایل OVPN را از پنل دانلود یا Share کن.","فایل را با OpenVPN باز و Import کن.","Connect را فعال کن."],fixes:commonFixes},
    macos:{client:"OpenVPN Connect",credential:"OVPN file + Username/Password",image:"/learning/apps/openvpn.png",download:"https://openvpn.net/connect-docs/connect-for-macos.html",downloadLabel:"OpenVPN برای macOS",steps:["OpenVPN Connect را نصب کن.","OVPN اشتراک را دانلود کن.","Profile را Import کن.","در صورت نیاز Username/Password را وارد و وصل شو."],fixes:commonFixes},
    linux:{client:"OpenVPN Community",credential:"OVPN file + Username/Password",image:"/learning/apps/openvpn.png",download:"https://openvpn.net/community/",downloadLabel:"OpenVPN Community",steps:["openvpn را نصب کن.","فایل OVPN را از پنل بگیر.","فایل را با openvpn اجرا کن.","در صورت درخواست Credential را وارد کن."],fixes:commonFixes}
  },
  wireguard:{
    windows:{client:"WireGuard",credential:"Config file or QR",image:"/learning/apps/wireguard.png",download:"/downloads/apps/windows/wireguard/WireGuard-Windows-amd64.msi",downloadLabel:"دانلود آفلاین WireGuard",steps:["WireGuard را نصب کن.","فایل کانفیگ را از پنل دانلود کن.","Import tunnel(s) from file را بزن.","Tunnel را Activate کن."],fixes:commonFixes},
    android:{client:"WireGuard",credential:"Config file or QR",image:"/learning/apps/wireguard.png",download:"/downloads/apps/android/wireguard/WireGuard-Android.apk",downloadLabel:"دانلود آفلاین WireGuard Android",steps:["APK WireGuard را نصب کن.","در بخش اتصال پنل QR یا فایل WireGuard را باز کن.","با + گزینه Scan QR یا Import file را انتخاب کن.","Tunnel را فعال کن."],fixes:commonFixes},
    ios:{client:"WireGuard",credential:"Config file or QR",image:"/learning/apps/wireguard.png",download:"https://apps.apple.com/us/app/wireguard/id1441195209",downloadLabel:"دریافت از App Store",steps:["WireGuard را نصب کن.","QR یا فایل را از پنل بگیر.","Create from QR code یا file را انتخاب کن.","Tunnel را فعال کن."],fixes:commonFixes},
    macos:{client:"WireGuard",credential:"Config file",image:"/learning/apps/wireguard.png",download:"https://www.wireguard.com/install/",downloadLabel:"WireGuard برای macOS",steps:["WireGuard را نصب کن.","فایل کانفیگ را دانلود کن.","Tunnel را Import کن.","Activate را بزن."],fixes:commonFixes},
    linux:{client:"WireGuard",credential:"Config file",image:"/learning/apps/wireguard.png",download:"https://www.wireguard.com/install/",downloadLabel:"راهنمای نصب WireGuard",steps:["wireguard-tools را نصب کن.","فایل کانفیگ را از پنل بگیر.","فایل را در مسیر مناسب قرار بده.","Tunnel را با wg-quick بالا بیاور."],fixes:commonFixes}
  },
  l2tp:{
    windows:{client:"VPN داخلی Windows",credential:"Server + Username + Password + PSK",downloadLabel:"بدون نصب برنامه",steps:["Settings > Network & Internet > VPN را باز کن.","Add VPN را بزن و نوع L2TP/IPsec with pre-shared key را انتخاب کن.","Server، Username، Password و PSK را از پنل وارد کن.","Save و سپس Connect را بزن."],fixes:commonFixes},
    android:{client:"VPN داخلی Android",credential:"Server + Username + Password + PSK",downloadLabel:"بدون نصب برنامه",warning:"در Android 12 و جدیدتر ممکن است L2TP در VPN داخلی وجود نداشته باشد؛ در این حالت OpenVPN یا V2Ray را استفاده کن.",steps:["Settings > VPN را باز کن.","در نسخه‌های پشتیبانی‌شده L2TP/IPsec PSK را انتخاب کن.","اطلاعات حساب را از پنل وارد کن.","Profile را ذخیره و Connect کن."],fixes:commonFixes},
    ios:{client:"VPN داخلی iPhone / iPad",credential:"Server + Account + Password + Secret",downloadLabel:"بدون نصب برنامه",steps:["Settings > General > VPN & Device Management > VPN را باز کن.","Add VPN Configuration و L2TP را انتخاب کن.","Server، Account، Password و Secret را وارد کن.","Done و سپس VPN را روشن کن."],fixes:commonFixes},
    macos:{client:"VPN داخلی macOS",credential:"Server + Account + Password + Shared Secret",downloadLabel:"بدون نصب برنامه",steps:["System Settings > VPN را باز کن.","VPN Configuration جدید برای L2TP/IPsec بساز.","Server، Account، Password و Shared Secret را وارد کن.","Save و Connect کن."],fixes:commonFixes},
    linux:{client:"NetworkManager L2TP",credential:"Gateway + Username + Password + PSK",download:"https://github.com/nm-l2tp/NetworkManager-l2tp",downloadLabel:"NetworkManager-l2tp",steps:["NetworkManager L2TP را نصب کن.","VPN جدید از نوع L2TP بساز.","Gateway و Credential را از پنل وارد کن.","IPsec PSK را تنظیم و اتصال را فعال کن."],fixes:commonFixes}
  },
  xray:{
    windows:{client:"v2rayN",credential:"Subscription URL or VLESS/VMess/Trojan link",image:"/learning/apps/v2rayn.png",download:"/downloads/apps/windows/v2rayn/v2rayN-windows-64-desktop.zip",downloadLabel:"دانلود آفلاین v2rayN Windows",steps:["فایل v2rayN را دانلود و اجرا کن.","Subscription Link را از پنل کاربری کپی کن.","Subscription group جدید بساز و لینک را وارد کن.","Update subscription را بزن، سرور را انتخاب و System Proxy را فعال کن."],fixes:commonFixes},
    android:{client:"v2rayNG",credential:"Subscription URL or VLESS/VMess/Trojan link",image:"/learning/apps/v2rayng.png",download:"/downloads/apps/android/v2rayng/v2rayNG-android-arm64.apk",downloadLabel:"دانلود آفلاین v2rayNG Android",steps:["APK v2rayNG را نصب کن.","Subscription Link را از پنل کپی کن.","Subscription group را اضافه و Update کن.","یک سرور را انتخاب و اتصال را روشن کن."],fixes:commonFixes},
    ios:{client:"Streisand / compatible client",credential:"Subscription URL",image:"/learning/apps/hiddify.png",download:"https://apps.apple.com/tr/app/streisand/id6450534064",downloadLabel:"دریافت Streisand",steps:["کلاینت سازگار را نصب کن.","Subscription Link را از پنل کپی کن.","Subscription را Import کن.","سرور را انتخاب و اتصال را فعال کن."],fixes:commonFixes},
    macos:{client:"v2rayN / Hiddify",credential:"Subscription URL",image:"/learning/apps/v2rayn.png",download:"/downloads/apps/macos/v2rayn/v2rayN-macos-arm64.dmg",downloadLabel:"دانلود v2rayN Apple Silicon",warning:"برای Mac Intel نسخه Intel را از Download Center پایین همین بخش بگیر.",steps:["نسخه متناسب با پردازنده را نصب کن.","Subscription Link را کپی کن.","Subscription را اضافه و Update کن.","سرور را انتخاب و Proxy را فعال کن."],fixes:commonFixes},
    linux:{client:"v2rayN",credential:"Subscription URL",image:"/learning/apps/v2rayn.png",download:"/downloads/apps/linux/v2rayn/v2rayN-linux-amd64.deb",downloadLabel:"دانلود v2rayN Linux amd64",steps:["پکیج متناسب با معماری را نصب کن.","Subscription Link را از پنل کپی کن.","Subscription را اضافه و Update کن.","سرور را انتخاب و Proxy را فعال کن."],fixes:commonFixes}
  }
};

const offlineDownloads=[
  ["Windows","v2rayN 64-bit","/downloads/apps/windows/v2rayn/v2rayN-windows-64-desktop.zip"],
  ["Windows","WireGuard 64-bit","/downloads/apps/windows/wireguard/WireGuard-Windows-amd64.msi"],
  ["Windows","OpenVPN 2.7.6","/downloads/apps/windows/openvpn/OpenVPN-2.7.6-Windows-amd64.msi"],
  ["Android","v2rayNG arm64","/downloads/apps/android/v2rayng/v2rayNG-android-arm64.apk"],
  ["Android","WireGuard","/downloads/apps/android/wireguard/WireGuard-Android.apk"],
  ["Android","OpenConnect 1.12","/downloads/apps/android/openconnect/OpenConnect-1.12-Android.apk"],
  ["macOS","v2rayN Apple Silicon","/downloads/apps/macos/v2rayn/v2rayN-macos-arm64.dmg"],
  ["macOS","v2rayN Intel","/downloads/apps/macos/v2rayn/v2rayN-macos-intel.dmg"],
  ["Linux","v2rayN amd64","/downloads/apps/linux/v2rayn/v2rayN-linux-amd64.deb"],
  ["Linux","v2rayN arm64","/downloads/apps/linux/v2rayn/v2rayN-linux-arm64.deb"]
] as const;

export function StoreEnhancements(){
  const pathname=usePathname();const {pick}=useI18n();
  const [header,setHeader]=useState<Element|null>(null);const [hero,setHero]=useState<Element|null>(null);const [guideHost,setGuideHost]=useState<Element|null>(null);
  const [platform,setPlatform]=useState<Platform>("windows");const [protocol,setProtocol]=useState<Protocol>("cisco");
  const isStore=pathname==="/"||pathname==="/store";
  useEffect(()=>{
    if(!isStore){setHeader(null);setHero(null);setGuideHost(null);return;}
    const timer=window.setTimeout(()=>{setHeader(document.querySelector(".store-actions"));setHero(document.querySelector(".hero-product-card"));setGuideHost(document.getElementById("guides"));},50);
    return()=>window.clearTimeout(timer);
  },[isStore]);
  const guide=useMemo(()=>guides[protocol][platform],[protocol,platform]);
  if(!isStore)return null;
  return <>
    {header&&createPortal(<Link className="ghost store-desktop-register" href="/register">{pick("ثبت‌نام","Register")}</Link>,header)}
    {hero&&createPortal(<div className="store-account-cta"><Link className="ghost xl" href="/login">{pick("ورود","Sign in")}</Link><Link className="primary xl" href="/register">{pick("ساخت حساب","Create account")}</Link></div>,hero)}
    {guideHost&&createPortal(<section className="legacy-guide-center">
      <div className="legacy-guide-head"><div><small>{pick("مرکز آموزش کامل","COMPLETE SETUP CENTER")}</small><h3>{pick("آموزش‌های پنل قبلی + دانلود مستقیم برنامه‌ها","Legacy guides with direct app downloads")}</h3><p>{pick("سیستم‌عامل و پروتکل را انتخاب کن؛ اطلاعات لازم، مراحل نصب، اتصال و عیب‌یابی را یکجا می‌بینی.","Choose your platform and protocol to see client, credentials, setup steps and troubleshooting.")}</p></div><Link className="primary" href="/panel/connection">{pick("دریافت اطلاعات اکانت","Get account details")}</Link></div>
      <div className="legacy-guide-tabs"><div>{platforms.map(([id,label])=><button className={platform===id?"active":""} key={id} onClick={()=>setPlatform(id)}>{label}</button>)}</div><div>{protocols.map(([id,label])=><button className={protocol===id?"active":""} key={id} onClick={()=>setProtocol(id)}>{label}</button>)}</div></div>
      <div className="legacy-guide-layout"><article className="legacy-client-card"><div className="legacy-client-logo">{guide.image?<img src={guide.image} alt={guide.client} onError={e=>{e.currentTarget.style.display="none"}}/>:<span>VPN</span>}</div><small>{pick("کلاینت پیشنهادی","Recommended client")}</small><h4>{guide.client}</h4><div className="legacy-credential"><small>{pick("اطلاعات لازم از حساب","Required account data")}</small><code>{guide.credential}</code></div>{guide.warning&&<div className="legacy-warning">{guide.warning}</div>}{guide.download?<a className="primary full" href={guide.download} target="_blank" rel="noreferrer">↓ {guide.downloadLabel}</a>:<span className="legacy-no-download">{guide.downloadLabel}</span>}</article><article className="legacy-steps"><div className="card-head"><b>{pick("از نصب تا اتصال موفق","From install to connected")}</b><span>{guide.steps.length.toLocaleString("fa-IR")} {pick("مرحله","steps")}</span></div>{guide.steps.map((s,i)=><div key={s}><i>{String(i+1).padStart(2,"0")}</i><p>{s}</p></div>)}</article><aside className="legacy-fixes"><b>{pick("اگر وصل نشد","If it does not connect")}</b>{guide.fixes.map(f=><p key={f}>✓ {f}</p>)}</aside></div>
      <div className="offline-download-center"><div className="card-head"><div><b>{pick("دانلود آفلاین برنامه‌ها","Offline app downloads")}</b><small>{pick("فایل‌ها از دامنه Subscription همین نصب سرو می‌شوند.","Files are served from this installation's subscription domain.")}</small></div></div><div className="offline-download-grid">{offlineDownloads.map(([os,name,url])=><a key={url} href={url} target="_blank" rel="noreferrer"><span>{os}</span><b>{name}</b><small>↓ {pick("دانلود مستقیم","Direct download")}</small></a>)}</div></div>
    </section>,guideHost)}
  </>;
}
