"use client";

import {useEffect} from "react";

const MODAL_SELECTOR=".runtime-modal";
const SUCCESS_SELECTOR=".runtime-success,.runtime-alert.success,.alert.success";
const ERROR_SELECTOR=".runtime-error,.runtime-alert.error,.alert.error";
const ACTION_SELECTOR="button[type='submit'],input[type='submit'],button.primary,button.primary-soft,button.danger,button.danger-btn";
const CLOSE_SELECTOR="button.icon-button,button.runtime-modal-bg";
const MUTATING_METHODS=new Set(["POST","PUT","PATCH","DELETE"]);

function mutationTouches(record:MutationRecord,selector:string){
  const target=record.target instanceof Element?record.target:record.target.parentElement;
  if(target&&(target.matches(selector)||Boolean(target.closest(selector))))return true;
  for(const node of record.addedNodes){
    if(!(node instanceof Element))continue;
    if(node.matches(selector)||Boolean(node.querySelector(selector)))return true;
  }
  return false;
}

function requestMethod(input:RequestInfo|URL,init?:RequestInit){
  if(init?.method)return init.method.toUpperCase();
  if(typeof Request!=="undefined"&&input instanceof Request)return input.method.toUpperCase();
  return "GET";
}

export function ModalAutoCloseOnSuccess(){
  useEffect(()=>{
    let armedUntil=0;
    let completionUntil=0;
    let armTimer:number|undefined;
    let closeTimer:number|undefined;
    const nativeFetch=window.fetch.bind(window);

    const clearArm=()=>{
      armedUntil=0;
      if(armTimer!==undefined){window.clearTimeout(armTimer);armTimer=undefined;}
    };

    const clearCompletion=()=>{
      completionUntil=0;
      if(closeTimer!==undefined){window.clearTimeout(closeTimer);closeTimer=undefined;}
    };

    const arm=()=>{
      armedUntil=Date.now()+10*60*1000;
      if(armTimer!==undefined)window.clearTimeout(armTimer);
      armTimer=window.setTimeout(clearArm,10*60*1000);
    };

    const attemptClose=()=>{
      const now=Date.now();
      if(!completionUntil||now>completionUntil){clearCompletion();clearArm();return;}

      const modals=Array.from(document.querySelectorAll<HTMLElement>(MODAL_SELECTOR));
      const visible=modals.filter(modal=>modal.offsetParent!==null);
      const modal=visible.length?visible[visible.length-1]:undefined;

      if(modal){
        const candidates=Array.from(modal.querySelectorAll<HTMLButtonElement>(CLOSE_SELECTOR));
        const close=candidates.find(button=>!button.disabled&&button.offsetParent!==null);
        if(close)close.click();
      }

      if(Date.now()<completionUntil){
        closeTimer=window.setTimeout(attemptClose,120);
      }else{
        clearCompletion();
        clearArm();
      }
    };

    const scheduleClose=(replacementWindowMs=8000)=>{
      completionUntil=Math.max(completionUntil,Date.now()+replacementWindowMs);
      if(closeTimer!==undefined)window.clearTimeout(closeTimer);
      closeTimer=window.setTimeout(attemptClose,40);
    };

    const onClick=(event:MouseEvent)=>{
      const target=event.target;
      if(!(target instanceof Element))return;
      const modal=target.closest(MODAL_SELECTOR);
      if(!modal)return;
      const action=target.closest(ACTION_SELECTOR);
      if(!action||action.matches(CLOSE_SELECTOR))return;
      arm();
    };

    const onSubmit=(event:SubmitEvent)=>{
      const form=event.target;
      if(!(form instanceof HTMLFormElement))return;
      if(form.closest(MODAL_SELECTOR))arm();
    };

    const observer=new MutationObserver(records=>{
      const now=Date.now();
      if(completionUntil&&now<completionUntil&&records.some(record=>mutationTouches(record,MODAL_SELECTOR))){
        scheduleClose(Math.max(250,completionUntil-now));
        return;
      }
      if(!armedUntil||now>armedUntil)return;
      if(records.some(record=>mutationTouches(record,ERROR_SELECTOR))){clearCompletion();clearArm();return;}
      if(records.some(record=>mutationTouches(record,SUCCESS_SELECTOR)))scheduleClose();
    });

    window.fetch=async(input:RequestInfo|URL,init?:RequestInit)=>{
      const method=requestMethod(input,init);
      try{
        const response=await nativeFetch(input,init);
        if(armedUntil&&Date.now()<=armedUntil&&MUTATING_METHODS.has(method)){
          if(response.ok)scheduleClose();
          else{clearCompletion();clearArm();}
        }
        return response;
      }catch(error){
        if(armedUntil&&MUTATING_METHODS.has(method)){clearCompletion();clearArm();}
        throw error;
      }
    };

    document.addEventListener("click",onClick,true);
    document.addEventListener("submit",onSubmit,true);
    observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:["class","disabled"]});

    return()=>{
      document.removeEventListener("click",onClick,true);
      document.removeEventListener("submit",onSubmit,true);
      observer.disconnect();
      window.fetch=nativeFetch;
      if(armTimer!==undefined)window.clearTimeout(armTimer);
      if(closeTimer!==undefined)window.clearTimeout(closeTimer);
    };
  },[]);

  return null;
}
