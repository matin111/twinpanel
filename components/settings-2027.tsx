"use client";

import {Badge,Card,PageHead,Shell} from "./ui";
import {useI18n} from "../lib/i18n";
import {ThemeSwitch,useTheme} from "../lib/theme";

export function SettingsPage2027(){
  const {pick}=useI18n();
  const {mode,resolved}=useTheme();
  return <Shell active="/admin/settings"><div className="page">
    <PageHead title={pick("تنظیمات سیستم","System Settings")} sub={pick("ظاهر، امنیت، رفتار عمومی و تنظیمات مدیریتی TwinPanel","Appearance, security and global TwinPanel behavior")}/>
    <div className="settings settings2027">
      <Card className="settings-nav"><button className="active">{pick("ظاهر","Appearance")}</button><button>{pick("عمومی","General")}</button><button>{pick("امنیت","Security")}</button><button>{pick("اعلان‌ها","Notifications")}</button><button>{pick("درگاه پرداخت","Payments")}</button><button>{pick("سرویس‌ها","Services")}</button></Card>
      <div className="module-grid">
        <Card><div className="card-head"><div><b>{pick("حالت نمایش","Appearance mode")}</b><small>{pick("تغییر در تمام صفحات و ذخیره خودکار","Applies everywhere and is saved automatically")}</small></div><Badge tone="violet">{mode.toUpperCase()} · {resolved}</Badge></div><div className="theme-setting-panel"><ThemeSwitch/><div><b>{pick("دارک، لایت یا هماهنگ با سیستم","Dark, light or follow system")}</b><p className="muted">{pick("دارک‌مود کم‌فشار و لایت‌مود روشن بدون سفید زننده.","Low-glare dark mode and a soft light mode without harsh white surfaces.")}</p></div></div></Card>
        <Card><h3>{pick("رنگ و حرکت","Color & motion")}</h3><div className="setting-grid"><div><label>{pick("رنگ Accent","Accent color")}</label><div className="swatches"><i className="violet active"/><i className="blue"/><i className="green"/><i className="amber"/></div></div><div><label>{pick("تراکم رابط","Interface density")}</label><div className="segments"><button>{pick("فشرده","Compact")}</button><button className="active">{pick("متعادل","Comfortable")}</button><button>{pick("باز","Spacious")}</button></div></div></div><label className="toggle"><span>{pick("انیمیشن‌های نرم","Soft animations")}</span><input type="checkbox" defaultChecked/><i/></label><label className="toggle"><span>{pick("کاهش حرکت بر اساس سیستم","Respect reduced motion")}</span><input type="checkbox" defaultChecked/><i/></label></Card>
        <Card><h3>{pick("تنظیمات عمومی","General settings")}</h3><div className="module-grid two"><label className="field"><span>{pick("نام محصول","Product name")}</span><input defaultValue="TwinPanel"/></label><label className="field"><span>{pick("منطقه زمانی","Timezone")}</span><select defaultValue="Asia/Tehran"><option>Asia/Tehran</option><option>Europe/Amsterdam</option><option>UTC</option></select></label></div><div className="action-row"><button className="primary">{pick("ذخیره تنظیمات","Save settings")}</button></div></Card>
      </div>
    </div>
  </div></Shell>;
}
