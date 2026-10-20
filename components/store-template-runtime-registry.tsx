"use client";

import type {ReactNode} from "react";
import {DEFAULT_STORE_TEMPLATE_ID,resolveStoreTemplateId} from "../lib/store-template-registry";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {EditorialPro2027Template} from "./store-template-editorial-pro";
import {StoreTemplateRenderer,type StoreTemplateProps} from "./store-template-renderer";

export type StoreThemeRuntimeProps=StoreTemplateProps&{
  templateId:string;
  themeOptions:StoreTemplateOptionMap;
};

export type StoreTemplateRuntimeRenderer=(props:StoreThemeRuntimeProps)=>ReactNode;

const STORE_TEMPLATE_RUNTIME_RENDERERS:Record<string,StoreTemplateRuntimeRenderer>={
  "conversion-2027":({templateId:_,themeOptions:__,...props})=><StoreTemplateRenderer {...props}/>,
  "editorial-grid-2027":({templateId:_,themeOptions,...props})=><EditorialPro2027Template themeOptions={themeOptions} {...props}/>,
};

export function installedStoreTemplateRuntime(templateId:unknown){
  const resolved=resolveStoreTemplateId(templateId);
  return STORE_TEMPLATE_RUNTIME_RENDERERS[resolved]||STORE_TEMPLATE_RUNTIME_RENDERERS[DEFAULT_STORE_TEMPLATE_ID];
}

export function StoreTemplateRuntime(props:StoreThemeRuntimeProps){
  const renderer=installedStoreTemplateRuntime(props.templateId);
  return <>{renderer(props)}</>;
}
