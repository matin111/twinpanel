"use client";

import {FormEvent,useEffect,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {useBranding} from "../lib/branding";
import {useI18n} from "../lib/i18n";
import {playNotificationSound,primeNotificationSound} from "../lib/notification-sound";

type ChatMessage={id:number;sender_role:string;message:string|null;attachment_type?:string|null;attachment_ref?:string|null;created_at:string;_pending?:boolean};
type ChatTicket={id:number;status:string;subject?:string|null;messages?:ChatMessage[];guest_token?:string};
type GuestSession={ticketId:number;token:string;name:string;contact:string};
type UploadResult={attachment_type:string;attachment_ref:string};
type GuestDelta={ticket_id:number;status:string;last_message_at?:string|null;messages?:ChatMessage[]};
type GuestFastReply={ticket_id:number;status:string;last_message_at?:string|null;message:ChatMessage};

const SESSION_KEY="twinpanel_guest_chat_v3";
const SESSION_BACKUP_KEY="twinpanel_guest_chat_session_v3";
const COOKIE_KEY="twinpanel_guest_chat_v3";
const TICKET_CACHE_KEY="twinpanel_guest_chat_ticket_v3";
const OPEN_KEY="twinpanel_guest_chat_open_v3";
const ALLOWED_IMAGES=new Set(["image/jpeg","image/png","image/webp","image/gif"]);
const MAX_IMAGE_BYTES=5*1024*1024;
const EMOJIS=["😀","😁","😂","😍","🥰","😊","😉","😎","🤩","🥳","👍","👌","🙏","👏","💜","❤️","🔥","✨","✅","💯","🎉","🚀","📌","🤝"];
const STICKERS=["👍","❤️","🙏","😊","😂","🎉","✅","🔥","💜","👋","⭐","🤝","😍","👏","💯","🚀"];

function parseSession(raw:string|null):GuestSession|null{
  if(!raw)return null;
  try{
    const value=JSON.parse(raw) as Partial<GuestSession>;
    const ticketId=Number(value.ticketId||0);
    const token=String(value.token||"").trim();
    if(!ticketId||!token)return null;
    return {ticketId,token,name:String(value.name||""),contact:String(value.contact||"")};
  }catch{return null;}
}
function cookieSession(){
  if(typeof document==="undefined")return null;
  const prefix=`${COOKIE_KEY}=`;
  const row=document.cookie.split(";").map(x=>x.trim()).find(x=>x.startsWith(prefix));
  if(!row)return null;
  try{return parseSession(decodeURIComponent(row.slice(prefix.length)));}catch{return null;}
}
function loadSession():GuestSession|null{
  if(typeof window==="undefined")return null;
  try{const value=parseSession(localStorage.getItem(SESSION_KEY));if(value)return value;}catch{}
  try{const value=parseSession(sessionStorage.getItem(SESSION_BACKUP_KEY));if(value)return value;}catch{}
  return cookieSession();
}
function saveSession(value:GuestSession){
  const raw=JSON.stringify(value);
  try{localStorage.setItem(SESSION_KEY,raw);}catch{}
  try{sessionStorage.setItem(SESSION_BACKUP_KEY,raw);}catch{}
  try{document.cookie=`${COOKIE_KEY}=${encodeURIComponent(raw)}; Max-Age=31536000; Path=/; SameSite=Lax`;}catch{}
}
function clearSession(){
  try{localStorage.removeItem(SESSION_KEY);localStorage.removeItem(TICKET_CACHE_KEY);localStorage.removeItem(OPEN_KEY);}catch{}
  try{sessionStorage.removeItem(SESSION_BACKUP_KEY);}catch{}
  try{document.cookie=`${COOKIE_KEY}=; Max-Age=0; Path=/; SameSite=Lax`;}catch{}
}
function loadTicketCache(session:GuestSession|null):ChatTicket|null{
  if(!session)return null;
  try{
    const row=JSON.parse(localStorage.getItem(TICKET_CACHE_KEY)||"null") as ChatTicket|null;
    return row&&Number(row.id)===session.ticketId?row:null;
  }catch{return null;}
}
function saveTicketCache(ticket:ChatTicket|null){
  if(!ticket||ticket.id<=0)return;
  try{localStorage.setItem(TICKET_CACHE_KEY,JSON.stringify(ticket));}catch{}
}
function friendlyError(reason:unknown,fa:string,en:string,lang:"fa"|"en"){
  const error=reason instanceof Error?reason:null;
  const raw=String(error?.message||reason||"");
  if(error?.name==="TimeoutError"||error?.name==="AbortError"||/signal timed out|timeout|aborted/i.test(raw))return lang==="fa"?fa:en;
  return raw||(lang==="fa"?fa:en);
}
async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const headers=new Headers(init.headers);
  if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof Blob)&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store",signal:init.signal??AbortSignal.timeout(init.method&&init.method!=="GET"?12000:8000)});
  if(!response.ok){
    let message=`API ${response.status}`;
    try{const payload=await response.json() as {detail?:string;message?:string};message=payload.detail??payload.message??message;}catch{}
    throw new Error(message);
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}
function maxAdminMessageId(ticket:ChatTicket|null){return Math.max(0,...(ticket?.messages||[]).filter(x=>String(x.sender_role).toLowerCase()==="admin").map(x=>Number(x.id)||0));}
function maxMessageId(ticket:ChatTicket|null){return Math.max(0,...(ticket?.messages||[]).filter(x=>Number(x.id)>0).map(x=>Number(x.id)||0));}
function attachmentUrl(value?:string|null){const ref=String(value||"").trim();if(!ref)return "";if(/^https?:\/\//.test(ref))return ref;return `${API_BASE}${ref.startsWith("/")?ref:`/v1/support/files/${encodeURIComponent(ref)}`}`;}

export function SupportGuestChatWidgetV3(){
  const {pick,lang}=useI18n();
  const {brand}=useBranding();
  const [open,setOpen]=useState(false);
  const [initialized,setInitialized]=useState(false);
  const [session,setSession]=useState<GuestSession|null>(null);
  const [ticket,setTicket]=useState<ChatTicket|null>(null);
  const ticketRef=useRef<ChatTicket|null>(null);
  const [name,setName]=useState("");
  const [contact,setContact]=useState("");
  const [draft,setDraft]=useState("");
  const [sending,setSending]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [image,setImage]=useState<File|null>(null);
  const [preview,setPreview]=useState("");
  const [emojiOpen,setEmojiOpen]=useState(false);
  const [stickerOpen,setStickerOpen]=useState(false);
  const fileRef=useRef<HTMLInputElement|null>(null);
  const endRef=useRef<HTMLDivElement|null>(null);
  const refreshBusy=useRef(false);
  const deltaBusy=useRef(false);
  const lastAdminId=useRef(0);
  const soundReady=useRef(false);

  useEffect(()=>{ticketRef.current=ticket;},[ticket]);

  const applyTicket=(next:ChatTicket,play=true)=>{
    const adminId=maxAdminMessageId(next);
    if(play&&lastAdminId.current>0&&adminId>lastAdminId.current&&soundReady.current)void playNotificationSound("message");
    lastAdminId.current=Math.max(lastAdminId.current,adminId);
    ticketRef.current=next;
    setTicket(next);
    saveTicketCache(next);
    setInitialized(true);
  };

  const applyFastReply=(sent:GuestFastReply,tempId?:number)=>{
    const current=ticketRef.current;
    if(!current||current.id!==sent.ticket_id)return;
    const cleaned=(current.messages||[]).filter(item=>item.id!==tempId&&item.id!==sent.message.id);
    applyTicket({...current,status:sent.status,messages:[...cleaned,sent.message]},false);
  };

  useEffect(()=>{
    const saved=loadSession();
    if(saved){
      setSession(saved);setName(saved.name);setContact(saved.contact);
      const cached=loadTicketCache(saved);
      if(cached){ticketRef.current=cached;setTicket(cached);lastAdminId.current=maxAdminMessageId(cached);}
    }
    try{setOpen(localStorage.getItem(OPEN_KEY)==="1");}catch{}
    setInitialized(true);
    const prime=()=>{soundReady.current=true;void primeNotificationSound();};
    window.addEventListener("pointerdown",prime,{once:true});
    window.addEventListener("keydown",prime,{once:true});
    return()=>{window.removeEventListener("pointerdown",prime);window.removeEventListener("keydown",prime);};
  },[]);

  const scrollBottom=()=>window.setTimeout(()=>endRef.current?.scrollIntoView({behavior:"smooth",block:"end"}),20);
  const refresh=async(silent=true)=>{
    const saved=session??loadSession();
    if(!saved||refreshBusy.current)return;
    refreshBusy.current=true;
    if(!silent)setLoading(true);
    try{
      const next=await request<ChatTicket>(`/v1/support/guest/tickets/${saved.ticketId}`,{headers:{"X-Guest-Chat-Token":saved.token}});
      saveSession(saved);setSession(saved);applyTicket(next,true);setError("");
    }catch(reason){if(!silent)setError(friendlyError(reason,"ارتباط با پشتیبانی کند شده است؛ گفتگوی قبلی محفوظ است.","Support connection is slow; your previous chat is preserved.",lang));}
    finally{refreshBusy.current=false;if(!silent)setLoading(false);}
  };
  const refreshDelta=async()=>{
    const saved=session??loadSession();const current=ticketRef.current;
    if(!saved||!current||current.id<=0||deltaBusy.current)return;
    deltaBusy.current=true;
    try{
      const delta=await request<GuestDelta>(`/v1/support/guest/tickets/${saved.ticketId}/messages-after?after_id=${maxMessageId(current)}`,{headers:{"X-Guest-Chat-Token":saved.token}});
      const latest=ticketRef.current;if(!latest||latest.id!==saved.ticketId)return;
      const existing=new Set((latest.messages||[]).map(item=>item.id));
      const incoming=(delta.messages||[]).filter(item=>!existing.has(item.id));
      if(incoming.length||delta.status!==latest.status){applyTicket({...latest,status:delta.status||latest.status,messages:[...(latest.messages||[]),...incoming]},true);}
    }catch{}finally{deltaBusy.current=false;}
  };

  useEffect(()=>{if(open&&session)void refresh(false);},[open,session?.ticketId]);
  useEffect(()=>{
    if(!open||!session||!ticket||ticket.id<=0)return;
    const timer=window.setInterval(()=>{if(document.visibilityState==="visible")void refreshDelta();},500);
    return()=>window.clearInterval(timer);
  },[open,session?.ticketId,ticket?.id]);
  useEffect(()=>{if(open&&ticket?.messages?.length)scrollBottom();},[open,ticket?.messages?.length]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);

  const setOpenPersist=(value:boolean)=>{setOpen(value);try{localStorage.setItem(OPEN_KEY,value?"1":"0");}catch{}if(value)void primeNotificationSound();};
  const resetConversation=()=>{if(!window.confirm(pick("گفتگوی ذخیره‌شده پاک شود و گفتگوی جدید شروع شود؟","Clear the saved conversation and start a new one?")))return;clearSession();setSession(null);setTicket(null);ticketRef.current=null;setName("");setContact("");setDraft("");setError("");lastAdminId.current=0;setInitialized(true);};
  const resetImage=()=>{if(preview)URL.revokeObjectURL(preview);setImage(null);setPreview("");if(fileRef.current)fileRef.current.value="";};
  const chooseImage=(file?:File|null)=>{if(!file)return;if(!ALLOWED_IMAGES.has(file.type)){setError(pick("فرمت تصویر باید JPG، PNG، WebP یا GIF باشد","Image must be JPG, PNG, WebP or GIF"));return;}if(file.size>MAX_IMAGE_BYTES){setError(pick("حداکثر حجم تصویر ۵ مگابایت است","Maximum image size is 5 MB"));return;}if(preview)URL.revokeObjectURL(preview);setImage(file);setPreview(URL.createObjectURL(file));setError("");};
  const uploadImage=async(ticketId:number,current:GuestSession)=>{
    if(!image)return null;
    const response=await fetch(`${API_BASE}/v1/support/guest/tickets/${ticketId}/upload-image`,{method:"POST",headers:{"X-Guest-Chat-Token":current.token,"Content-Type":image.type||"application/octet-stream"},body:image,cache:"no-store",signal:AbortSignal.timeout(15000)});
    if(!response.ok)throw new Error(pick("آپلود تصویر ناموفق بود","Image upload failed"));
    return response.json() as Promise<UploadResult>;
  };
  const sendAttachment=async(ticketId:number,current:GuestSession)=>{
    const uploaded=await uploadImage(ticketId,current);if(!uploaded)return null;
    return request<GuestFastReply>(`/v1/support/guest/tickets/${ticketId}/messages-fast`,{method:"POST",headers:{"X-Guest-Chat-Token":current.token},body:JSON.stringify({message:null,attachment_type:uploaded.attachment_type,attachment_ref:uploaded.attachment_ref,source:"web"})});
  };

  const startChat=async(event:FormEvent)=>{
    event.preventDefault();if(sending)return;
    const text=draft.trim();
    if(!text&&!image)return;
    if(name.trim().length<2||contact.trim().length<3){setError(pick("نام و راه ارتباطی را وارد کنید","Enter your name and contact"));return;}
    const first=text||pick("📷 تصویر پیوست شد","📷 Image attached");
    const pending:ChatTicket={id:0,status:"open",messages:[{id:-Date.now(),sender_role:"guest",message:first,created_at:new Date().toISOString(),_pending:true}]};
    setSending(true);setError("");ticketRef.current=pending;setTicket(pending);setDraft("");scrollBottom();
    try{
      const created=await request<ChatTicket>("/v1/support/guest/tickets",{method:"POST",body:JSON.stringify({name:name.trim(),contact:contact.trim(),message:first,source:"web"})});
      if(!created.id||!created.guest_token)throw new Error("CHAT_CREATE_FAILED");
      const current={ticketId:created.id,token:created.guest_token,name:name.trim(),contact:contact.trim()};
      saveSession(current);setSession(current);
      const clean={...created,guest_token:undefined};applyTicket(clean,false);
      if(image){const sent=await sendAttachment(created.id,current);if(sent)applyFastReply(sent);}
      resetImage();scrollBottom();
    }catch(reason){ticketRef.current=null;setTicket(null);setDraft(text);setError(friendlyError(reason,"ارسال بیش از حد طول کشید. دوباره تلاش کنید؛ اطلاعات شما حفظ شده است.","Sending took too long. Please retry; your details are preserved.",lang));}
    finally{setSending(false);}
  };

  const sendText=async(textValue:string)=>{
    const currentTicket=ticketRef.current;
    if(!currentTicket||currentTicket.id<=0||sending)return;
    const text=textValue.trim();if(!text)return;
    const current=session??loadSession();if(!current){setError(pick("گفتگوی قبلی پیدا نشد","Previous chat session was not found"));return;}
    const tempId=-Date.now();
    setSending(true);setError("");setDraft("");
    applyTicket({...currentTicket,messages:[...(currentTicket.messages||[]),{id:tempId,sender_role:"guest",message:text,created_at:new Date().toISOString(),_pending:true}]},false);scrollBottom();
    try{
      const sent=await request<GuestFastReply>(`/v1/support/guest/tickets/${currentTicket.id}/messages-fast`,{method:"POST",headers:{"X-Guest-Chat-Token":current.token},body:JSON.stringify({message:text,source:"web"})});
      applyFastReply(sent,tempId);
    }catch(reason){const latest=ticketRef.current;if(latest)applyTicket({...latest,messages:(latest.messages||[]).filter(x=>x.id!==tempId)},false);setDraft(text);setError(friendlyError(reason,"ارسال پیام دیر پاسخ داد؛ دوباره تلاش کنید.","Message delivery timed out; please retry.",lang));}
    finally{setSending(false);}
  };

  const submitMessage=async(event:FormEvent)=>{
    event.preventDefault();const currentTicket=ticketRef.current;if(!currentTicket||currentTicket.id<=0||sending)return;
    const text=draft.trim();if(!text&&!image)return;
    if(text&&!image){await sendText(text);return;}
    const current=session??loadSession();if(!current){setError(pick("گفتگوی قبلی پیدا نشد","Previous chat session was not found"));return;}
    setSending(true);setError("");
    try{
      if(text){const sent=await request<GuestFastReply>(`/v1/support/guest/tickets/${currentTicket.id}/messages-fast`,{method:"POST",headers:{"X-Guest-Chat-Token":current.token},body:JSON.stringify({message:text,source:"web"})});applyFastReply(sent);}
      if(image){const sent=await sendAttachment(currentTicket.id,current);if(sent)applyFastReply(sent);}
      setDraft("");resetImage();scrollBottom();
    }catch(reason){setError(friendlyError(reason,"ارسال پیام یا تصویر بیش از حد طول کشید.","Message or image delivery took too long.",lang));}
    finally{setSending(false);}
  };

  const messages=ticket?.messages||[];
  const emojiPicker=<div className="supportEmojiRootV3"><button type="button" className="supportEmojiButtonV3" onClick={()=>{setEmojiOpen(v=>!v);setStickerOpen(false);}}>☺</button>{emojiOpen&&<div className="supportEmojiPickerV3">{EMOJIS.map(x=><button type="button" key={x} onClick={()=>{setDraft(v=>v+x);setEmojiOpen(false);}}>{x}</button>)}</div>}</div>;
  const stickerPicker=<div className="supportEmojiRootV3"><button type="button" className="supportEmojiButtonV3" title={pick("استیکر","Sticker")} onClick={()=>{setStickerOpen(v=>!v);setEmojiOpen(false);}}>✨</button>{stickerOpen&&<div className="supportEmojiPickerV3">{STICKERS.map(x=><button type="button" key={x} onClick={()=>{setStickerOpen(false);void sendText(x);}}>{x}</button>)}</div>}</div>;

  return <div className="supportChatRoot"><input ref={fileRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/gif" onChange={e=>chooseImage(e.target.files?.[0])}/>{open&&<section className="supportChatWindow"><header className="supportChatHeader"><div className="supportChatHeaderInfo"><span className="supportChatStatus"/><div><b>{pick("پشتیبانی آنلاین","Live support")}</b><small>{brand.name}</small></div></div><div><button type="button" className="supportChatClose" title={pick("گفتگوی جدید","New chat")} onClick={resetConversation}>↻</button><button type="button" className="supportChatClose" onClick={()=>setOpenPersist(false)}>×</button></div></header><div className="supportChatBody">
    {loading&&!initialized&&<div className="supportChatState">{pick("در حال بازیابی گفتگو...","Restoring chat...")}</div>}
    {initialized&&!ticket&&<form className="supportChatStart" onSubmit={startChat}><h3>{pick("چطور می‌توانیم کمک کنیم؟","How can we help?")}</h3><label><span>{pick("نام","Name")}</span><input value={name} onChange={e=>setName(e.target.value)} required/></label><label><span>{pick("ایمیل یا شماره تماس","Email or phone")}</span><input dir="ltr" value={contact} onChange={e=>setContact(e.target.value)} required/></label><label><span>{pick("پیام","Message")}</span><textarea value={draft} onChange={e=>setDraft(e.target.value)} rows={4}/></label>{preview&&<div className="supportChatImagePreview"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}<div className="supportChatStartTools"><div className="supportChatToolRow">{emojiPicker}{stickerPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎 {pick("تصویر","Image")}</button></div>{error&&<div className="supportChatError">{error}</div>}</div><button type="submit" className="supportChatPrimary" disabled={sending||(!draft.trim()&&!image)}>{sending?pick("در حال اتصال...","Connecting..."):pick("شروع گفتگو","Start chat")}</button></form>}
    {ticket&&<><div className="supportChatMessages">{messages.map(item=>{const own=item.sender_role==="guest"||item.sender_role==="user";return <article key={item.id} className={own?"supportChatMessage own":"supportChatMessage admin"}><small>{own?pick("شما","You"):pick("پشتیبانی","Support")}</small>{item.message&&<p>{item.message}</p>}{item.attachment_ref&&<a href={attachmentUrl(item.attachment_ref)} target="_blank" rel="noreferrer"><img className="supportChatImage" src={attachmentUrl(item.attachment_ref)} alt=""/></a>}<time>{item._pending?pick("در حال ارسال","Sending"):new Date(item.created_at).toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit"})}</time></article>})}<div ref={endRef}/></div>{ticket.id<=0?<div className="supportChatState">{pick("در حال ایجاد گفتگوی امن...","Creating secure chat...")}</div>:<form className="supportChatComposer" onSubmit={submitMessage}>{preview&&<div className="supportChatImagePreview compact"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}{error&&<div className="supportChatError">{error}</div>}<div>{emojiPicker}{stickerPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎</button><textarea value={draft} onChange={e=>setDraft(e.target.value)} placeholder={pick("پیام...","Message...")} rows={1}/><button className="supportChatSend" type="submit" disabled={sending||(!draft.trim()&&!image)}>{sending?"…":pick("ارسال","Send")}</button></div></form>}</>}
  </div></section>}<button type="button" className={open?"supportChatLauncher active":"supportChatLauncher"} onClick={()=>setOpenPersist(!open)}><span className="supportChatLauncherIcon">{open?"×":"✦"}</span>{!open&&<span><b>{pick("پشتیبانی آنلاین","Live support")}</b><small>{pick("گفتگو با پشتیبانی","Chat with support")}</small></span>}</button></div>;
}
