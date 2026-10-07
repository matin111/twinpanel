"use client";

import {Badge,Card,PageHead,Shell,Stat} from "./ui";
import {useI18n} from "../lib/i18n";

function Toggle({label,defaultChecked=true}:{label:string;defaultChecked?:boolean}){
  return <label className="toggle module-toggle"><span>{label}</span><input type="checkbox" defaultChecked={defaultChecked}/><i/></label>;
}

function ServiceRow({name,meta,status="ok"}:{name:string;meta:string;status?:"ok"|"warn"|"bad"}){
  return <div className="module-row"><span className="module-icon">◈</span><div className="grow"><b>{name}</b><small>{meta}</small></div><Badge tone={status}>{status==="ok"?"Online":status==="warn"?"Attention":"Offline"}</Badge></div>;
}

export function DomainsPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/domains"><div className="page">
    <PageHead title={pick("دامنه و SSL","Domains & SSL")} sub={pick("مدیریت دامنه‌ها، صدور گواهی و مسیرهای عمومی سرویس","Manage domains, certificates and public service routing")} action={pick("دامنه جدید","Add domain")}/>
    <div className="stats"><Stat label={pick("دامنه فعال","Active domains")} value="3" delta="SSL OK"/><Stat label={pick("گواهی معتبر","Valid certificates")} value="3 / 3" delta="100%"/><Stat label={pick("نیاز به تمدید","Renew soon")} value="1" delta={pick("۲۱ روز","21 days")}/><Stat label={pick("Nginx","Nginx")} value="Online" delta="config valid"/></div>
    <Card><div className="card-head"><div><b>{pick("دامنه‌های متصل","Connected domains")}</b><small>{pick("API، فروشگاه و لینک اشتراک","API, storefront and subscription endpoints")}</small></div></div>
      {[['api.example.com','API · 443','ok'],['panel.example.com','Web · 443','ok'],['sub.example.com','Subscription · 2096','warn']].map(([d,m,s])=><div className="module-row" key={d}><span className="module-icon">⌘</span><div className="grow"><b>{d}</b><small>{m}</small></div><Badge tone={s as "ok"|"warn"}>{s==="ok"?pick("SSL معتبر","SSL valid"):pick("تمدید نزدیک","Renew soon")}</Badge><button className="mini-btn">{pick("مدیریت","Manage")}</button></div>)}
    </Card>
    <div className="module-grid two"><Card><h3>{pick("صدور / تمدید SSL","Issue / renew SSL")}</h3><p className="muted">Let's Encrypt · ACME</p><label className="field"><span>{pick("دامنه","Domain")}</span><input defaultValue="panel.example.com"/></label><div className="action-row"><button className="primary">{pick("صدور گواهی","Issue certificate")}</button><button className="ghost">{pick("بررسی Nginx","Validate Nginx")}</button></div></Card><Card><h3>{pick("مسیریابی عمومی","Public routing")}</h3><Toggle label={pick("اجبار HTTPS","Force HTTPS")}/><Toggle label={pick("ریدایرکت www","Redirect www")} defaultChecked={false}/><Toggle label={pick("HSTS","HSTS")}/></Card></div>
  </div></Shell>;
}

export function ProvisionPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/provision"><div className="page"><PageHead title={pick("راه‌اندازی و Provision","Provisioning")} sub={pick("نصب، تعمیر، ارتقا Agent و بررسی سلامت نودها","Install, repair and upgrade node agents")} action={pick("نود جدید","Provision node")}/>
    <div className="stats"><Stat label={pick("Agent فعال","Agents online")} value="5 / 5" delta="100%"/><Stat label={pick("نسخه Agent","Agent version")} value="0.9.7" delta={pick("آخرین نسخه","Latest")}/><Stat label={pick("Fabric سالم","Healthy fabric")} value="4" delta="OK"/><Stat label={pick("نیاز به اقدام","Needs action")} value="1" delta={pick("بررسی","Review")}/></div>
    <div className="module-grid two"><Card><h3>{pick("Preflight نود","Node preflight")}</h3><label className="field"><span>IP / Host</span><input placeholder="203.0.113.10"/></label><label className="field"><span>SSH Port</span><input defaultValue="22"/></label><div className="action-row"><button className="primary">{pick("تست اتصال","Test connection")}</button><button className="ghost">{pick("بررسی پیش‌نیازها","Run preflight")}</button></div></Card><Card><h3>{pick("عملیات Agent","Agent operations")}</h3><ServiceRow name="DE-01" meta="Agent 0.9.7 · Ubuntu 24.04"/><div className="action-row"><button className="ghost">{pick("تعمیر","Repair")}</button><button className="ghost">{pick("ری‌استارت","Restart")}</button><button className="primary">{pick("ارتقا","Upgrade")}</button></div></Card></div>
    <Card><div className="card-head"><div><b>{pick("وضعیت Fabric","Fabric status")}</b><small>{pick("مسیرهای فعال بین نودهای ایران و خروجی","Active paths between Iran and exit nodes")}</small></div></div>{['IR-01 → DE-01','IR-02 → NL-01','IR-03 → TR-01'].map((x,i)=><ServiceRow key={x} name={x} meta={`Transport #${i+1} · ${82+i*9}ms`} status={i===2?"warn":"ok"}/>)}</Card>
  </div></Shell>;
}

