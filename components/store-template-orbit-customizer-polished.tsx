"use client";

import {OrbitTemplateCustomizer} from "./store-template-orbit-customizer";
import styles from "./store-template-orbit-customizer-polish.module.css";

export function OrbitTemplateCustomizerPolished({onClose}:{onClose:()=>void}){
  return <div className={styles.polish}><OrbitTemplateCustomizer onClose={onClose}/></div>;
}
