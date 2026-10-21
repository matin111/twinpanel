"use client";

import type {StoreTemplateOptionMap} from "../lib/store-template-options";
import {OrbitNeo2027Template} from "./store-template-orbit-neo";
import type {StoreTemplateProps} from "./store-template-renderer";
import styles from "./store-template-orbit-polish.module.css";

type Props=StoreTemplateProps&{themeOptions:StoreTemplateOptionMap};

export function OrbitNeoPolishedTemplate(props:Props){
  const guideImage=props.themeOptions.orbit_guides_image;
  const hasCustomGuide=typeof guideImage==="string"&&guideImage.trim().length>0;
  return <div className={styles.polish} data-guide-custom={hasCustomGuide?"true":"false"}>
    <OrbitNeo2027Template {...props}/>
  </div>;
}
