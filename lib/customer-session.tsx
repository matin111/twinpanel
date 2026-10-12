"use client";

import {createContext,useCallback,useContext,useEffect,useMemo,useState} from "react";
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

  const load=useCallback(async()=>{
    const current=getCustomerToken();
    if(!current){
      window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }

    setError("");

    // /auth/me is the single source of truth for an already authenticated
    // customer portal session. Portal role resolution belongs to the login
    // flow; probing /reseller/me again here can create a /panel <-> /reseller
    // navigation loop when the auxiliary reseller probe is stale or transient.
    let account:CustomerUser;
    try{
      account=await customerApi.me(current);
    }catch(reason){
      clearCustomerToken();
      setToken(null);
      setUser(null);
      setReady(false);
      setError(reason instanceof Error?reason.message:"نشست کاربری معتبر نیست");
      window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }

    if(account.role==="admin"){
      window.location.replace("/admin");
      return;
    }

    if(!account.is_active){
      clearCustomerToken();
      setToken(null);
      setUser(null);
      setReady(false);
      window.location.replace("/login");
      return;
    }

    setToken(current);
    setUser(account);
    setReady(true);
  },[]);

  useEffect(()=>{void load();},[load]);

  const logout=()=>{
    clearCustomerToken();
    setToken(null);
    setUser(null);
    setReady(false);
    window.location.replace("/login");
  };

  const value=useMemo<SessionValue>(
    ()=>({ready,token,user,error,logout,refresh:load}),
    [ready,token,user,error,load]
  );

  if(!ready)return <div className="customer-session-loading"><span className="customer-loader"/><b>در حال دریافت حساب...</b></div>;
  return <CustomerSessionContext.Provider value={value}>{children}</CustomerSessionContext.Provider>;
}

export function useCustomerSession(){
  const value=useContext(CustomerSessionContext);
  if(!value)throw new Error("useCustomerSession must be used inside CustomerSessionProvider");
  return value;
}
