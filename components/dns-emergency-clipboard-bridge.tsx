"use client";

import {useEffect} from "react";

import {DnsEmergencyPanel} from "./dns-emergency-panel";

const MANUAL_COPY_ID="twinpanel-netmod-manual-copy";

function showManualCopy(value:string){
  document.getElementById(MANUAL_COPY_ID)?.remove();

  const panel=document.createElement("div");
  panel.id=MANUAL_COPY_ID;
  panel.dir="ltr";
  panel.style.position="fixed";
  panel.style.left="20px";
  panel.style.right="20px";
  panel.style.bottom="20px";
  panel.style.zIndex="2147483647";
  panel.style.display="grid";
  panel.style.gridTemplateColumns="minmax(0,1fr) auto";
  panel.style.gap="10px";
  panel.style.padding="12px";
  panel.style.border="1px solid rgba(139,92,246,.55)";
  panel.style.borderRadius="14px";
  panel.style.background="#111827";
  panel.style.boxShadow="0 18px 60px rgba(0,0,0,.45)";

  const textarea=document.createElement("textarea");
  textarea.value=value;
  textarea.readOnly=true;
  textarea.rows=3;
  textarea.setAttribute("aria-label","NetMod link for manual copy");
  textarea.style.width="100%";
  textarea.style.resize="vertical";
  textarea.style.padding="10px";
  textarea.style.border="1px solid rgba(255,255,255,.14)";
  textarea.style.borderRadius="10px";
  textarea.style.background="#0b1220";
  textarea.style.color="#f8fafc";
  textarea.style.fontFamily="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace";
  textarea.style.fontSize="12px";
  textarea.style.lineHeight="1.55";

  const close=document.createElement("button");
  close.type="button";
  close.textContent="×";
  close.setAttribute("aria-label","Close manual copy panel");
  close.style.width="42px";
  close.style.height="42px";
  close.style.border="1px solid rgba(255,255,255,.14)";
  close.style.borderRadius="10px";
  close.style.background="#1f2937";
  close.style.color="#fff";
  close.style.fontSize="24px";
  close.style.cursor="pointer";
  close.onclick=()=>panel.remove();

  panel.append(textarea,close);
  document.body.appendChild(panel);
  textarea.focus({preventScroll:true});
  textarea.select();
  textarea.setSelectionRange(0,value.length);
}

function legacyCopyText(value:string):Promise<void>{
  return new Promise((resolve,reject)=>{
    const textarea=document.createElement("textarea");
    textarea.value=value;
    textarea.setAttribute("readonly","");
    textarea.setAttribute("aria-hidden","true");
    textarea.style.position="fixed";
    textarea.style.inset="-10000px auto auto -10000px";
    textarea.style.opacity="0";
    document.body.appendChild(textarea);
    textarea.focus({preventScroll:true});
    textarea.select();
    textarea.setSelectionRange(0,value.length);
    try{
      const copied=document.execCommand("copy");
      showManualCopy(value);
      if(!copied)throw new Error("LEGACY_COPY_REJECTED");
      resolve();
    }catch(error){
      showManualCopy(value);
      reject(error);
    }finally{
      textarea.remove();
    }
  });
}

export function DnsEmergencyClipboardBridge(){
  useEffect(()=>{
    if(window.isSecureContext)return;

    const previous=Object.getOwnPropertyDescriptor(navigator,"clipboard");
    const installed=Reflect.defineProperty(navigator,"clipboard",{
      configurable:true,
      value:{writeText:legacyCopyText},
    });

    return ()=>{
      document.getElementById(MANUAL_COPY_ID)?.remove();
      if(!installed)return;
      if(previous){
        Reflect.defineProperty(navigator,"clipboard",previous);
      }else{
        Reflect.deleteProperty(navigator,"clipboard");
      }
    };
  },[]);

  return <DnsEmergencyPanel/>;
}
