"use client";

import type {ReactNode} from "react";
import {DEFAULT_STORE_TEMPLATE_ID,resolveStoreTemplateId} from "../lib/store-template-registry";
import {EditorialGrid2027Template} from "./store-template-editorial-grid";
import {StoreTemplateRenderer,type StoreTemplateProps} from "./store-template-renderer";

export type StoreTemplateRuntimeRenderer=(props:StoreTemplateProps)=>ReactNode;

const STORE_TEMPLATE_RUNTIME_RENDERERS:Record<string,StoreTemplateRuntimeRenderer>={
  "conversion-2027":props=><StoreTemplateRenderer {...props}/>,
  "editorial-grid-2027":props=><EditorialGrid2027Template {...props}/>,
};

export function installedStoreTemplateRuntime(templateId:unknown){
  const resolved=resolveStoreTemplateId(templateId);
  return STORE_TEMPLATE_RUNTIME_RENDERERS[resolved]||STORE_TEMPLATE_RUNTIME_RENDERERS[DEFAULT_STORE_TEMPLATE_ID];
}

export function StoreTemplateRuntime({templateId,...props}:StoreTemplateProps&{templateId:string}){
  const renderer=installedStoreTemplateRuntime(templateId);
  return <>{renderer(props)}</>;
}
