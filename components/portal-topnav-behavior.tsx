"use client";

import {useEffect} from "react";

const GROUP_SELECTOR=".customer-portal-topnav-group";

function closeGroups(except:HTMLDetailsElement|null=null){
  document.querySelectorAll<HTMLDetailsElement>(GROUP_SELECTOR).forEach(group=>{
    if(group!==except)group.open=false;
  });
}

export function PortalTopNavBehavior(){
  useEffect(()=>{
    const onClick=(event:MouseEvent)=>{
      const target=event.target as HTMLElement|null;
      if(!target)return;

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
