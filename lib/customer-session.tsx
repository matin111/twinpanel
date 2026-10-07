"use client";

import {createContext,useContext,useEffect,useMemo,useState} from "react";
import {clearCustomerToken,customerApi,CustomerUser,getCustomerToken} from "./customer-api";

type SessionValue={
  ready:boolean;
  token:string|null;
  user:CustomerUser|null;
  error:string;
  logout:()=>void;
  refresh:()=>Promise<void>;
};

const CustomerSessionContext=createContext<SessionValue|null>(null);

export function CustomerSessionProvider({children}:{children:React.ReactNode}){
  const [ready,setReady]=useState(false);
  const [token,setToken]=useState<string|null>(null);
  const [user,setUser]=useState<CustomerUser|null>(null);
  const [error,setError]=useState("");

  const load=async()=>{
    const current=getCustomerToken();
    if(!current){window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);return;}
    setToken(current);setError("");
    try{
      const account=await customerApi.me(current);
      if(account.role==="admin"){window.location.replace("/admin");return;}
      if(!account.is_active)throw new Error("حساب کاربری غیرفعال است");
      setUser(account);setReady(true);
    }catch(reason){
      clearCustomerToken();setToken(null);setUser(null);
      setError(reason instanceof Error?reason.message:"نشست کاربری معتبر نیست");
      window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  };

  useEffect(()=>{void load();},[]);

  const logout=()=>{clearCustomerToken();window.location.replace("/login");};
  const value=useMemo<SessionValue>(()=>({ready,token,user,error,logout,refresh:load}),[ready,token,user,error]);

  if(!ready)return <div className="customer-session-loading"><span className="customer-loader"/><b>در حال دریافت حساب...</b></div>;
  return <CustomerSessionContext.Provider value={value}>{children}</CustomerSessionContext.Provider>;
}

export function useCustomerSession(){
  const value=useContext(CustomerSessionContext);
  if(!value)throw new Error("useCustomerSession must be used inside CustomerSessionProvider");
  return value;
}