export function TelegramManagerPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/telegram-manager"><div className="page"><PageHead title={pick("مدیریت تلگرام","Telegram Manager")} sub={pick("لینک کاربران، Sessionها، وضعیت Botها و اتصال به سرویس‌ها","User links, sessions and bot connectivity")}/>
    <div className="module-grid two"><Card><h3>{pick("وضعیت اتصال","Connection status")}</h3><ServiceRow name="Telegram API" meta="Session healthy · last touch 20s"/><ServiceRow name="Purchase Bot" meta="Polling active"/><ServiceRow name="Support Bot" meta="Polling active"/><ServiceRow name="Wallet Bot" meta="Polling active"/></Card><Card><h3>{pick("لینک کاربری","User link")}</h3><label className="field"><span>{pick("شناسه کاربر","User ID")}</span><input placeholder="User #1024"/></label><label className="field"><span>Telegram ID</span><input placeholder="123456789"/></label><div className="action-row"><button className="primary">{pick("اتصال حساب","Link account")}</button><button className="ghost">{pick("بررسی وضعیت","Check status")}</button></div></Card></div>
    <Card><div className="card-head"><b>{pick("Sessionهای اخیر","Recent sessions")}</b></div>{[['@user_one','Active','2m'],['@reseller_one','Active','8m'],['@support_agent','Idle','24m']].map(x=><div className="module-row" key={x[0]}><span className="module-icon">✈</span><div className="grow"><b>{x[0]}</b><small>{x[2]}</small></div><Badge tone={x[1]==='Active'?"ok":"warn"}>{x[1]}</Badge></div>)}</Card>
  </div></Shell>;
}

export function SmsReaderPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/sms-reader"><div className="page"><PageHead title="SMS Reader" sub={pick("دریافت پیامک پرداخت، Pair دستگاه‌ها و Relay امن","Payment SMS ingestion, device pairing and secure relay")}/>
    <div className="stats"><Stat label={pick("دستگاه متصل","Connected devices")} value="5" delta="Online"/><Stat label={pick("پیامک امروز","SMS today")} value="42" delta="+8"/><Stat label={pick("تطبیق موفق","Matched payments")} value="39" delta="92.8%"/><Stat label={pick("Pair Code فعال","Active pair codes")} value="2" delta="5m TTL"/></div>
    <div className="module-grid two"><Card><h3>{pick("ساخت Pair Code","Create pair code")}</h3><p className="muted">{pick("کد موقت برای اتصال اپ SMS Reader","Temporary code for pairing SMS Reader app")}</p><div className="pair-code">TP-483-291</div><div className="action-row"><button className="primary">{pick("کد جدید","Generate new")}</button><button className="ghost">{pick("لغو همه","Revoke all")}</button></div></Card><Card><h3>{pick("Relay","Relay")}</h3><ServiceRow name="Payment SMS Relay" meta="Authenticated · 18ms"/><Toggle label={pick("پذیرش فقط دستگاه‌های Pair شده","Only paired devices")}/><Toggle label={pick("تطبیق خودکار پرداخت","Automatic payment matching")}/></Card></div>
    <Card><div className="card-head"><b>{pick("دستگاه‌ها","Devices")}</b></div>{['Samsung A54','Pixel 8','Xiaomi 13'].map((x,i)=><ServiceRow key={x} name={x} meta={`Device #${i+1} · seen ${i*3+1}m ago`}/>)}</Card>
  </div></Shell>;
}

export function AccountDeliveryPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/account-delivery"><div className="page"><PageHead title={pick("تحویل اکانت","Account Delivery")} sub={pick("فایل اتصال، QR، لینک عمومی و سیاست تحویل پروتکل‌ها","Connection files, QR codes and delivery policy")}/>
    <div className="module-grid two"><Card><h3>{pick("سیاست تحویل","Delivery policy")}</h3><Toggle label="Cisco / OpenConnect"/><Toggle label="OpenVPN"/><Toggle label="WireGuard"/><Toggle label="V2Ray / Xray"/><Toggle label="L2TP"/><label className="field"><span>{pick("اعتبار لینک عمومی","Public link TTL")}</span><select defaultValue="24"><option value="1">1 hour</option><option value="24">24 hours</option><option value="72">72 hours</option></select></label></Card><Card><h3>{pick("پیش‌نمایش کاربر","User delivery preview")}</h3><label className="field"><span>{pick("اشتراک","Subscription")}</span><input defaultValue="#1024 · Ali Rezaei"/></label><div className="delivery-preview"><div className="qr-placeholder">QR</div><div><b>sub.example.com/c/••••••</b><small>{pick("لینک امضاشده و زمان‌دار","Signed expiring link")}</small></div></div><div className="action-row"><button className="primary">{pick("ساخت لینک","Generate link")}</button><button className="ghost">{pick("دانلود فایل","Download file")}</button></div></Card></div>
    <Card><div className="card-head"><b>{pick("تحویل‌های اخیر","Recent deliveries")}</b></div>{['WireGuard config','OpenVPN profile','V2Ray subscription'].map((x,i)=><ServiceRow key={x} name={x} meta={`User #10${24-i} · ${i*5+2}m ago`}/>)}</Card>
  </div></Shell>;
}

