"use client";

import type {CSSProperties} from "react";
import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {StoreTemplateRenderer,type StoreTemplateProps} from "./store-template-renderer";
import bridge from "./store-template-conversion-theme-bridge.module.css";
import composition from "./store-template-conversion-composition.module.css";

type Props=StoreTemplateProps&{themeOptions:StoreTemplateOptionMap};

function stringOption(options:StoreTemplateOptionMap,key:string,fallback:string){
  const value=options[key];
  return typeof value==="string"&&value.trim()?value:fallback;
}

function booleanOption(options:StoreTemplateOptionMap,key:string,fallback:boolean){
  return typeof options[key]==="boolean"?Boolean(options[key]):fallback;
}

export function ConversionPro2027Template({themeOptions,...props}:Props){
  const style={
    "--conversion-theme-accent":stringOption(themeOptions,"conversion_accent","#8b5cf6"),
    "--conversion-theme-accent-2":stringOption(themeOptions,"conversion_accent_2","#6d28d9"),
    "--conversion-theme-page":stringOption(themeOptions,"conversion_page_bg","#060915"),
    "--conversion-theme-section":stringOption(themeOptions,"conversion_section_bg","#0b1020"),
    "--conversion-theme-card":stringOption(themeOptions,"conversion_card_bg","#0f1526"),
    "--conversion-theme-border":stringOption(themeOptions,"conversion_card_border","#202b42"),
    "--conversion-theme-header":stringOption(themeOptions,"conversion_header_bg","#080c18"),
    "--conversion-theme-header-text":stringOption(themeOptions,"conversion_header_text","#f7f8ff"),
    "--conversion-theme-button":stringOption(themeOptions,"conversion_button_bg","#7c3aed"),
    "--conversion-theme-button-text":stringOption(themeOptions,"conversion_button_text","#ffffff"),
    "--conversion-theme-text":stringOption(themeOptions,"conversion_text","#f7f8ff"),
    "--conversion-theme-muted":stringOption(themeOptions,"conversion_muted","#9aa7bf"),
  } as CSSProperties;

  return <div
    className={`${bridge.themeBridge} ${composition.composition} tpConversionThemeRuntime`}
    data-density={stringOption(themeOptions,"conversion_density","balanced")}
    data-header={stringOption(themeOptions,"conversion_header_style","glass")}
    data-buttons={stringOption(themeOptions,"conversion_button_style","gradient")}
    data-cards={stringOption(themeOptions,"conversion_card_style","glass")}
    data-corners={stringOption(themeOptions,"conversion_corner_style","soft")}
    data-glow={stringOption(themeOptions,"conversion_glow","soft")}
    data-hero-visual={booleanOption(themeOptions,"conversion_show_hero_visual",true)?"on":"off"}
    style={style}
  ><StoreTemplateRenderer {...props}/></div>;
}
