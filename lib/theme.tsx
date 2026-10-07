"use client";

import {createContext,useContext,useEffect,useMemo,useState} from "react";

type ThemeMode="dark"|"light"|"system";
type ThemeContextValue={mode:ThemeMode;resolved:"dark"|"light";setMode:(mode:ThemeMode)=>void;cycle:()=>void};

const ThemeContext=createContext<ThemeContextValue|null>(null);
const STORAGE_KEY="twinpanel.theme";

function getSystemTheme():"dark"|"light"{
  if(typeof window==="undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";
}

export function ThemeProvider({children}:{children:React.ReactNode}){
  const [mode,setModeState]=useState<ThemeMode>("dark");
  const [systemTheme,setSystemTheme]=useState<"dark"|"light">("dark");

  useEffect(()=>{
    const media=window.matchMedia("(prefers-color-scheme: light)");
    const sync=()=>setSystemTheme(media.matches?"light":"dark");
    sync();
    const saved=localStorage.getItem(STORAGE_KEY) as ThemeMode|null;
    if(saved==="dark"||saved==="light"||saved==="system") setModeState(saved);
    media.addEventListener("change",sync);
    return ()=>media.removeEventListener("change",sync);
  },[]);

  const resolved=mode==="system"?systemTheme:mode;

  useEffect(()=>{
    document.documentElement.dataset.theme=resolved;
    document.documentElement.style.colorScheme=resolved;
  },[resolved]);

  const setMode=(next:ThemeMode)=>{
    setModeState(next);
    try{localStorage.setItem(STORAGE_KEY,next);}catch{}
  };

  const value=useMemo<ThemeContextValue>(()=>({
    mode,
    resolved,
    setMode,
    cycle:()=>setMode(mode==="dark"?"light":mode==="light"?"system":"dark")
  }),[mode,resolved]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(){
  const value=useContext(ThemeContext);
  if(!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}

export function ThemeSwitch({compact=false}:{compact?:boolean}){
  const {mode,resolved,setMode}=useTheme();
  return <div className={`theme-switch ${compact?"compact":""}`} role="group" aria-label="Theme">
    <button type="button" className={mode==="dark"?"active":""} onClick={()=>setMode("dark")} title="Dark">☾</button>
    <button type="button" className={mode==="light"?"active":""} onClick={()=>setMode("light")} title="Light">☀</button>
    <button type="button" className={mode==="system"?"active":""} onClick={()=>setMode("system")} title={`System (${resolved})`}>◐</button>
  </div>;
}
