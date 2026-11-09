"use client";

import {ChangeEvent,useEffect,useMemo,useRef,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {BackupHome,BackupSettings,parityApi} from "../lib/admin-parity-api";
import {downloadBackupFile,uploadBackup,initTelegramParts,uploadTelegramPart,getTelegramPartsStatus,finishTelegramParts,discardTelegramParts,TelegramPartsSession} from "../lib/backup-runtime-api";
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
  const telegramPartRef=useRef<HTMLInputElement>(null);
  const [telegramParts,setTelegramParts]=useState<TelegramPartsSession|null>(null);
  const [telegramPartsSha,setTelegramPartsSha]=useState("");
  const [home,setHome]=useState<BackupHome>({ok:true,backups:[],settings:defaults});
  const [settings,setSettings]=useState<BackupSettings>(defaults);
  const [backupBotToken,setBackupBotToken]=useState("");
  const [info,setInfo]=useState<Record<string,unknown>|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const normalizeSettings=(value:BackupSettings):BackupSettings=>{
    const telegram_chat_id=String(value.telegram_chat_id||"").trim();
    return {...defaults,...value,telegram_chat_id,send_telegram:Boolean(value.send_telegram&&telegram_chat_id)};
  };

  const load=async()=>{
    setLoading(true);setError("");
    try{const data=await parityApi.backups();const normalized=normalizeSettings({...defaults,...data.settings});setHome({...data,settings:normalized});setSettings(normalized);}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const backups=home.backups||[];
  const telegramBot=home.telegram_bot;
  const telegramConfigured=Boolean(telegramBot?.configured);
  const telegramUsername=String(telegramBot?.bot?.username||"").trim();
  const totalBytes=useMemo(()=>backups.reduce((sum,row)=>sum+num(row,"size_bytes","size","bytes"),0),[backups]);
  const telegramCount=useMemo(()=>backups.filter(telegramOk).length,[backups]);

  const run=async(key:string,label:string,fn:()=>Promise<unknown>,reload=true)=>{
    if(busy)return;setBusy(key);setError("");setOk("");
    try{const result=await fn();setOk(label);if(key.startsWith("info:"))setInfo(result as Record<string,unknown>);if(reload)await load();}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const pollManualTelegramJob=async(id:string)=>{
    for(let attempt=0;attempt<840;attempt+=1){
      const result=await parityApi.backupManualJob(id);
      const job=result.job;
      if(job.state==="succeeded"){
        sessionStorage.removeItem("tp-manual-backup-job");
        const filename=String(job.filename||"");
        if(!filename.endsWith(".tpbak"))throw new Error("BACKUP_FILENAME_MISSING");
        await load();
        await downloadBackupFile(filename);
        setOk(pick("فایل ZIP بکاپ آماده و دانلود شد.","Backup ZIP created and downloaded."));
        return;
      }
      if(job.state==="failed"){
        sessionStorage.removeItem("tp-manual-backup-job");
        throw new Error(String(job.error_code||"BACKUP_CREATE_FAILED"));
      }
      setOk(pick("در حال ساخت بکاپ…","Creating backup…"));
      await new Promise<void>(resolve=>setTimeout(resolve,5000));
    }
    throw new Error("BACKUP_JOB_STILL_PROCESSING");
  };
  const create=async()=>{
    if(busy)return;
    setBusy("create");setError("");setOk("");
    try{
      const result=await parityApi.backupCreate(false);
      const job=(result.job||{}) as Record<string,unknown>;
      const id=String(job.id||"");
      if(!/^[0-9a-f]{32}$/.test(id))throw new Error("BACKUP_JOB_ID_MISSING");
      sessionStorage.setItem("tp-manual-backup-job",id);
      await pollManualTelegramJob(id);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };
  useEffect(()=>{
    const id=typeof window!=="undefined"?sessionStorage.getItem("tp-manual-backup-job"):null;
    if(!id||!/^[0-9a-f]{32}$/.test(id))return;
    setBusy("create");
    void pollManualTelegramJob(id)
      .catch(e=>setError(e instanceof Error?e.message:String(e)))
      .finally(()=>setBusy(""));
    // The background job survives navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  const saveSettings=()=>{const normalized=normalizeSettings(settings);setSettings(normalized);void run("settings",pick("تنظیمات بکاپ ذخیره شد","Backup settings saved"),()=>parityApi.backupSettings(normalized));};
  const saveBackupBot=()=>{const token=backupBotToken.trim();if(token.length<20){setError(pick("توکن ربات بکاپ را کامل وارد کنید.","Enter the complete backup bot token."));return;}void run("backup-bot-save",pick("ربات اختصاصی بکاپ ذخیره شد","Dedicated backup bot saved"),async()=>{const result=await parityApi.backupTelegramSaveToken(token);setBackupBotToken("");return result;});};
  const deleteBackupBot=()=>{if(!window.confirm(pick("توکن ربات اختصاصی بکاپ حذف شود؟","Remove the dedicated backup bot token?")))return;void run("backup-bot-delete",pick("توکن ربات بکاپ حذف شد","Backup bot token removed"),()=>parityApi.backupTelegramDeleteToken());};
  const verifyTelegram=()=>{const chatId=settings.telegram_chat_id.trim();if(!chatId){setError(pick("ابتدا Telegram Chat ID را وارد کنید.","Enter the Telegram Chat ID first."));return;}void run("verify-telegram",pick("اتصال ربات بکاپ و Chat ID تأیید شد","Backup bot and Chat ID verified"),()=>parityApi.backupVerifyTelegram(chatId),false);};
  const upload=async(event:ChangeEvent<HTMLInputElement>)=>{
    const file=event.target.files?.[0];event.target.value="";
    if(!file)return;
    if(!/\.(zip|tpbak)$/i.test(file.name)){
      setError(pick("فقط فایل ZIP بکاپ قابل آپلود است.","Select a backup ZIP file."));return;
    }
    if(busy)return;
    setBusy("upload");setError("");setOk("");
    try{
      const result=await uploadBackup(file,(percent)=>setOk(pick(`در حال آپلود: ${percent}٪`,`Uploading: ${percent}%`)));
      const filename=String(result.filename||"");
      await load();
      if(filename&&window.confirm(pick("بکاپ آپلود شد. اطلاعات پنل فعلی با اطلاعات این بکاپ جایگزین شود؟","Backup uploaded. Replace this panel's current data with this backup?"))){
        await parityApi.backupRestore(filename);
        await load();
        setOk(pick("بازیابی بکاپ انجام شد.","Backup restored."));
      }else{
        setOk(pick("بکاپ آپلود شد و برای بازیابی آماده است.","Backup uploaded and ready to restore."));
      }
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };
  const uploadTelegramPiece=async(event:ChangeEvent<HTMLInputElement>)=>{
    const file=event.target.files?.[0];event.target.value="";
    if(!file||busy)return;
    setBusy("telegram-piece");setError("");setOk("");
    try{
      let session=telegramParts;
      if(!session){
        session=await initTelegramParts(file,telegramPartsSha);
        sessionStorage.setItem("tp-telegram-parts-session",session.id);
        setTelegramParts(session);
      }
      const updated=await uploadTelegramPart(session.id,file);
      setTelegramParts(updated);
      setOk(pick(
        `قسمت دریافت شد: ${updated.received_count} از ${updated.total_parts}. می‌توانید قسمت بعدی را جداگانه انتخاب کنید.`,
        `Part uploaded: ${updated.received_count} of ${updated.total_parts}. Select the next part separately.`
      ));
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy("")}
  };
  const finishTelegramSet=async()=>{
    const current=telegramParts;
    if(!current||busy)return;
    if(current.received_count!==current.total_parts){
      setError(pick("ابتدا تمام قسمت‌های بکاپ را آپلود کنید.","Upload every part before combining."));
      return;
    }
    setBusy("telegram-join");setError("");setOk("");
    try{
      let state=await finishTelegramParts(current.id);
      setTelegramParts(state);
      for(let i=0;i<600&&state.state==="verifying";i++){
        await new Promise<void>(resolve=>setTimeout(resolve,4000));
        state=await getTelegramPartsStatus(current.id);
        setTelegramParts(state);
      }
      if(state.state==="failed")throw new Error(state.error_code||"BACKUP_JOIN_FAILED");
      if(state.state==="imported"){
        setOk(pick(
          "تمام قسمت‌ها ترکیب و صحت بکاپ تأیید شد. فایل در فهرست بکاپ‌ها آماده Restore است.",
          "All parts combined and verified; the backup is now listed for manual restore."
        ));
        sessionStorage.removeItem("tp-telegram-parts-session");
        await load();
      }else{
        setOk(pick("بررسی فایل همچنان ادامه دارد؛ دوباره وضعیت را بررسی کنید.","Verification is still running; check the status again."));
      }
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy("")}
  };
  const resetTelegramSet=async()=>{
    if(busy)return;
    setBusy("telegram-discard");setError("");
    try{
      if(telegramParts)await discardTelegramParts(telegramParts.id);
      sessionStorage.removeItem("tp-telegram-parts-session");
      setTelegramParts(null);setTelegramPartsSha("");setOk("");
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy("")}
  };
  useEffect(()=>{
    const id=typeof window==="undefined"?null:sessionStorage.getItem("tp-telegram-parts-session");
    if(!id)return;
    void getTelegramPartsStatus(id).then(setTelegramParts).catch(()=>{
      sessionStorage.removeItem("tp-telegram-parts-session");
    });
  },[]);
  const download=async(filename:string)=>{if(busy)return;setBusy(`download:${filename}`);setError("");setOk("");try{await downloadBackupFile(filename);setOk(pick("دانلود بکاپ شروع شد","Backup download started"));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy("");}};


  return <Shell active="/admin/backups"><div className="page">
    <div className="page-head"><div><h1>{pick("بکاپ و بازیابی","Backup & Restore")}</h1></div><div className="action-row"><button className="ghost" disabled={Boolean(busy)} onClick={()=>inputRef.current?.click()}>{busy==="upload"?"…":pick("آپلود و بازیابی ZIP","Upload and restore ZIP")}</button><input ref={inputRef} type="file" accept=".zip,.tpbak" hidden onChange={upload}/><button className="primary" disabled={Boolean(busy)} onClick={create}>{busy==="create"?"…":pick("دانلود بکاپ ZIP","Download backup ZIP")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats"><Stat label={pick("تعداد بکاپ","Backups")} value={String(backups.length)} icon="⟲"/><Stat label={pick("حجم کل","Total size")} value={totalBytes?sizeText({size_bytes:totalBytes}):"—"} icon="▤"/><Stat label={pick("ارسال Telegram","Telegram copies")} value={String(telegramCount)} icon="✈"/><Stat label={pick("Retention","Retention")} value={`${settings.retention} ${pick("نسخه","copies")}`} icon="⌛"/></div>

    <div className="module-grid two backup-settings-pair">
      <Card><div className="card-head"><div><b>{pick("ربات بکاپ","Backup Bot")}</b></div><Badge tone={telegramConfigured?"ok":"warn"}>{telegramConfigured?(telegramUsername?`@${telegramUsername}`:pick("تنظیم شده","Configured")):pick("تنظیم نشده","Not configured")}</Badge></div><label className="field"><span>{pick("توکن ربات بکاپ","Backup bot token")}</span><input type="password" dir="ltr" autoComplete="off" placeholder={telegramConfigured?pick("برای تعویض، توکن جدید را وارد کنید","Enter a new token to replace it"):"123456:AA..."} value={backupBotToken} onChange={e=>setBackupBotToken(e.target.value)}/></label><label className="field"><span>Telegram Chat ID</span><input dir="ltr" value={settings.telegram_chat_id} onChange={e=>setSettings(v=>({...v,telegram_chat_id:e.target.value}))}/></label><label className="toggle module-toggle"><span>{pick("ارسال بکاپ‌های جدید به Telegram","Send new backups to Telegram")}</span><input type="checkbox" checked={settings.send_telegram} onChange={e=>setSettings(v=>({...v,send_telegram:e.target.checked}))}/><i/></label><div className="action-row"><button className="primary" disabled={Boolean(busy)||backupBotToken.trim().length<20} onClick={saveBackupBot}>{busy==="backup-bot-save"?"…":pick("ذخیره ربات بکاپ","Save backup bot")}</button>{telegramConfigured&&<button className="ghost danger" disabled={Boolean(busy)} onClick={deleteBackupBot}>{busy==="backup-bot-delete"?"…":pick("حذف توکن","Remove token")}</button>}<button className="ghost" disabled={Boolean(busy)||!telegramConfigured} onClick={verifyTelegram}>{busy==="verify-telegram"?"…":pick("تأیید و تست Chat ID","Verify & test Chat ID")}</button><button className="primary" disabled={Boolean(busy)} onClick={saveSettings}>{busy==="settings"?"…":pick("ذخیره تنظیمات","Save settings")}</button></div></Card>
    <Card className="runtime-editor"><div className="card-head"><div><b>{pick("زمان‌بندی بکاپ","Backup Schedule")}</b></div><label className="toggle module-toggle"><span>{settings.enabled?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</span><input type="checkbox" checked={settings.enabled} onChange={e=>setSettings(v=>({...v,enabled:e.target.checked}))}/><i/></label></div><div className="setting-grid"><label className="field"><span>{pick("تکرار","Frequency")}</span><select value={settings.frequency} onChange={e=>setSettings(v=>({...v,frequency:e.target.value as BackupSettings["frequency"]}))}><option value="hourly">Hourly</option><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label><label className="field"><span>{pick("ساعت","Hour")}</span><input type="number" min={0} max={23} value={settings.hour} onChange={e=>setSettings(v=>({...v,hour:Number(e.target.value)}))}/></label><label className="field"><span>{pick("دقیقه","Minute")}</span><input type="number" min={0} max={59} value={settings.minute} onChange={e=>setSettings(v=>({...v,minute:Number(e.target.value)}))}/></label><label className="field"><span>{pick("روز هفته ۰ تا ۶","Weekday 0-6")}</span><input type="number" min={0} max={6} value={settings.weekday} onChange={e=>setSettings(v=>({...v,weekday:Number(e.target.value)}))}/></label><label className="field"><span>{pick("Timezone","Timezone")}</span><input dir="ltr" value={settings.timezone} onChange={e=>setSettings(v=>({...v,timezone:e.target.value}))}/></label><label className="field"><span>{pick("تعداد نگهداری","Retention")}</span><input type="number" min={1} max={100} value={settings.retention} onChange={e=>setSettings(v=>({...v,retention:Number(e.target.value)}))}/></label></div><button className="primary" disabled={Boolean(busy)} onClick={saveSettings}>{busy==="settings"?"…":pick("ذخیره زمان‌بندی","Save schedule")}</button></Card>
    </div>

    <Card><div className="card-head"><div><b>{pick("فهرست بکاپ‌ها","Backup files")}</b></div><button className="ghost" disabled={loading} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>{loading?<div className="runtime-loading">{pick("در حال دریافت بکاپ‌ها...","Loading backups...")}</div>:<div className="table"><table><thead><tr><th>{pick("فایل","File")}</th><th>{pick("نوع","Kind")}</th><th>{pick("حجم","Size")}</th><th>{pick("تاریخ","Created")}</th><th>Telegram</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{backups.map((raw,index)=>{const row=raw as Record<string,unknown>,name=fileName(row);return <tr key={name||index}><td dir="ltr">{name}</td><td>{str(row,"kind","type")||"—"}</td><td>{sizeText(row)}</td><td>{dateText(row.created_at||row.timestamp)}</td><td><Badge tone={row.telegram_error?"bad":telegramOk(row)?"ok":"warn"}>{row.telegram_error?pick("خطا","Error"):row.telegram_only?pick("فقط تلگرام","Telegram only"):telegramOk(row)?pick("ارسال شده","Sent"):pick("ارسال نشده","Not sent")}</Badge></td><td><div className="row-actions"><button className="mini-btn" disabled={Boolean(busy)||row.archive_on_server===false} onClick={()=>void run(`info:${name}`,pick("اطلاعات بکاپ دریافت شد","Backup info loaded"),()=>parityApi.backupInfo(name),false)}>{pick("Info","Info")}</button><button className="mini-btn" disabled={Boolean(busy)||row.archive_on_server===false} onClick={()=>void download(name)}>{pick("دانلود","Download")}</button><button className="mini-btn" disabled={Boolean(busy)||row.archive_on_server===false} onClick={()=>void run(`tg:${name}`,pick("بکاپ به Telegram ارسال شد","Backup sent to Telegram"),()=>parityApi.backupTelegram(name))}>{pick("Telegram","Telegram")}</button><button className="mini-btn danger" disabled={Boolean(busy)||row.archive_on_server===false} onClick={()=>{const confirmText=window.prompt(pick("برای Restore عبارت RESTORE را وارد کنید","Type RESTORE to continue"),"");if(confirmText==="RESTORE")void run(`restore:${name}`,pick("Restore انجام شد","Restore completed"),()=>parityApi.backupRestore(name));}}>{pick("Restore","Restore")}</button><button className="mini-btn danger" disabled={Boolean(busy)} onClick={()=>{if(window.confirm(pick("این فایل بکاپ حذف شود؟","Delete this backup file?")))void run(`delete:${name}`,pick("بکاپ حذف شد","Backup deleted"),()=>parityApi.backupDelete(name));}}>{pick("حذف","Delete")}</button></div></td></tr>})}</tbody></table></div>}{!loading&&!backups.length&&<div className="runtime-empty">{pick("بکاپی وجود ندارد.","No backups exist.")}</div>}</Card>

    {info&&<Card><div className="card-head"><b>{pick("جزئیات بکاپ","Backup details")}</b><button className="mini-btn" onClick={()=>setInfo(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(info,null,2)}</pre></Card>}
  </div></Shell>;
}
