"use client";

import type {CSSProperties,ReactNode} from "react";
import {ADVANCED_COLOR_SLOTS,ADVANCED_LAYOUT_KEYS,advancedColor,advancedString} from "../lib/storefront-advanced-design";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import styles from "./storefront-advanced-design-runtime.module.css";

type Props={templateId:string;themeOptions:StoreTemplateOptionMap;children:ReactNode};

type RuntimeStyle=CSSProperties&Record<`--${string}`,string>;

export function StorefrontAdvancedDesignRuntime({templateId,themeOptions,children}:Props){
  const style:RuntimeStyle={} as RuntimeStyle;
  const attrs:Record<string,string>={"data-template":templateId};

  for(const mode of ["dark","light"] as const){
    for(const slot of ADVANCED_COLOR_SLOTS){
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

  return <div className={styles.runtime} style={style} {...attrs}>{children}</div>;
}
