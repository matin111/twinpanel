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

function option(options:StoreTemplateOptionMap,key:string,fallback:string){
  const value=options[key];
  return typeof value==="string"&&value.trim()?value:fallback;
}

function conversionPalette(mode:AdvancedDesignMode,options:StoreTemplateOptionMap){
  if(mode==="light"){
    return {
      primary_bg:option(options,"conversion_button_bg",option(options,"conversion_accent","#7c3aed")),primary_text:option(options,"conversion_button_text","#ffffff"),secondary_bg:"#ffffff",secondary_text:"#273244",
      plan_bg:"#ffffff",protocol_bg:"#ffffff",service_bg:"#ffffff",guide_bg:"#ffffff",account_bg:"#ffffff",faq_bg:"#ffffff",contact_bg:"#ffffff",
      card_text:"#111827",muted:"#667085",border:"#d7dee8",
    };
  }
  const card=option(options,"conversion_card_bg","#0f1526");
  return {
    primary_bg:option(options,"conversion_button_bg",option(options,"conversion_accent","#7c3aed")),primary_text:option(options,"conversion_button_text","#ffffff"),secondary_bg:card,secondary_text:option(options,"conversion_text","#f7f8ff"),
    plan_bg:card,protocol_bg:card,service_bg:card,guide_bg:card,account_bg:card,faq_bg:card,contact_bg:card,
    card_text:option(options,"conversion_text","#f7f8ff"),muted:option(options,"conversion_muted","#9aa7bf"),border:option(options,"conversion_card_border","#202b42"),
  };
}

function editorialPalette(mode:AdvancedDesignMode,options:StoreTemplateOptionMap){
  if(mode==="light"){
    return {
      primary_bg:"#171719",primary_text:"#fffdf9",secondary_bg:"#f8f4ed",secondary_text:"#171719",
      plan_bg:"#fffdf9",protocol_bg:"#fffdf9",service_bg:"#fffdf9",guide_bg:"#fffdf9",account_bg:"#fffdf9",faq_bg:"#fffdf9",contact_bg:"#fffdf9",
      card_text:"#171719",muted:"#67635d",border:"#d8d1c8",
    };
  }
  const surface=option(options,"editorial_surface_bg","#15171c");
  return {
    primary_bg:option(options,"editorial_button_bg","#f7f3ec"),primary_text:option(options,"editorial_button_text","#0f1014"),secondary_bg:option(options,"editorial_surface_alt","#1b1e24"),secondary_text:option(options,"editorial_text","#f7f3ec"),
    plan_bg:surface,protocol_bg:surface,service_bg:surface,guide_bg:surface,account_bg:surface,faq_bg:surface,contact_bg:surface,
    card_text:option(options,"editorial_text","#f7f3ec"),muted:option(options,"editorial_muted","#a8a29a"),border:option(options,"editorial_border","#30343b"),
  };
}

function orbitPalette(mode:AdvancedDesignMode,options:StoreTemplateOptionMap){
  const prefix=mode==="dark"?"orbit_dark":"orbit_light";
  const surface=option(options,`${prefix}_surface`,mode==="dark"?"#0c0f16":"#ffffff");
  return {
    primary_bg:option(options,"theme_primary","#6d5dfc"),primary_text:option(options,"orbit_button_text","#ffffff"),secondary_bg:option(options,`${prefix}_surface_alt`,mode==="dark"?"#131824":"#edf1f8"),secondary_text:option(options,`${prefix}_text`,mode==="dark"?"#f8fafc":"#10131a"),
    plan_bg:surface,protocol_bg:surface,service_bg:surface,guide_bg:surface,account_bg:surface,faq_bg:surface,contact_bg:surface,
    card_text:option(options,`${prefix}_text`,mode==="dark"?"#f8fafc":"#10131a"),muted:option(options,`${prefix}_muted`,mode==="dark"?"#9aa4b5":"#667085"),border:option(options,`${prefix}_border`,mode==="dark"?"#253043":"#d9e0ec"),
  };
}

export function advancedDesignFallbacks(templateId:AdvancedDesignTemplateId,mode:AdvancedDesignMode,options:StoreTemplateOptionMap={}):Record<string,string>{
  const palette=templateId==="editorial-grid-2027"
    ?editorialPalette(mode,options)
    :templateId==="orbit-neo-2027"
      ?orbitPalette(mode,options)
      :conversionPalette(mode,options);
  return Object.fromEntries(Object.entries(palette).map(([key,value])=>[`ui_${mode}_${key}`,value]));
}

export function advancedString(options:StoreTemplateOptionMap,key:string,fallback="native"){
  return option(options,key,fallback);
}

export function hasAdvancedValue(options:StoreTemplateOptionMap,key:string){
  const value=options[key];
  return typeof value==="string"&&value.trim().length>0;
}

export function advancedColor(options:StoreTemplateOptionMap,key:string){
  const value=options[key];
  return typeof value==="string"&&/^#[0-9a-fA-F]{6}$/.test(value)?value:"";
}
