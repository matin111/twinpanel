"use client";

import {createContext,useCallback,useContext,useEffect,useMemo,useState} from "react";
import {clearCustomerToken,customerApi,CustomerUser,getCustomerToken} from "./customer-api";
import {readPortalAccess} from "./access-cache";

type SessionValue={
  ready:boolean;
  token:string|null;
  user:CustomerUser|null;
  error:string;
  logout:()=>void;
  refresh:()=>Promise<void>;
};

type CachedSession={token:string;user:CustomerUser}|null;

const CustomerSessionContext=createContext<SessionValue|null>(null);

function cachedSession():CachedSession{
  const token=getCustomerToken();
  if(!token)return null;
  const cached=readPortalAccess(token);
  const user=cached?.user;
  if(cached?.portal!=="customer"||!user||!user.is_active||String(user.role||"").toLowerCase()==="admin")return null;
  return {token,user};
}

export function CustomerSessionProvider({children}:{children:React.ReactNode}){
  const initial=cachedSession();
  const [ready,setReady]=useState(Boolean(initial));
  const [token,setToken]=useState<string|null>(initial?.token??null);
  const [user,setUser]=useState<CustomerUser|null>(initial?.user??null);
  const [error,setError]=useState("");

  const load=useCallback(async()=>{
    const current=getCustomerToken();
    if(!current){
      window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }

    setError("");

    // /auth/me remains the source of truth, but a short-lived verified cache
    // lets route-to-route navigation render immediately while this request
    // revalidates the account in the background.
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
