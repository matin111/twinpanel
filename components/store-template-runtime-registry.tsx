"use client";

import type {CSSProperties,ReactNode} from "react";
import {DEFAULT_STORE_TEMPLATE_ID,resolveStoreTemplateId} from "../lib/store-template-registry";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {ConversionPro2027Template} from "./store-template-conversion-pro";
import {EditorialPro2027Template} from "./store-template-editorial-pro";
import editorialBridge from "./store-template-editorial-theme-bridge.module.css";
import type {StoreTemplateProps} from "./store-template-renderer";

export type StoreThemeRuntimeProps=StoreTemplateProps&{
  templateId:string;
  themeOptions:StoreTemplateOptionMap;
};

export type StoreTemplateRuntimeRenderer=(props:StoreThemeRuntimeProps)=>ReactNode;

function option(options:StoreTemplateOptionMap,key:string,fallback:string){
  const value=options[key];
  return typeof value==="string"&&value.trim()?value:fallback;
}

function editorialThemeStyle(options:StoreTemplateOptionMap){
  return {
    "--ep-theme-primary":option(options,"theme_primary","#8b5cf6"),
    "--ep-theme-secondary":option(options,"theme_secondary","#6366f1"),
    "--ep-theme-page":option(options,"editorial_page_bg","#0f1014"),
    "--ep-theme-surface":option(options,"editorial_surface_bg","#15171c"),
    "--ep-theme-surface-alt":option(options,"editorial_surface_alt","#1b1e24"),
    "--ep-theme-border":option(options,"editorial_border","#30343b"),
    "--ep-theme-header":option(options,"editorial_header_bg","#15171c"),
    "--ep-theme-footer":option(options,"editorial_footer_bg","#0f1014"),
    "--ep-theme-text":option(options,"editorial_text","#f7f3ec"),
    "--ep-theme-muted":option(options,"editorial_muted","#a8a29a"),
    "--ep-theme-button":option(options,"editorial_button_bg","#f7f3ec"),
    "--ep-theme-button-text":option(options,"editorial_button_text","#0f1014"),
  } as CSSProperties;
}

const STORE_TEMPLATE_RUNTIME_RENDERERS:Record<string,StoreTemplateRuntimeRenderer>={
  "conversion-2027":({templateId:_,themeOptions,...props})=><ConversionPro2027Template themeOptions={themeOptions} {...props}/>,
  "editorial-grid-2027":({templateId:_,themeOptions,...props})=><div className={editorialBridge.themeBridge} style={editorialThemeStyle(themeOptions)}><EditorialPro2027Template themeOptions={themeOptions} {...props}/></div>,
};

export function installedStoreTemplateRuntime(templateId:unknown){
  const resolved=resolveStoreTemplateId(templateId);
  return STORE_TEMPLATE_RUNTIME_RENDERERS[resolved]||STORE_TEMPLATE_RUNTIME_RENDERERS[DEFAULT_STORE_TEMPLATE_ID];
}

export function StoreTemplateRuntime(props:StoreThemeRuntimeProps){
  const renderer=installedStoreTemplateRuntime(props.templateId);
  return <>{renderer(props)}</>;
}
