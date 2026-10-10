"use client";

import {useEffect} from "react";

const MODAL_SELECTOR=".runtime-modal";
const SUCCESS_SELECTOR=".runtime-success,.runtime-alert.success,.alert.success";
const ERROR_SELECTOR=".runtime-error,.runtime-alert.error,.alert.error";
const ACTION_SELECTOR="button[type='submit'],input[type='submit'],button.primary,button.primary-soft,button.danger,button.danger-btn";
const CLOSE_SELECTOR="button.icon-button,button.runtime-modal-bg";

function mutationTouches(record:MutationRecord,selector:string){
  const target=record.target instanceof Element?record.target:record.target.parentElement;
  if(target&&(target.matches(selector)||Boolean(target.closest(selector))))return true;
  for(const node of record.addedNodes){
    if(!(node instanceof Element))continue;
    if(node.matches(selector)||Boolean(node.querySelector(selector)))return true;
  }
  return false;
}

export function ModalAutoCloseOnSuccess(){
  useEffect(()=>{
    let armedUntil=0;
    let armTimer:number|undefined;
    let closeTimer:number|undefined;
    let closeStartedAt=0;

    const clearArm=()=>{
      armedUntil=0;
      if(armTimer!==undefined){window.clearTimeout(armTimer);armTimer=undefined;}
    };

    const arm=()=>{
      armedUntil=Date.now()+10*60*1000;
      if(armTimer!==undefined)window.clearTimeout(armTimer);
      armTimer=window.setTimeout(clearArm,10*60*1000);
    };

    const attemptClose=()=>{
      if(!armedUntil||Date.now()>armedUntil){clearArm();return;}
      const modals=Array.from(document.querySelectorAll<HTMLElement>(MODAL_SELECTOR));
      const modal=modals.length?modals[modals.length-1]:undefined;
      if(!modal){clearArm();return;}

      const candidates=Array.from(modal.querySelectorAll<HTMLButtonElement>(CLOSE_SELECTOR));
      const close=candidates.find(button=>!button.disabled&&button.offsetParent!==null);
      if(close){
        close.click();
        clearArm();
        return;
      }

      if(Date.now()-closeStartedAt<5000){
        closeTimer=window.setTimeout(attemptClose,100);
      }else{
        clearArm();
      }
    };

    const scheduleClose=()=>{
      closeStartedAt=Date.now();
      if(closeTimer!==undefined)window.clearTimeout(closeTimer);
      closeTimer=window.setTimeout(attemptClose,80);
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
      if(!armedUntil||Date.now()>armedUntil)return;

      if(records.some(record=>mutationTouches(record,ERROR_SELECTOR))){
        clearArm();
        return;
      }

      if(records.some(record=>mutationTouches(record,SUCCESS_SELECTOR))){
        scheduleClose();
      }
    });

    document.addEventListener("click",onClick,true);
    document.addEventListener("submit",onSubmit,true);
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});

    return()=>{
      document.removeEventListener("click",onClick,true);
      document.removeEventListener("submit",onSubmit,true);
      observer.disconnect();
      if(armTimer!==undefined)window.clearTimeout(armTimer);
      if(closeTimer!==undefined)window.clearTimeout(closeTimer);
    };
  },[]);

  return null;
}
