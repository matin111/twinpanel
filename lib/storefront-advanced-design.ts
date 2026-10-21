import type {StoreTemplateOptionMap} from "./store-template-options";

export type AdvancedDesignMode="dark"|"light";
export type AdvancedDesignTemplateId="conversion-2027"|"editorial-grid-2027"|"orbit-neo-2027"|string;

export const ADVANCED_COLOR_SLOTS=[
  "primary_bg","primary_text","secondary_bg","secondary_text",
  "plan_bg","protocol_bg","service_bg","guide_bg","account_bg","faq_bg","contact_bg",
  "card_text","muted","border",
] as const;

export const ADVANCED_LAYOUT_KEYS=[
  "ui_card_size","ui_card_shape","ui_card_effect","ui_plan_layout","ui_protocol_layout","ui_service_layout","ui_button_size","ui_button_shape",
] as const;

export const ADVANCED_DESIGN_KEYS=[
  ...ADVANCED_COLOR_SLOTS.flatMap(slot=>[`ui_dark_${slot}`,`ui_light_${slot}`]),
  ...ADVANCED_LAYOUT_KEYS,
] as const;

export const ADVANCED_LAYOUT_DEFAULTS={
  ui_card_size:"native",
  ui_card_shape:"native",
  ui_card_effect:"native",
  ui_plan_layout:"native",
  ui_protocol_layout:"native",
  ui_service_layout:"native",
  ui_button_size:"native",
  ui_button_shape:"native",
} as const;

const conversionDark={
  primary_bg:"#7c3aed",primary_text:"#ffffff",secondary_bg:"#0f1526",secondary_text:"#f7f8ff",
  plan_bg:"#101728",protocol_bg:"#0f1526",service_bg:"#0f1526",guide_bg:"#0f1526",account_bg:"#0f1526",faq_bg:"#0f1526",contact_bg:"#0f1526",
  card_text:"#f7f8ff",muted:"#9aa7bf",border:"#202b42",
};
const conversionLight={
  primary_bg:"#7c3aed",primary_text:"#ffffff",secondary_bg:"#ffffff",secondary_text:"#273244",
  plan_bg:"#ffffff",protocol_bg:"#ffffff",service_bg:"#ffffff",guide_bg:"#ffffff",account_bg:"#ffffff",faq_bg:"#ffffff",contact_bg:"#ffffff",
  card_text:"#111827",muted:"#667085",border:"#d7dee8",
};
const editorialDark={
  primary_bg:"#f7f3ec",primary_text:"#0f1014",secondary_bg:"#1b1e24",secondary_text:"#f7f3ec",
  plan_bg:"#15171c",protocol_bg:"#15171c",service_bg:"#15171c",guide_bg:"#15171c",account_bg:"#15171c",faq_bg:"#15171c",contact_bg:"#15171c",
  card_text:"#f7f3ec",muted:"#a8a29a",border:"#30343b",
};
const editorialLight={
  primary_bg:"#171719",primary_text:"#fffdf9",secondary_bg:"#f8f4ed",secondary_text:"#171719",
  plan_bg:"#fffdf9",protocol_bg:"#fffdf9",service_bg:"#fffdf9",guide_bg:"#fffdf9",account_bg:"#fffdf9",faq_bg:"#fffdf9",contact_bg:"#fffdf9",
  card_text:"#171719",muted:"#67635d",border:"#d8d1c8",
};
const orbitDark={
  primary_bg:"#6d5dfc",primary_text:"#ffffff",secondary_bg:"#131824",secondary_text:"#f8fafc",
  plan_bg:"#0c0f16",protocol_bg:"#0c0f16",service_bg:"#0c0f16",guide_bg:"#0c0f16",account_bg:"#0c0f16",faq_bg:"#0c0f16",contact_bg:"#0c0f16",
  card_text:"#f8fafc",muted:"#9aa4b5",border:"#253043",
};
const orbitLight={
  primary_bg:"#6d5dfc",primary_text:"#ffffff",secondary_bg:"#edf1f8",secondary_text:"#10131a",
  plan_bg:"#ffffff",protocol_bg:"#ffffff",service_bg:"#ffffff",guide_bg:"#ffffff",account_bg:"#ffffff",faq_bg:"#ffffff",contact_bg:"#ffffff",
  card_text:"#10131a",muted:"#667085",border:"#d9e0ec",
};

export function advancedDesignFallbacks(templateId:AdvancedDesignTemplateId,mode:AdvancedDesignMode):Record<string,string>{
  const palette=templateId==="editorial-grid-2027"
    ?(mode==="dark"?editorialDark:editorialLight)
    :templateId==="orbit-neo-2027"
      ?(mode==="dark"?orbitDark:orbitLight)
      :(mode==="dark"?conversionDark:conversionLight);
  return Object.fromEntries(Object.entries(palette).map(([key,value])=>[`ui_${mode}_${key}`,value]));
}

export function advancedString(options:StoreTemplateOptionMap,key:string,fallback="native"){
  const value=options[key];
  return typeof value==="string"&&value.trim()?value:fallback;
}

export function hasAdvancedValue(options:StoreTemplateOptionMap,key:string){
  const value=options[key];
  return typeof value==="string"&&value.trim().length>0;
}

export function advancedColor(options:StoreTemplateOptionMap,key:string){
  const value=options[key];
  return typeof value==="string"&&/^#[0-9a-fA-F]{6}$/.test(value)?value:"";
}
