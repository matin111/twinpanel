"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Shell,PageHead,Badge,Card} from "./ui";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

 type Asset={id:number;platform:string;protocol:string|null;name:string;note:string|null;original_filename:string;file_size:number;sort_order:number;is_active:boolean;file_exists:boolean;download_url:string|null;created_at:string|null};
 type ListResponse={items:Asset[];storage_dir:string;platforms:string[];protocols:string[]};

const platformFa:Record<string,string>={android:"Android",ios:"iPhone / iPad",windows:"Windows",macos:"macOS",linux:"Linux"};
const protocolFa:Record<string,string>={cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray",other:"عمومی"};

async function call<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  const headers=new Headers(init.headers);
  if(token)headers.set("Authorization",`Bearer ${token}`);
  if(init.body && !(init.body instanceof FormData) && !headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(path,{...init,headers,cache:"no-store"});
  if(!response.ok){let message=`HTTP ${response.status}`;try{const body=await response.json();if(typeof body?.detail==="string")message=body.detail;}catch{}throw new Error(message);}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

function bytes(value:number){
  if(value>=1024*1024*1024)return `${(value/1024/1024/1024).toFixed(2)} GB`;
  if(value>=1024*1024)return `${(value/1024/1024).toFixed(1)} MB`;
  if(value>=1024)return `${(value/1024).toFixed(1)} KB`;
  return `${value} B`;
}

export function DownloadAssetsRuntime(){
  const {pick}=useI18n();
  const [data,setData]=useState<ListResponse|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [filter,setFilter]=useState("all");

  const load=async()=>{setLoading(true);setError("");try{setData(await call<ListResponse>("/v1/admin/download-assets"));}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setLoading(false);}};
  useEffect(()=>{void load();},[]);

  const visible=useMemo(()=>{
    const rows=data?.items||[];
    return filter==="all"?rows:rows.filter(x=>x.platform===filter);
  },[data,filter]);

  const submit=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    const form=event.currentTarget;
    const body=new FormData(form);
    const file=body.get("file") as File|null;
    if(!file?.size){setError(pick("فایل را انتخاب کنید.","Choose a file."));return;}
    setBusy(true);setError("");setOk("");
    try{
      await call<Asset>("/v1/admin/download-assets",{method:"POST",body});
      form.reset();setOk(pick("فایل با موفقیت آپلود شد.","File uploaded successfully."));await load();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const toggle=async(row:Asset)=>{setError("");try{await call(`/v1/admin/download-assets/${row.id}`,{method:"PATCH",body:JSON.stringify({is_active:!row.is_active})});await load();}catch(e){setError(e instanceof Error?e.message:String(e));}};
  const remove=async(row:Asset)=>{if(!window.confirm(pick(`فایل «${row.name}» حذف شود؟`,`Delete “${row.name}”?`)))return;setError("");try{await call(`/v1/admin/download-assets/${row.id}`,{method:"DELETE"});await load();}catch(e){setError(e instanceof Error?e.message:String(e));}};

  return <Shell active="/admin/downloads"><div className="page download-assets-page">
    <PageHead title={pick("فایل‌های دانلود","Download files")}/>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="download-assets-ok">{ok}</div>}

    <div className="download-assets-layout">
      <Card className="download-upload-card">
        <div className="download-card-head"><div><small>UPLOAD</small><h2>{pick("آپلود برنامه","Upload app")}</h2></div><span>500 MB</span></div>
        <form onSubmit={submit}>
          <label><span>{pick("سیستم عامل","Platform")}</span><select name="platform" defaultValue="android" required><option value="android">Android</option><option value="ios">iPhone / iPad</option><option value="windows">Windows</option><option value="macos">macOS</option><option value="linux">Linux</option></select></label>
          <label><span>{pick("پروتکل","Protocol")}</span><select name="protocol" defaultValue="other"><option value="other">{pick("عمومی","General")}</option><option value="cisco">Cisco / OpenConnect</option><option value="openvpn">OpenVPN</option><option value="wireguard">WireGuard</option><option value="l2tp">L2TP / IPsec</option><option value="v2ray">V2Ray / Xray</option></select></label>
          <label className="full"><span>{pick("نام نمایشی","Display name")}</span><input name="name" placeholder="OpenVPN Connect · Windows" required/></label>
          <label className="full"><span>{pick("توضیح کوتاه","Short note")}</span><input name="note" placeholder={pick("مثلاً نسخه 64 بیتی","e.g. 64-bit version")}/></label>
          <label><span>{pick("ترتیب","Order")}</span><input name="sort_order" type="number" defaultValue="100"/></label>
          <label className="file full"><span>{pick("فایل","File")}</span><input name="file" type="file" required accept=".apk,.aab,.msi,.exe,.zip,.dmg,.pkg,.deb,.rpm,.AppImage,.ovpn,.conf,.txt,.pdf"/></label>
          <button className="primary full" disabled={busy}>{busy?pick("در حال آپلود...","Uploading..."):pick("آپلود فایل","Upload file")}</button>
        </form>
      </Card>

      <Card className="download-assets-info"><div><small>{pick("مسیر ذخیره‌سازی","Storage path")}</small><code dir="ltr">{data?.storage_dir||"—"}</code></div><div><small>{pick("فایل‌های ثبت‌شده","Registered files")}</small><b>{(data?.items.length||0).toLocaleString("fa-IR")}</b></div><div><small>{pick("فایل‌های فعال","Active files")}</small><b>{(data?.items.filter(x=>x.is_active&&x.file_exists).length||0).toLocaleString("fa-IR")}</b></div></Card>
    </div>

    <div className="download-assets-toolbar"><button className={filter==="all"?"active":""} onClick={()=>setFilter("all")}>{pick("همه","All")}</button>{["android","ios","windows","macos","linux"].map(p=><button key={p} className={filter===p?"active":""} onClick={()=>setFilter(p)}>{platformFa[p]}</button>)}</div>

    {loading?<div className="customer-loading"><span className="customer-loader"/></div>:visible.length===0?<Card className="customer-empty"><p>{pick("فایلی ثبت نشده است.","No files uploaded yet.")}</p></Card>:<div className="download-assets-grid">{visible.map(row=><Card key={row.id} className="download-asset-card">
      <div className="download-asset-top"><div><small>#{row.id} · {platformFa[row.platform]||row.platform}</small><h3>{row.name}</h3></div><Badge tone={row.is_active&&row.file_exists?"ok":row.file_exists?"warn":"bad"}>{row.file_exists?(row.is_active?pick("فعال","Active"):pick("غیرفعال","Disabled")):pick("فایل گم شده","Missing")}</Badge></div>
      <div className="download-asset-meta"><span>{protocolFa[row.protocol||"other"]||row.protocol||"—"}</span><span>{bytes(row.file_size)}</span><span dir="ltr">{row.original_filename}</span></div>
      {row.note&&<p>{row.note}</p>}
      <div className="download-asset-actions">{row.download_url&&<a className="ghost" href={row.download_url} target="_blank" rel="noopener noreferrer">{pick("تست دانلود","Test")}</a>}<button className="ghost" onClick={()=>void toggle(row)}>{row.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button><button className="danger" onClick={()=>void remove(row)}>{pick("حذف","Delete")}</button></div>
    </Card>)}</div>}
  </div></Shell>;
}
