"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";
import {getCustomerToken} from "../lib/customer-api";

export function CustomerStoreRedirect(){
  const pathname=usePathname();

  useEffect(()=>{
    if(pathname!=="/store")return;
    if(!getCustomerToken())return;
    window.location.replace("/panel/buy");
  },[pathname]);

  return null;
}
