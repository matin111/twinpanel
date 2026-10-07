"use client";

import {Badge,Card,PageHead,Shell,Stat} from "./ui";
import {useI18n} from "../lib/i18n";

function Toggle({label,checked=true}:{label:string;checked?:boolean}){
  return <label className="toggle module-toggle"><span>{label}</span><input type="checkbox" defaultChecked={checked}/><i/></label>;
}

export function L2tpSettingsPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/l2tp"><div className="page">
    <PageHead title="L2TP / IPsec" sub={pick("مدیریت مستقل پروتکل L2TP، پارامترهای IPsec، آدرس‌دهی و سلامت سرویس","Manage L2TP, IPsec parameters, address pools and service health")}/>

    <div className="stats">
      <Stat label={pick("وضعیت سرویس","Service status")} value={pick("آنلاین","Online")} delta="L2TP / IPsec" icon="◎"/>
      <Stat label={pick("کاربر آنلاین","Online users")} value="126" delta="LIVE" icon="◉"/>
      <Stat label={pick("نود فعال","Enabled nodes")} value="4 / 5" delta={pick("۱ نود غیرفعال","1 disabled")} icon="▦"/>
      <Stat label={pick("میانگین Ping","Average ping")} value="91ms" delta={pick("پایدار","Stable")} icon="⌁"/>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("تنظیمات عمومی L2TP","General L2TP settings")}</b><small>{pick("فعال‌سازی و پارامترهای پایه سرویس","Service availability and base parameters")}</small></div><Badge>Online</Badge></div>
        <Toggle label={pick("فعال‌سازی L2TP برای ساخت اشتراک","Enable L2TP for subscriptions")}/>
        <Toggle label={pick("مسیریابی ترافیک از تانل","Route traffic through tunnel")}/>
        <Toggle label={pick("Failover خودکار","Automatic failover")}/>
        <label className="field"><span>{pick("MTU پیش‌فرض","Default MTU")}</span><input defaultValue="1380"/></label>
        <label className="field"><span>{pick("DNS کاربران","Client DNS")}</span><input defaultValue="1.1.1.1, 8.8.8.8"/></label>
      </Card>

      <Card>
        <div className="card-head"><div><b>IPsec</b><small>UDP 500 / 4500 · ESP</small></div><Badge tone="violet">IPsec</Badge></div>
        <label className="field"><span>{pick("کلید اشتراکی IPsec","IPsec pre-shared key")}</span><div className="secret-field"><input type="password" value="••••••••••••••••" readOnly/><button>{pick("تغییر","Change")}</button></div></label>
        <label className="field"><span>{pick("حالت احراز هویت","Authentication mode")}</span><select defaultValue="psk"><option value="psk">PSK + Username/Password</option><option value="cert">Certificate</option></select></label>
        <label className="field"><span>{pick("الگوریتم پیشنهادشده","Preferred proposal")}</span><select defaultValue="aes256"><option value="aes256">AES-256 / SHA-256</option><option value="aes128">AES-128 / SHA-256</option></select></label>
        <div className="action-row"><button className="primary">{pick("ذخیره تنظیمات","Save settings")}</button><button className="ghost">{pick("تست سرویس","Test service")}</button></div>
      </Card>
    </div>

    <div className="module-grid two">
      <Card>
        <h3>{pick("آدرس‌دهی کاربران","Client address pool")}</h3>
        <label className="field"><span>{pick("شبکه کاربران","Client subnet")}</span><input defaultValue="10.60.0.0/16"/></label>
        <label className="field"><span>{pick("شروع Pool","Pool start")}</span><input defaultValue="10.60.10.10"/></label>
        <label className="field"><span>{pick("پایان Pool","Pool end")}</span><input defaultValue="10.60.250.250"/></label>
        <Toggle label={pick("جلوگیری از ارتباط کاربران با یکدیگر","Client isolation")}/>
      </Card>

      <Card>
        <h3>{pick("سلامت و محدودیت","Health & limits")}</h3>
        <label className="field"><span>{pick("فاصله Health Check","Health check interval")}</span><select defaultValue="30"><option value="15">15s</option><option value="30">30s</option><option value="60">60s</option></select></label>
        <label className="field"><span>{pick("حداکثر Session هر اکانت","Max sessions per account")}</span><input defaultValue="1"/></label>
        <Toggle label={pick("قطع خودکار اشتراک منقضی","Disconnect expired subscriptions")}/>
        <Toggle label={pick("اعمال محدودیت حجم از Quota Core","Enforce Quota Core limits")}/>
      </Card>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("وضعیت L2TP روی نودها","L2TP node status")}</b><small>{pick("آمادگی سرویس در نودهای خروجی","Service readiness on exit nodes")}</small></div></div>
      {[['DE-01','Germany','Online','88ms'],['NL-01','Netherlands','Online','93ms'],['TR-01','Turkey','Online','101ms'],['AE-01','UAE','Online','86ms'],['SG-01','Singapore','Disabled','—']].map((x,i)=><div className="module-row" key={x[0]}><span className="module-icon">◎</span><div className="grow"><b>{x[0]}</b><small>{x[1]} · UDP 500/4500 · {x[3]}</small></div><Badge tone={i===4?"warn":"ok"}>{x[2]}</Badge><button className="mini-btn">{pick("مدیریت","Manage")}</button></div>)}
    </Card>
  </div></Shell>;
}
