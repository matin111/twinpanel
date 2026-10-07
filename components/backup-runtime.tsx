"use client";

import {ChangeEvent,useEffect,useRef,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {BackupHome,BackupSettings,parityApi} from "../lib/admin-parity-api";
import {downloadBackupFile,downloadRecoveryKey,uploadBackup} from "../lib/backup-runtime-api";
import {useI18n} from "../lib/i18n";

const DEFAULT_SETTINGS:BackupSettings={
  enabled:false,
  frequency:"daily",
  hour:3,
  minute:0,
  weekday:0,
  timezone:"Asia/Tehran",
  send_telegram:true,
  telegram_chat_id:"",
  retention:14
};

const text=(row:Record<string,unknown>,...keys:string[])=>{
  for(const key of keys){
    const value=row[key];
    if(value!==undefined&&value!==null&&value!=="")return String(value);
  }
  return "";
};

const formatDate=(value:unknown)=>{
  if(!value)return "—";
  const date=new Date(String(value));
  return Number.isNaN(date.getTime())?String(value):date.toLocaleString("fa-IR");
};

const formatSize=(value:unknown)=>{
  const bytes=Number(value||0);
  if(!Number.isFinite(bytes)||bytes<=0)return "—";
  if(bytes<1024)return `${bytes} B`;
  if(bytes<1024**2)return `${(bytes/1024).toFixed(1)} KB`;
  if(bytes<1024**3)return `${(bytes/1024**2).toFixed(1)} MB`;
  return `${(bytes/1024**3).toFixed(2)} GB`;
};

export function BackupRuntimePage(){
  const {pick}=useI18n();
  const uploadRef=useRef<HTMLInputElement|null>(null);
  const [home,setHome]=useState<BackupHome|null>(null);
  const [settings,setSettings]=useState<BackupSettings>(DEFAULT_SETTINGS);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [detail,setDetail]=useState("");

  const load=async()=>{
    setError("");
    try{
      const data=await parityApi.backups();
      setHome(data);
      setSettings({...DEFAULT_SETTINGS,...data.settings});
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }
  };

  useEffect(()=>{void load();},[]);

  const act=async(label:string,fn:()=>Promise<unknown>,refresh=true)=>{
    if(busy)return;
    setBusy(true);setError("");setOk("");
    try{
      const result=await fn();
      setOk(label);
      if(result&&typeof result==="object")setDetail(JSON.stringify(result,null,2));
      if(refresh)await load();
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      setBusy(false);
    }
  };

  const onUpload=async(event:ChangeEvent<HTMLInputElement>)=>{
    const file=event.target.files?.[0];
    event.target.value="";
    if(!file)return;
    await act(pick("فایل بکاپ با موفقیت وارد شد","Backup uploaded successfully"),()=>uploadBackup(file));
  };

  const rows=home?.backups||[];
  const latest=rows[0];
  const schedule=settings.enabled
    ? `${settings.frequency} · ${String(settings.hour).padStart(2,"0")}:${String(settings.minute).padStart(2,"0")}`
    : pick("خاموش","Off");

  return <Shell active="/admin/backups"><div className="page backup-runtime-page">
    <div className="page-head">
      <div><h1>{pick("بکاپ و بازیابی","Backup & Restore")}</h1></div>
      <div className="action-row">
        <input ref={uploadRef} type="file" accept=".tpbak,application/octet-stream" hidden onChange={onUpload}/>
        <button className="ghost" disabled={busy} onClick={()=>uploadRef.current?.click()}>{pick("آپلود بکاپ","Upload backup")}</button>
        <button className="ghost" disabled={busy} onClick={()=>void act(pick("کلید بازیابی دانلود شد","Recovery key downloaded"),downloadRecoveryKey,false)}>{pick("کلید بازیابی","Recovery key")}</button>
        <button className="ghost" disabled={busy} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
        <button className="primary" disabled={busy} onClick={()=>void act(pick("بکاپ جدید ساخته شد","Backup created"),()=>parityApi.backupCreate(settings.send_telegram))}>{pick("ایجاد بکاپ","Create backup")}</button>
      </div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("تعداد بکاپ‌ها","Backups")} value={String(rows.length)} icon="⟲"/>
      <Stat label={pick("آخرین بکاپ","Latest backup")} value={latest?formatDate(latest.created_at||latest.created_at_iso||latest.timestamp):"—"}/>
      <Stat label={pick("زمان‌بندی","Schedule")} value={schedule}/>
      <Stat label={pick("نگهداری","Retention")} value={String(settings.retention)}/>
      <Stat label={pick("Fingerprint کلید","Key fingerprint")} value={home?.key_fingerprint?String(home.key_fingerprint).slice(0,18)+"…":"—"}/>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("نسخه‌های موجود","Available backups")}</b><small>{pick("فایل‌های واقعی رمزگذاری‌شده روی سرور","Encrypted backup files on the server")}</small></div></div>
        {rows.length===0&&<div className="runtime-empty">{pick("هنوز بکاپی وجود ندارد.","No backups yet.")}</div>}
        {rows.map((row,index)=>{
          const filename=text(row,"filename","name","file")||`backup-${index+1}.tpbak`;
          const validFlag="valid" in row?Boolean(row.valid):"verified" in row?Boolean(row.verified):true;
          return <div className="module-row" key={filename}>
            <span className="module-icon">⟲</span>
            <div className="grow">
              <b dir="ltr">{filename}</b>
              <small>{formatDate(row.created_at||row.created_at_iso||row.timestamp)} · {formatSize(row.size_bytes||row.size)}</small>
            </div>
            <Badge tone={validFlag?"ok":"warn"}>{validFlag?pick("آماده","Ready"):pick("نیاز به بررسی","Check")}</Badge>
            <div className="row-actions">
              <button className="mini-btn" disabled={busy} onClick={()=>void act(pick("اطلاعات بکاپ دریافت شد","Backup info loaded"),()=>parityApi.backupInfo(filename),false)}>{pick("جزئیات","Info")}</button>
              <button className="mini-btn" disabled={busy} onClick={()=>void act(pick("دانلود شروع شد","Download started"),()=>downloadBackupFile(filename),false)}>{pick("دانلود","Download")}</button>
              <button className="mini-btn" disabled={busy} onClick={()=>void act(pick("به تلگرام ارسال شد","Sent to Telegram"),()=>parityApi.backupTelegram(filename))}>Telegram</button>
              <button className="mini-btn" disabled={busy} onClick={()=>{
                if(window.confirm(pick("بازیابی این نسخه انجام شود؟ سرویس‌ها ممکن است موقتاً ری‌استارت شوند.","Restore this backup? Services may restart temporarily.")))void act(pick("بازیابی انجام شد","Restore completed"),()=>parityApi.backupRestore(filename));
              }}>{pick("بازیابی","Restore")}</button>
              <button className="mini-btn danger" disabled={busy} onClick={()=>{
                if(window.confirm(pick("این بکاپ برای همیشه حذف شود؟","Delete this backup permanently?")))void act(pick("بکاپ حذف شد","Backup deleted"),()=>parityApi.backupDelete(filename));
              }}>{pick("حذف","Delete")}</button>
            </div>
          </div>;
        })}
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("زمان‌بندی خودکار","Automatic schedule")}</b><small>{pick("تنظیمات مستقیماً در Backend ذخیره می‌شود","Stored directly in the backend")}</small></div></div>
        <label className="toggle module-toggle"><span>{pick("بکاپ خودکار","Automatic backups")}</span><input type="checkbox" checked={settings.enabled} onChange={e=>setSettings(s=>({...s,enabled:e.target.checked}))}/><i/></label>
        <label className="field"><span>{pick("تناوب","Frequency")}</span><select value={settings.frequency} onChange={e=>setSettings(s=>({...s,frequency:e.target.value as BackupSettings["frequency"]}))}><option value="hourly">Hourly</option><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label>
        <div className="setting-grid">
          <label className="field"><span>{pick("ساعت","Hour")}</span><input type="number" min={0} max={23} value={settings.hour} onChange={e=>setSettings(s=>({...s,hour:Number(e.target.value)}))}/></label>
          <label className="field"><span>{pick("دقیقه","Minute")}</span><input type="number" min={0} max={59} value={settings.minute} onChange={e=>setSettings(s=>({...s,minute:Number(e.target.value)}))}/></label>
          <label className="field"><span>{pick("روز هفته","Weekday")}</span><select value={settings.weekday} onChange={e=>setSettings(s=>({...s,weekday:Number(e.target.value)}))}><option value={0}>{pick("دوشنبه","Monday")}</option><option value={1}>{pick("سه‌شنبه","Tuesday")}</option><option value={2}>{pick("چهارشنبه","Wednesday")}</option><option value={3}>{pick("پنجشنبه","Thursday")}</option><option value={4}>{pick("جمعه","Friday")}</option><option value={5}>{pick("شنبه","Saturday")}</option><option value={6}>{pick("یکشنبه","Sunday")}</option></select></label>
          <label className="field"><span>{pick("تعداد نسخه نگهداری","Retention")}</span><input type="number" min={1} max={100} value={settings.retention} onChange={e=>setSettings(s=>({...s,retention:Number(e.target.value)}))}/></label>
        </div>
        <label className="field"><span>{pick("منطقه زمانی","Timezone")}</span><input dir="ltr" value={settings.timezone} onChange={e=>setSettings(s=>({...s,timezone:e.target.value}))}/></label>
        <label className="toggle module-toggle"><span>{pick("ارسال خودکار به تلگرام","Send automatically to Telegram")}</span><input type="checkbox" checked={settings.send_telegram} onChange={e=>setSettings(s=>({...s,send_telegram:e.target.checked}))}/><i/></label>
        <label className="field"><span>Telegram Chat ID</span><input dir="ltr" value={settings.telegram_chat_id} onChange={e=>setSettings(s=>({...s,telegram_chat_id:e.target.value}))}/></label>
        <div className="action-row">
          <button className="primary" disabled={busy} onClick={()=>void act(pick("تنظیمات بکاپ ذخیره شد","Backup settings saved"),()=>parityApi.backupSettings(settings))}>{pick("ذخیره تنظیمات","Save settings")}</button>
          <button className="ghost" disabled={busy||!settings.telegram_chat_id.trim()} onClick={()=>void act(pick("تست تلگرام موفق بود","Telegram test passed"),parityApi.backupTestTelegram)}>{pick("تست تلگرام","Test Telegram")}</button>
        </div>
      </Card>
    </div>

    {detail&&<Card className="runtime-detail"><div className="card-head"><b>{pick("جزئیات عملیات","Operation details")}</b><button className="mini-btn" onClick={()=>setDetail("")}>×</button></div><pre className="runtime-log" dir="ltr">{detail}</pre></Card>}
  </div></Shell>;
}
