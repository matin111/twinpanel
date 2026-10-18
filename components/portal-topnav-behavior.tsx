"use client";

import {useEffect} from "react";

const GROUP_SELECTOR=".customer-portal-topnav-group";
const PANEL_NAV_LINK_SELECTOR=[
  ".admin-topnav a[href]",
  ".customer-portal-topnav a[href]",
  ".customer-portal-nav a[href]"
].join(",");

function closeGroups(except:HTMLDetailsElement|null=null){
  document.querySelectorAll<HTMLDetailsElement>(GROUP_SELECTOR).forEach(group=>{
    if(group!==except)group.open=false;
  });
}

function shouldUseNativeNavigation(event:MouseEvent,anchor:HTMLAnchorElement){
  if(event.button!==0)return false;
  if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return false;
  if(anchor.target&&anchor.target!=="_self")return false;
  if(anchor.hasAttribute("download"))return false;

  const url=new URL(anchor.href,window.location.href);
  if(url.origin!==window.location.origin)return false;

  const current=`${window.location.pathname}${window.location.search}${window.location.hash}`;
  const next=`${url.pathname}${url.search}${url.hash}`;
  return next!==current;
}

export function PortalTopNavBehavior(){
  useEffect(()=>{
    const onClick=(event:MouseEvent)=>{
      const target=event.target as HTMLElement|null;
      if(!target)return;

      const navAnchor=target.closest<HTMLAnchorElement>(PANEL_NAV_LINK_SELECTOR);
      if(navAnchor&&shouldUseNativeNavigation(event,navAnchor)){
        closeGroups();
        event.preventDefault();
        event.stopImmediatePropagation();
        window.location.assign(navAnchor.href);
        return;
      }

      const group=target.closest<HTMLDetailsElement>(GROUP_SELECTOR);
      const summary=target.closest("summary");
      if(group&&summary&&group.contains(summary)){
        closeGroups(group);
        return;
      }

      if(target.closest(`${GROUP_SELECTOR} a`)){
        closeGroups();
        return;
      }

      if(!target.closest(".customer-portal-topnav"))closeGroups();
    };

    const onKeyDown=(event:KeyboardEvent)=>{
      if(event.key==="Escape")closeGroups();
    };

    document.addEventListener("click",onClick,true);
    document.addEventListener("keydown",onKeyDown);
    return()=>{
      document.removeEventListener("click",onClick,true);
      document.removeEventListener("keydown",onKeyDown);
    };
  },[]);

  return null;
}
