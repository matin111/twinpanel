"use client";

import React from "react";
import {CustomerDashboardPro} from "./customer-dashboard-pro";

type State={failed:boolean;message:string};

class CustomerPanelBoundary extends React.Component<{children:React.ReactNode},State>{
  state:State={failed:false,message:""};

  static getDerivedStateFromError(error:unknown):State{
    return {failed:true,message:error instanceof Error?error.message:String(error||"خطای ناشناخته")};
  }

  componentDidCatch(error:unknown){
    console.error("[TwinPanel customer portal] render failure",error);
  }

  private retry=()=>{
    this.setState({failed:false,message:""});
    window.location.reload();
  };

  render(){
    if(!this.state.failed)return this.props.children;
    return <main className="auth-gate" dir="rtl">
      <section className="auth-gate-card">
        <b>پنل کاربری کامل بارگذاری نشد</b>
        <small>یک خطای رابط کاربری رخ داد؛ نشست شما حذف نشده است.</small>
        {this.state.message&&<code dir="ltr" style={{maxWidth:"100%",overflowWrap:"anywhere"}}>{this.state.message}</code>}
        <button type="button" className="primary" onClick={this.retry}>بارگذاری مجدد</button>
      </section>
    </main>;
  }
}

export function CustomerPanelEntry(){
  return <CustomerPanelBoundary><CustomerDashboardPro/></CustomerPanelBoundary>;
}