export function VpnSettingsPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/vpn-settings"><div className="page"><PageHead title={pick("تنظیمات VPN","VPN Settings")} sub={pick("فعال‌سازی پروتکل‌ها و تنظیمات عمومی سرویس","Protocol availability and global service settings")}/>
    <div className="module-grid two"><Card><h3>{pick("پروتکل‌ها","Protocols")}</h3><Toggle label="Cisco / OpenConnect"/><Toggle label="OpenVPN"/><Toggle label="WireGuard"/><Toggle label="V2Ray / Xray"/><Toggle label="L2TP"/></Card><Card><h3>L2TP</h3><label className="field"><span>UDP 500 / 4500</span><input defaultValue="enabled"/></label><label className="field"><span>{pick("MTU پیش‌فرض","Default MTU")}</span><input defaultValue="1380"/></label><Toggle label={pick("مسیریابی از تونل","Route through tunnel")}/><div className="action-row"><button className="primary">{pick("ذخیره تنظیمات","Save settings")}</button></div></Card></div>
    <Card><h3>{pick("سیاست اتصال","Connection policy")}</h3><div className="setting-grid"><div><label>{pick("Failover","Failover")}</label><div className="segments"><button className="active">Auto</button><button>Manual</button></div></div><div><label>{pick("Health interval","Health interval")}</label><div className="segments"><button>15s</button><button className="active">30s</button><button>60s</button></div></div></div></Card>
  </div></Shell>;
}

export function MotherAccessPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/mother-access"><div className="page"><PageHead title={pick("دسترسی مادر","Mother Access")} sub={pick("کلیدهای دسترسی کنترل‌شده برای نودها و عملیات مدیریتی","Controlled access keys for nodes and management operations")}/>
    <div className="module-grid two"><Card><h3>{pick("کلید Agent","Agent key")}</h3><div className="secret-field"><input type="password" value="••••••••••••••••" readOnly/><button>{pick("چرخش کلید","Rotate")}</button></div><p className="muted">{pick("کلید عمومی امضای فرمان‌ها در نودها توزیع می‌شود.","Command verification public key is distributed to nodes.")}</p><div className="action-row"><button className="primary">{pick("ساخت کلید جدید","Generate new key")}</button></div></Card><Card><h3>{pick("محدوده دسترسی","Access scope")}</h3><Toggle label={pick("نصب Agent","Install agent")}/><Toggle label={pick("Repair / Restart","Repair / Restart")}/><Toggle label={pick("اجرای فرمان حساس","Sensitive commands")} defaultChecked={false}/></Card></div>
    <Card><div className="card-head"><b>{pick("دسترسی نودها","Node access")}</b></div>{['IR-01','DE-01','NL-01','TR-01'].map(x=><ServiceRow key={x} name={x} meta="Signed agent identity · SSH managed"/>)}</Card>
  </div></Shell>;
}

export function BrandingPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/branding"><div className="page"><PageHead title={pick("برندینگ","Branding")} sub={pick("نام، لوگو، رنگ Accent و اطلاعات عمومی محصول","Product identity, logo and public brand settings")}/>
    <div className="module-grid two"><Card><h3>{pick("هویت برند","Brand identity")}</h3><label className="field"><span>{pick("نام عمومی","Public name")}</span><input defaultValue="TwinPanel"/></label><label className="field"><span>{pick("نام کوتاه","Short name")}</span><input defaultValue="Twin"/></label><label className="field"><span>{pick("لینک پشتیبانی","Support link")}</span><input defaultValue="https://t.me/support"/></label><div className="action-row"><button className="primary">{pick("ذخیره","Save")}</button></div></Card><Card><h3>{pick("ظاهر","Appearance")}</h3><div className="brand-preview"><img src="/logo.svg" alt="TwinPanel"/><div><b>TwinPanel</b><small>VPN CONTROL 2027</small></div></div><label className="field"><span>{pick("رنگ Accent","Accent color")}</span><input type="color" defaultValue="#7c3aed"/></label><button className="ghost">{pick("آپلود لوگو","Upload logo")}</button></Card></div>
  </div></Shell>;
}
