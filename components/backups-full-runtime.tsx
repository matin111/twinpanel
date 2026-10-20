"use client";

import {ChangeEvent,useEffect,useMemo,useRef,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {BackupHome,BackupSettings,parityApi} from "../lib/admin-parity-api";
import {downloadBackupFile,downloadRecoveryKey,uploadBackup} from "../lib/backup-runtime-api";
import {useI18n} from "../lib/i18n";

const defaults:BackupSettings={enabled:false,frequency:"daily",hour:3,minute:0,weekday:0,timezone:"Asia/Tehran",send_telegram:false,telegram_chat_id:"",retention:14};
const str=(row:Record<string,unknown>,...keys:string[])=>{for(const key of keys){const v=row[key];if(v!==undefined&&v!==null)return String(v);}return "";};
const num=(row:Record<string,unknown>,...keys:string[])=>{for(const key of keys){const v=Number(row[key]);if(Number.isFinite(v))return v;}return 0;};
const fileName=(row:Record<string,unknown>)=>str(row,"filename","name","file")||"—";
const dateText=(value:unknown)=>{if(!value)return "—";const d=new Date(String(value));return Number.isNaN(d.getTime())?String(value):d.toLocaleString("fa-IR");};
const sizeText=(row:Record<string,unknown>)=>{const bytes=num(row,"size_bytes","size","bytes");if(!bytes)return "—";if(bytes>=1024**3)return `${(bytes/1024**3).toFixed(2)} GB`;if(bytes>=1024**2)return `${(bytes/1024**2).toFixed(1)} MB`;if(bytes>=1024)return `${(bytes/1024).toFixed(1)} KB`;return `${bytes} B`;};
const telegramOk=(row:Record<string,unknown>)=>Boolean(row.telegram_file_id||row.telegram_sent||row.sent_telegram)&&!row.telegram_error;

export function BackupsFullRuntimePage(){
  const {pick}=useI18n();
  const inputRef=useRef<HTMLInputElement>(null);
  const [home,setHome]=useState<BackupHome>({ok:true,backups:[],settings:defaults});
  const [settings,setSettings]=useState<BackupSettings>(defaults);
  const [info,setInfo]=useState<Record<string,unknown>|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const normalizeSettings=(value:BackupSettings):BackupSettings=>{
    const telegram_chat_id=String(value.telegram_chat_id||"").trim();
    return {
      ...defaults,
      ...value,
      telegram_chat_id,
      send_telegram:Boolean(value.send_telegram&&telegram_chat_id),
    };
  };

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const data=await parityApi.backups();
      const normalized=normalizeSettings({...defaults,...data.settings});
      setHome({...data,settings:normalized});
      setSettings(normalized);
    }
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const backups=home.backups||[];
  const totalBytes=useMemo(()=>backups.reduce((sum,row)=>sum+num(row,"size_bytes","size","bytes"),0),[backups]);
  const telegramCount=useMemo(()=>backups.filter(telegramOk).length,[backups]);

  const run=async(key:string,label:string,fn:()=>Promise<unknown>,reload=true)=>{
    if(busy)return;
    setBusy(key);setError("");setOk("");
    try{const result=await fn();setOk(label);if(key.startsWith("info:"))setInfo(result as Record<string,unknown>);if(reload)await load();}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const create=()=>void run("create",pick("بکاپ جدید ساخته شد","Backup created"),()=>parityApi.backupCreate(Boolean(settings.send_telegram&&settings.telegram_chat_id.trim())));
  const saveSettings=()=>{
    const normalized=normalizeSettings(settings);
    setSettings(normalized);
    void run("settings",pick("تنظیمات بکاپ ذخیره شد","Backup settings saved"),()=>parityApi.backupSettings(normalized));
  };
  const testTelegram=()=>{
    const chatId=settings.telegram_chat_id.trim();
    if(!chatId){setError(pick("ابتدا Telegram Chat ID را وارد کنید.","Enter the Telegram Chat ID first."));return;}
    void run("test-telegram",pick("ارسال آزمایشی Telegram موفق بود","Telegram test message sent"),()=>parityApi.backupVerifyTelegram(chatId),false);
  };
  const upload=async(event:ChangeEvent<HTMLInputElement>)=>{
    const file=event.target.files?.[0];event.target.value="";if(!file)return;
    if(!file.name.toLowerCase().endsWith(".tpbak")){setError(pick("فقط فایل .tpbak قابل آپلود است.","Only .tpbak files are accepted."));return;}
    await run("upload",pick("فایل بکاپ وارد شد","Backup file imported"),()=>uploadBackup(file));
  };

  const download=async(filename:string)=>{
    if(busy)return;setBusy(`download:${filename}`);setError("");setOk("");
    try{await downloadBackupFile(filename);setOk(pick("دانلود بکاپ شروع شد","Backup download started"));}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const recovery=async()=>{
    if(busy)return;setBusy("recovery");setError("");setOk("");
    try{await downloadRecoveryKey();setOk(pick("کلید بازیابی دانلود شد؛ آن را خارج از سرور نگه دارید.","Recovery key downloaded; store it off-server."));}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/backups"><div className="page">
    <div className="page-head"><div><h1>{pick("بکاپ و بازیابی","Backup & Restore")}</h1><small>{pick("بکاپ رمزگذاری‌شده، زمان‌بندی، Telegram، آپلود، دانلود و Restore","Encrypted backups, scheduling, Telegram, upload, download and restore")}</small></div><div className="action-row"><button className="ghost" disabled={Boolean(busy)} onClick={()=>inputRef.current?.click()}>{busy==="upload"?"…":pick("آپلود .tpbak","Upload .tpbak")}</button><input ref={inputRef} type="file" accept=".tpbak" hidden onChange={upload}/><button className="primary" disabled={Boolean(busy)} onClick={create}>{busy==="create"?"…":pick("ساخت بکاپ","Create backup")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats"><Stat label={pick("تعداد بکاپ","Backups")} value={String(backups.length)} icon="⟲"/><Stat label={pick("حجم کل","Total size")} value={totalBytes?sizeText({size_bytes:totalBytes}):"—"} icon="▤"/><Stat label={pick("ارسال Telegram","Telegram copies")} value={String(telegramCount)} icon="✈"/><Stat label={pick("Retention","Retention")} value={`${settings.retention} ${pick("نسخه","copies")}`} icon="⌛"/></div>

    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("کلید بازیابی","Recovery Key")}</b><small>{pick("بدون این کلید، بکاپ رمزگذاری‌شده روی سرور دیگر قابل Restore نیست.","Encrypted backups cannot be restored on another server without this key.")}</small></div><Badge tone="violet">{home.key_fingerprint?pick("فعال","Ready"):pick("نامشخص","Unknown")}</Badge></div><div className="runtime-info-list"><div><span>{pick("Fingerprint","Fingerprint")}</span><b dir="ltr">{home.key_fingerprint||"—"}</b></div><div><span>{pick("جداول داخل بکاپ","Included tables")}</span><b>{home.included_tables?.length??0}</b></div><div><span>{pick("جداول Runtime حذف‌شده","Excluded runtime tables")}</span><b>{home.excluded_runtime_tables?.length??0}</b></div></div><button className="ghost full" disabled={Boolean(busy)} onClick={()=>void recovery()}>{busy==="recovery"?"…":pick("دانلود کلید بازیابی","Download recovery key")}</button></Card>

      <Card><div className="card-head"><div><b>{pick("Telegram Backup","Telegram Backup")}</b><small>{pick("ارسال بکاپ با همان ربات اصلی Telegram پنل انجام می‌شود.","Backups are sent by the same primary Telegram bot used by the panel.")}</small></div><Badge tone="violet">{pick("ربات اصلی پنل","Main panel bot")}</Badge></div><label className="field"><span>Telegram Chat ID</span><input dir="ltr" value={settings.telegram_chat_id} onChange={e=>setSettings(v=>({...v,telegram_chat_id:e.target.value}))}/></label><label className="toggle module-toggle"><span>{pick("ارسال بکاپ‌های جدید به Telegram","Send new backups to Telegram")}</span><input type="checkbox" checked={settings.send_telegram} onChange={e=>setSettings(v=>({...v,send_telegram:e.target.checked}))}/><i/></label><div className="action-row"><button className="ghost" disabled={Boolean(busy)||!settings.telegram_chat_id.trim()} onClick={testTelegram}>{busy==="test-telegram"?"…":pick("تست Telegram","Test Telegram")}</button><button className="primary" disabled={Boolean(busy)} onClick={saveSettings}>{busy==="settings"?"…":pick("ذخیره","Save")}</button></div></Card>
    </div>

    <Card className="runtime-editor"><div className="card-head"><div><b>{pick("بکاپ خودکار","Automatic Backup")}</b><small>{pick("تنظیمات مستقیم در Backend ذخیره می‌شود","Saved directly in the backend")}</small></div><label className="toggle module-toggle"><span>{settings.enabled?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</span><input type="checkbox" checked={settings.enabled} onChange={e=>setSettings(v=>({...v,enabled:e.target.checked}))}/><i/></label></div><div className="setting-grid"><label className="field"><span>{pick("تکرار","Frequency")}</span><select value={settings.frequency} onChange={e=>setSettings(v=>({...v,frequency:e.target.value as BackupSettings["frequency"]}))}><option value="hourly">Hourly</option><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label><label className="field"><span>{pick("ساعت","Hour")}</span><input type="number" min={0} max={23} value={settings.hour} onChange={e=>setSettings(v=>({...v,hour:Number(e.target.value)}))}/></label><label className="field"><span>{pick("دقیقه","Minute")}</span><input type="number" min={0} max={59} value={settings.minute} onChange={e=>setSettings(v=>({...v,minute:Number(e.target.value)}))}/></label><label className="field"><span>{pick("روز هفته ۰ تا ۶","Weekday 0-6")}</span><input type="number" min={0} max={6} value={settings.weekday} onChange={e=>setSettings(v=>({...v,weekday:Number(e.target.value)}))}/></label><label className="field"><span>{pick("Timezone","Timezone")}</span><input dir="ltr" value={settings.timezone} onChange={e=>setSettings(v=>({...v,timezone:e.target.value}))}/></label><label className="field"><span>{pick("تعداد نگهداری","Retention")}</span><input type="number" min={1} max={100} value={settings.retention} onChange={e=>setSettings(v=>({...v,retention:Number(e.target.value)}))}/></label></div><button className="primary" disabled={Boolean(busy)} onClick={saveSettings}>{busy==="settings"?"…":pick("ذخیره زمان‌بندی","Save schedule")}</button></Card>

    <Card><div className="card-head"><div><b>{pick("فهرست بکاپ‌ها","Backup files")}</b><small>{pick("Restore فقط با تأیید صریح اجرا می‌شود.","Restore runs only after explicit confirmation.")}</small></div><button className="ghost" disabled={loading} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>{loading?<div className="runtime-loading">{pick("در حال دریافت بکاپ‌ها...","Loading backups...")}</div>:<div className="table"><table><thead><tr><th>{pick("فایل","File")}</th><th>{pick("نوع","Kind")}</th><th>{pick("حجم","Size")}</th><th>{pick("تاریخ","Created")}</th><th>Telegram</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{backups.map((raw,index)=>{const row=raw as Record<string,unknown>,name=fileName(row);return <tr key={name||index}><td dir="ltr">{name}</td><td>{str(row,"kind","type")||"—"}</td><td>{sizeText(row)}</td><td>{dateText(row.created_at||row.timestamp)}</td><td><Badge tone={row.telegram_error?"bad":telegramOk(row)?"ok":"warn"}>{row.telegram_error?pick("خطا","Error"):telegramOk(row)?pick("ارسال شده","Sent"):pick("ارسال نشده","Not sent")}</Badge></td><td><div className="row-actions"><button className="mini-btn" disabled={Boolean(busy)} onClick={()=>void run(`info:${name}`,pick("اطلاعات بکاپ دریافت شد","Backup info loaded"),()=>parityApi.backupInfo(name),false)}>{pick("Info","Info")}</button><button className="mini-btn" disabled={Boolean(busy)} onClick={()=>void download(name)}>{pick("دانلود","Download")}</button><button className="mini-btn" disabled={Boolean(busy)} onClick={()=>void run(`tg:${name}`,pick("بکاپ به Telegram ارسال شد","Backup sent to Telegram"),()=>parityApi.backupTelegram(name))}>{pick("Telegram","Telegram")}</button><button className="mini-btn danger" disabled={Boolean(busy)} onClick={()=>{const confirmText=window.prompt(pick("برای Restore عبارت RESTORE را وارد کنید","Type RESTORE to continue"),"");if(confirmText==="RESTORE")void run(`restore:${name}`,pick("Restore انجام شد","Restore completed"),()=>parityApi.backupRestore(name));}}>{pick("Restore","Restore")}</button><button className="mini-btn danger" disabled={Boolean(busy)} onClick={()=>{if(window.confirm(pick("این فایل بکاپ حذف شود؟","Delete this backup file?")))void run(`delete:${name}`,pick("بکاپ حذف شد","Backup deleted"),()=>parityApi.backupDelete(name));}}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>}{!loading&&!backups.length&&<div className="runtime-empty">{pick("بکاپی وجود ندارد.","No backups exist.")}</div>}</Card>

    {info&&<Card><div className="card-head"><b>{pick("جزئیات بکاپ","Backup details")}</b><button className="mini-btn" onClick={()=>setInfo(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(info,null,2)}</pre></Card>}
  </div></Shell>;
}
