"use client";

import {OrbitTemplateCustomizer} from "./store-template-orbit-customizer";
import {OrbitModernProtocolDescriptionControl} from "./store-template-orbit-modern-protocol-control";
import styles from "./store-template-orbit-customizer-polish.module.css";

export function OrbitTemplateCustomizerPolished({onClose}:{onClose:()=>void}){
  return <div className={styles.polish}>
    <OrbitModernProtocolDescriptionControl/>
    <OrbitTemplateCustomizer onClose={onClose}/>
  </div>;
}
