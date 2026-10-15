"use client";

import {FormEvent,useEffect,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {useBranding} from "../lib/branding";
import {useI18n} from "../lib/i18n";
import {playNotificationSound,primeNotificationSound} from "../lib/notification-sound";

type ChatMessage={id:number;sender_role:string;message:string|null;attachment_type?:string|null;attachment_ref?:string|null;created_at:string;_pending?:boolean};
type ChatTicket={id:number;status:string;subject?:string|null;messages?:ChatMessage[]};
type UploadResult={attachment_type:string;attachment_ref:string};
type ChatDelta={ticket_id:number;status:string;last_message_at?:string|null;messages?:ChatMessage[]};
type ChatFastReply={ticket_id:number;status:string;last_message_at?:string|null;message:ChatMessage};

type Props={customerToken:string};

const OPEN_KEY="twinpanel_account_support_chat_open_v1";
const CHAT_EMOJIS=["😀","😁","😂","😍","🥰","😊","😉","😎","🤩","🥳","👍","👌","🙏","👏","💜","❤️","🔥","✨","✅","💯","🎉","🚀","📌","🤝"];
const STICKERS=["👍","❤️","🙏","😊","😂","🎉","✅","🔥","💜","👋","⭐","🤝","😍","👏","💯","🚀"];
const ALLOWED_IMAGES=new Set(["image/jpeg","image/png","image/webp","image/gif"]);
const MAX_IMAGE_BYTES=5*1024*1024;

async function api<T>(path:string,token:string,options:RequestInit={}):Promise<T>{
  const headers=new Headers(options.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(options.body&&!headers.has("Content-Type")&&!(options.body instanceof Blob)&&!(options.body instanceof FormData))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...options,headers,cache:"no-store",signal:options.signal??AbortSignal.timeout(4000)});
  if(!response.ok){let message=`API ${response.status}`;try{const body=await response.json() as {detail?:string;message?:string};message=body.detail??body.message??message;}catch{}throw new Error(message);}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

function attachmentUrl(value?:string|null){if(!value)return "";if(/^https?:\/\//.test(value))return value;return `${API_BASE}${value.startsWith("/")?value:`/v1/support/files/${encodeURIComponent(value)}`}`;}
function maxAdminMessageId(ticket:ChatTicket|null){return Math.max(0,...(ticket?.messages||[]).filter(x=>String(x.sender_role).toLowerCase()==="admin").map(x=>Number(x.id)||0));}
function maxMessageId(ticket:ChatTicket|null){return Math.max(0,...(ticket?.messages||[]).filter(x=>Number(x.id)>0).map(x=>Number(x.id)||0));}

export function SupportAccountChatWidget({customerToken}:Props){
  const {pick}=useI18n();const {brand}=useBranding();
  const [open,setOpen]=useState(false);const [initialized,setInitialized]=useState(false);const [loading,setLoading]=useState(false);const [sending,setSending]=useState(false);
  const [ticket,setTicket]=useState<ChatTicket|null>(null);const [draft,setDraft]=useState("");const [error,setError]=useState("");const [image,setImage]=useState<File|null>(null);const [preview,setPreview]=useState("");
  const [emojiOpen,setEmojiOpen]=useState(false);const [stickerOpen,setStickerOpen]=useState(false);
  const fileRef=useRef<HTMLInputElement|null>(null);const endRef=useRef<HTMLDivElement|null>(null);const busy=useRef(false);const deltaBusy=useRef(false);const ticketRef=useRef<ChatTicket|null>(null);const lastAdminMessage=useRef(0);const soundReady=useRef(false);

  useEffect(()=>{try{setOpen(localStorage.getItem(OPEN_KEY)==="1");}catch{}const prime=()=>{void primeNotificationSound();soundReady.current=true;};window.addEventListener("pointerdown",prime,{once:true});window.addEventListener("keydown",prime,{once:true});return()=>{window.removeEventListener("pointerdown",prime);window.removeEventListener("keydown",prime);};},[]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);

  const scrollBottom=()=>window.setTimeout(()=>endRef.current?.scrollIntoView({behavior:"smooth",block:"end"}),10);
  const applyTicket=(next:ChatTicket,play=true)=>{const nextAdmin=maxAdminMessageId(next);if(play&&lastAdminMessage.current>0&&nextAdmin>lastAdminMessage.current&&soundReady.current)void playNotificationSound("message");lastAdminMessage.current=Math.max(lastAdminMessage.current,nextAdmin);ticketRef.current=next;setTicket(next);setInitialized(true);};

  const applyFastReply=(sent:ChatFastReply,tempId?:number)=>{const current=ticketRef.current;if(!current||current.id!==sent.ticket_id)return;const cleaned=(current.messages||[]).filter(x=>x.id!==tempId&&x.id!==sent.message.id);applyTicket({...current,status:sent.status,messages:[...cleaned,sent.message]},false);};

  const refresh=async(silent=false)=>{if(busy.current)return;busy.current=true;if(!silent)setLoading(true);try{const rows=await api<ChatTicket[]>("/v1/support/tickets/me",customerToken);const current=rows.find(x=>x.status!=="closed")??rows[0]??null;if(!current){ticketRef.current=null;setTicket(null);setInitialized(true);setError("");return;}const detail=await api<ChatTicket>(`/v1/support/tickets/${current.id}`,customerToken);applyTicket(detail,silent);setError("");}catch(reason){if(!silent)setError(reason instanceof Error?reason.message:pick("دریافت گفتگو ناموفق بود","Could not load chat"));setInitialized(true);}finally{busy.current=false;if(!silent)setLoading(false);}};

  const refreshDelta=async()=>{const current=ticketRef.current;if(!current||current.id<=0||deltaBusy.current)return;deltaBusy.current=true;try{const delta=await api<ChatDelta>(`/v1/support/tickets/${current.id}/messages-after?after_id=${maxMessageId(current)}`,customerToken);const latest=ticketRef.current;if(!latest||latest.id!==delta.ticket_id)return;const existing=new Set((latest.messages||[]).map(x=>x.id));const incoming=(delta.messages||[]).filter(x=>!existing.has(x.id));if(incoming.length||delta.status!==latest.status){applyTicket({...latest,status:delta.status||latest.status,messages:[...(latest.messages||[]),...incoming]},true);}}catch{}finally{deltaBusy.current=false;}};

  useEffect(()=>{if(open)void refresh(false);},[open,customerToken]);
  useEffect(()=>{if(!open||!ticket)return;const timer=window.setInterval(()=>{if(document.visibilityState==="visible")void refreshDelta();},500);return()=>clearInterval(timer);},[open,ticket?.id,customerToken]);
  useEffect(()=>{if(open&&ticket?.messages?.length)scrollBottom();},[open,ticket?.messages?.length]);

  const setOpenPersist=(value:boolean)=>{setOpen(value);try{localStorage.setItem(OPEN_KEY,value?"1":"0");}catch{}if(value)void primeNotificationSound();};
  const resetImage=()=>{if(preview)URL.revokeObjectURL(preview);setImage(null);setPreview("");if(fileRef.current)fileRef.current.value="";};
  const chooseImage=(file?:File|null)=>{if(!file)return;if(!ALLOWED_IMAGES.has(file.type)){setError(pick("فرمت تصویر پشتیبانی نمی‌شود","Unsupported image format"));return;}if(file.size>MAX_IMAGE_BYTES){setError(pick("حداکثر حجم تصویر ۵ مگابایت است","Maximum image size is 5 MB"));return;}if(preview)URL.revokeObjectURL(preview);setImage(file);setPreview(URL.createObjectURL(file));setError("");};

  const uploadImage=async(ticketId:number)=>{if(!image)return null;const response=await fetch(`${API_BASE}/v1/support/tickets/${ticketId}/upload-image`,{method:"POST",headers:{Authorization:`Bearer ${customerToken}`,"Content-Type":image.type||"application/octet-stream"},body:image,cache:"no-store",signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error(pick("آپلود تصویر ناموفق بود","Image upload failed"));return response.json() as Promise<UploadResult>;};

  const createConversation=async(firstMessage:string)=>{return api<ChatTicket>("/v1/support/tickets",customerToken,{method:"POST",body:JSON.stringify({category:"other",subject:pick("پشتیبانی پنل","Panel support"),message:firstMessage})});};

  const sendText=async(textValue:string)=>{const currentTicket=ticketRef.current??ticket;const text=textValue.trim();if(!text||sending)return;setSending(true);setError("");const temp:ChatMessage={id:-Date.now(),sender_role:"user",message:text,created_at:new Date().toISOString(),_pending:true};if(currentTicket){const optimistic={...currentTicket,messages:[...(currentTicket.messages||[]),temp]};ticketRef.current=optimistic;setTicket(optimistic);}setDraft("");scrollBottom();try{if(currentTicket){const sent=await api<ChatFastReply>(`/v1/support/tickets/${currentTicket.id}/messages-fast`,customerToken,{method:"POST",body:JSON.stringify({message:text,source:"web"})});applyFastReply(sent,temp.id);}else{const next=await createConversation(text);applyTicket(next,false);}}catch(reason){const latest=ticketRef.current;if(latest){const restored={...latest,messages:(latest.messages||[]).filter(x=>x.id!==temp.id)};ticketRef.current=restored;setTicket(restored);}setDraft(text);setError(reason instanceof Error?reason.message:pick("ارسال پیام ناموفق بود","Could not send message"));}finally{setSending(false);}};

  const submit=async(event:FormEvent)=>{event.preventDefault();if(sending)return;const text=draft.trim();if(!text&&!image)return;if(text&&!image){await sendText(text);return;}setSending(true);setError("");try{let current=ticket;if(!current)current=await createConversation(text||pick("تصویر ارسال شد","Image sent"));else if(text)current=await api<ChatTicket>(`/v1/support/tickets/${current.id}/messages`,customerToken,{method:"POST",body:JSON.stringify({message:text,source:"web"})});if(image&&current){const uploaded=await uploadImage(current.id);if(uploaded)current=await api<ChatTicket>(`/v1/support/tickets/${current.id}/messages`,customerToken,{method:"POST",body:JSON.stringify({message:null,attachment_type:uploaded.attachment_type,attachment_ref:uploaded.attachment_ref,source:"web"})});}if(current)applyTicket(current,false);setDraft("");resetImage();scrollBottom();}catch(reason){setError(reason instanceof Error?reason.message:pick("ارسال پیام ناموفق بود","Could not send message"));}finally{setSending(false);}};

  const messages=ticket?.messages||[];
  const emojiPicker=<div className="supportEmojiRootV3"><button type="button" className="supportEmojiButtonV3" onClick={()=>{setEmojiOpen(v=>!v);setStickerOpen(false);}}>☺</button>{emojiOpen&&<div className="supportEmojiPickerV3">{CHAT_EMOJIS.map(x=><button type="button" key={x} onClick={()=>{setDraft(v=>v+x);setEmojiOpen(false);}}>{x}</button>)}</div>}</div>;
  const stickerPicker=<div className="supportEmojiRootV3"><button type="button" className="supportEmojiButtonV3" title={pick("استیکر","Sticker")} onClick={()=>{setStickerOpen(v=>!v);setEmojiOpen(false);}}>✨</button>{stickerOpen&&<div className="supportEmojiPickerV3">{STICKERS.map(x=><button type="button" key={x} onClick={()=>{setStickerOpen(false);void sendText(x);}}>{x}</button>)}</div>}</div>;

  return <div className="supportChatRoot"><input ref={fileRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/gif" onChange={e=>chooseImage(e.target.files?.[0])}/>{open&&<section className="supportChatWindow"><header className="supportChatHeader"><div className="supportChatHeaderInfo"><span className="supportChatStatus"/><div><b>{pick("پشتیبانی پنل","Panel support")}</b><small>{brand.name}</small></div></div><button type="button" className="supportChatClose" onClick={()=>setOpenPersist(false)}>×</button></header><div className="supportChatBody">
    {loading&&!initialized&&<div className="supportChatState">{pick("در حال دریافت گفتگو...","Loading chat...")}</div>}
    {initialized&&!ticket&&<form className="supportChatStart" onSubmit={submit}><h3>{pick("پیام به پشتیبانی","Message support")}</h3><label><span>{pick("پیام","Message")}</span><textarea value={draft} onChange={e=>setDraft(e.target.value)} rows={4}/></label>{preview&&<div className="supportChatImagePreview"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}<div className="supportChatStartTools"><div className="supportChatToolRow">{emojiPicker}{stickerPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎 {pick("تصویر","Image")}</button></div>{error&&<div className="supportChatError">{error}</div>}</div><button type="submit" className="supportChatPrimary" disabled={sending||(!draft.trim()&&!image)}>{sending?pick("در حال ارسال...","Sending..."):pick("ارسال پیام","Send message")}</button></form>}
    {ticket&&<><div className="supportChatMessages">{messages.map(item=>{const own=item.sender_role==="user";return <article key={item.id} className={own?"supportChatMessage own":"supportChatMessage admin"}><small>{own?pick("شما","You"):pick("پشتیبانی","Support")}</small>{item.message&&<p>{item.message}</p>}{item.attachment_ref&&<a href={attachmentUrl(item.attachment_ref)} target="_blank" rel="noreferrer"><img className="supportChatImage" src={attachmentUrl(item.attachment_ref)} alt=""/></a>}<time>{new Date(item.created_at).toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit"})}</time></article>})}<div ref={endRef}/></div><form className="supportChatComposer" onSubmit={submit}>{preview&&<div className="supportChatImagePreview compact"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}{error&&<div className="supportChatError">{error}</div>}<div>{emojiPicker}{stickerPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎</button><textarea value={draft} onChange={e=>setDraft(e.target.value)} placeholder={pick("پیام...","Message...")} rows={1}/><button className="supportChatSend" type="submit" disabled={sending||(!draft.trim()&&!image)}>{sending?"…":pick("ارسال","Send")}</button></div></form></>}
  </div></section>}<button type="button" className={open?"supportChatLauncher active":"supportChatLauncher"} onClick={()=>setOpenPersist(!open)}><span className="supportChatLauncherIcon">{open?"×":"✦"}</span>{!open&&<span><b>{pick("پشتیبانی پنل","Panel support")}</b><small>{pick("گفتگو با پشتیبانی","Chat with support")}</small></span>}</button></div>;
}
