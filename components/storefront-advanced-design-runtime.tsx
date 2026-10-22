"use client";

import {useEffect,useRef,type CSSProperties,type ReactNode} from "react";
import {ADVANCED_COLOR_SLOTS,ADVANCED_LAYOUT_KEYS,advancedColor,advancedString} from "../lib/storefront-advanced-design";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import styles from "./storefront-advanced-design-runtime.module.css";

type Props={templateId:string;themeOptions:StoreTemplateOptionMap;children:ReactNode};
type RuntimeStyle=CSSProperties&Record<`--${string}`,string>;
type CardKind="plan"|"protocol"|"service"|"guide"|"account"|"faq"|"contact";
type GridKind="plans"|"protocols"|"services";
type ActionKind="primary"|"secondary";

function tagAll(root:HTMLElement,selector:string,attribute:string,value:string){
  root.querySelectorAll<HTMLElement>(selector).forEach(element=>element.setAttribute(attribute,value));
}

function tagCard(root:HTMLElement,selector:string,kind:CardKind){tagAll(root,selector,"data-store-card",kind);}
function tagGrid(root:HTMLElement,selector:string,kind:GridKind){tagAll(root,selector,"data-store-grid",kind);}
function tagAction(root:HTMLElement,selector:string,kind:ActionKind){tagAll(root,selector,"data-store-action",kind);}

function applySemanticStorefrontMap(root:HTMLElement){
  tagCard(root,"#plans article","plan");
  tagCard(root,"#protocols article","protocol");
  tagCard(root,"#services article","service");
  tagCard(root,"#guides > div:last-child","guide");
  tagCard(root,"#account > div:first-child","account");
  tagCard(root,"#account article","account");
  tagCard(root,"#faq details","faq");
  tagCard(root,"#contact a, #contact button","contact");

  tagGrid(root,"#plans div:has(> article)","plans");
  tagGrid(root,"#protocols div:has(> article)","protocols");
  tagGrid(root,"#services div:has(> article)","services");

  tagAction(root,'.tpStorePrimary, .tpStoreHeaderBuy, .tpStoreBuyButton, #plans button, main a[href="#plans"], #account a[href="/panel"]',"primary");
  tagAction(root,'.tpStoreSecondary, .tpStoreLogin, main a[href="#guides"], #account button',"secondary");
}

export function StorefrontAdvancedDesignRuntime({templateId,themeOptions,children}:Props){
  const rootRef=useRef<HTMLDivElement|null>(null);
  const style:RuntimeStyle={} as RuntimeStyle;
  const attrs:Record<string,string>={"data-template":templateId};

  for(const slot of ADVANCED_COLOR_SLOTS){
    const unified=advancedColor(themeOptions,`ui_${slot}`);
    if(unified){
      for(const mode of ["dark","light"] as const){
        const cssName=`--ui-${mode}-${slot.replaceAll("_","-")}` as `--${string}`;
        style[cssName]=unified;
        attrs[`data-ui-${mode}-${slot.replaceAll("_","-")}`]="on";
      }
      continue;
    }
    for(const mode of ["dark","light"] as const){
      const key=`ui_${mode}_${slot}`;
      const color=advancedColor(themeOptions,key);
      if(!color)continue;
      const cssName=`--ui-${mode}-${slot.replaceAll("_","-")}` as `--${string}`;
      style[cssName]=color;
      attrs[`data-ui-${mode}-${slot.replaceAll("_","-")}`]="on";
    }
  }

  for(const key of ADVANCED_LAYOUT_KEYS){
    const value=advancedString(themeOptions,key,"native");
    if(value==="native")continue;
    attrs[`data-${key.replaceAll("_","-")}`]=value;
  }

  useEffect(()=>{
    const root=rootRef.current;
    if(!root)return;
    const apply=()=>applySemanticStorefrontMap(root);
    apply();
    const observer=new MutationObserver(apply);
    observer.observe(root,{childList:true,subtree:true});
    return()=>observer.disconnect();
  },[templateId]);

  return <div ref={rootRef} className={styles.runtime} style={style} {...attrs}>{children}</div>;
}
