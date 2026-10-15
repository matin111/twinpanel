"use client";

import dynamic from "next/dynamic";
import {AdminAuthGuard} from "./admin-auth-guard";

function RouteLoading(){
  return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>در حال بارگذاری...</b></div></div>;
}

const loading={loading:RouteLoading};

const TelegramManagerPage=dynamic(()=>import("./admin-control-screens").then(m=>m.TelegramManagerPage),loading);
const TelegramRuntimePage=dynamic(()=>import("./admin-parity-runtime").then(m=>m.TelegramRuntimePage),loading);
const WalletRuntimePage=dynamic(()=>import("./admin-parity-runtime").then(m=>m.WalletRuntimePage),loading);
const DiscountsRuntimePage=dynamic(()=>import("./admin-parity-runtime").then(m=>m.DiscountsRuntimePage),loading);
const ResellersRuntimePage=dynamic(()=>import("./admin-parity-runtime").then(m=>m.ResellersRuntimePage),loading);
const StoreSettingsRuntimePage=dynamic(()=>import("./admin-parity-runtime").then(m=>m.StoreSettingsRuntimePage),loading);
const BackupsFullRuntimePage=dynamic(()=>import("./backups-full-runtime").then(m=>m.BackupsFullRuntimePage),loading);
const ProvisionRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.ProvisionRuntimePage),loading);
const SmsReaderRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.SmsReaderRuntimePage),loading);
const MotherAccessRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.MotherAccessRuntimePage),loading);
const AccountDeliveryRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.AccountDeliveryRuntimePage),loading);
const SupportRuntimePage=dynamic(()=>import("./admin-ops-runtime").then(m=>m.SupportRuntimePage),loading);
const NotificationsRuntimePage=dynamic(()=>import("./admin-ops-runtime").then(m=>m.NotificationsRuntimePage),loading);
const SystemHealthRuntimePage=dynamic(()=>import("./system-health-runtime").then(m=>m.SystemHealthRuntimePage),loading);
const SubscriptionToolsRuntimePage=dynamic(()=>import("./subscription-tools-runtime").then(m=>m.SubscriptionToolsRuntimePage),loading);
const LegacySubscriptionsRuntimePage=dynamic(()=>import("./legacy-subscriptions-exact").then(m=>m.LegacySubscriptionsRuntimePage),loading);
const LegacyUsersRuntimePage=dynamic(()=>import("./legacy-users-exact").then(m=>m.LegacyUsersRuntimePage),loading);
const LegacyNodesRuntimePage=dynamic(()=>import("./legacy-nodes-exact").then(m=>m.LegacyNodesRuntimePage),loading);
const LegacyPlansRuntimePage=dynamic(()=>import("./legacy-plans-exact").then(m=>m.LegacyPlansRuntimePage),loading);
const TunnelsSimpleRuntimePage=dynamic(()=>import("./tunnels-simple-runtime").then(m=>m.TunnelsSimpleRuntimePage),loading);
const DomainsRuntimePage=dynamic(()=>import("./domains-runtime").then(m=>m.DomainsRuntimePage),loading);
const BrandingSettingsPage=dynamic(()=>import("./branding-settings").then(m=>m.BrandingSettingsPage),loading);
const L2tpSettingsPage=dynamic(()=>import("./l2tp-settings").then(m=>m.L2tpSettingsPage),loading);
const SettingsPage2027=dynamic(()=>import("./settings-2027").then(m=>m.SettingsPage2027),loading);
const LoginPage2027=dynamic(()=>import("./login-2027").then(m=>m.LoginPage2027),loading);
const RegisterPage2027=dynamic(()=>import("./login-2027").then(m=>m.RegisterPage2027),loading);
const CustomerSectionRuntime=dynamic(()=>import("./customer-runtime").then(m=>m.CustomerSectionRuntime),loading);
const CustomerConnectionModernPage=dynamic(()=>import("./customer-connection-modern").then(m=>m.CustomerConnectionModernPage),loading);
const VpnSettingsModernPage=dynamic(()=>import("./vpn-settings-modern").then(m=>m.VpnSettingsModernPage),loading);
const CustomerDashboardPro=dynamic(()=>import("./customer-dashboard-pro").then(m=>m.CustomerDashboardPro),loading);
const ResellerDashboardRuntime=dynamic(()=>import("./reseller-runtime").then(m=>m.ResellerDashboardRuntime),loading);
const ResellerSectionRuntime=dynamic(()=>import("./reseller-runtime").then(m=>m.ResellerSectionRuntime),loading);
const StoreRuntime2027=dynamic(()=>import("./store-runtime").then(m=>m.StoreRuntime2027),loading);
const AdminDashboardRuntime=dynamic(()=>import("./admin-dashboard-runtime").then(m=>m.AdminDashboardRuntime),loading);
const PaymentsReviewRuntime=dynamic(()=>import("./payments-review-runtime").then(m=>m.PaymentsReviewRuntime),loading);

const customerSections=new Set(["subscription","connection","usage","orders","wallet","payments","support","notifications","profile"]);
const resellerSections=new Set(["customers","subscriptions","sales","wallet","orders","traffic","bot","notifications","settings"]);
const admin=(node:React.ReactNode)=><AdminAuthGuard>{node}</AdminAuthGuard>;

export function RoutedPageClient({routeKey}:{routeKey:string}){
  const key=routeKey;

  if(key==="login") return <LoginPage2027/>;
  if(key==="register") return <RegisterPage2027/>;
  if(key==="admin") return admin(<AdminDashboardRuntime/>);
  if(key==="admin/users") return admin(<LegacyUsersRuntimePage/>);
  if(key==="admin/subscriptions") return admin(<LegacySubscriptionsRuntimePage/>);
  if(key==="admin/subscription-tools") return admin(<SubscriptionToolsRuntimePage/>);
  if(key==="admin/plans") return admin(<LegacyPlansRuntimePage/>);
  if(key==="admin/nodes") return admin(<LegacyNodesRuntimePage/>);
  if(key==="admin/tunnels") return admin(<TunnelsSimpleRuntimePage/>);
  if(key==="admin/tunnel-transports") return admin(<TunnelsSimpleRuntimePage/>);
  if(key==="admin/payments") return admin(<PaymentsReviewRuntime/>);
  if(key==="admin/settings") return admin(<SettingsPage2027/>);
  if(key==="admin/system-health") return admin(<SystemHealthRuntimePage/>);
  if(key==="admin/notifications") return admin(<NotificationsRuntimePage/>);
  if(key==="admin/support") return admin(<SupportRuntimePage/>);
  if(key==="admin/telegram") return admin(<TelegramRuntimePage/>);
  if(key==="admin/telegram-manager") return admin(<TelegramManagerPage/>);
  if(key==="admin/sms-reader") return admin(<SmsReaderRuntimePage/>);
  if(key==="admin/backups") return admin(<BackupsFullRuntimePage/>);
  if(key==="admin/store-settings") return admin(<StoreSettingsRuntimePage/>);
  if(key==="admin/wallet") return admin(<WalletRuntimePage/>);
  if(key==="admin/discounts") return admin(<DiscountsRuntimePage/>);
  if(key==="admin/resellers") return admin(<ResellersRuntimePage/>);
  if(key==="admin/domains") return admin(<DomainsRuntimePage/>);
  if(key==="admin/provision") return admin(<ProvisionRuntimePage/>);
  if(key==="admin/account-delivery") return admin(<AccountDeliveryRuntimePage/>);
  if(key==="admin/vpn-settings") return admin(<VpnSettingsModernPage/>);
  if(key==="admin/l2tp") return admin(<L2tpSettingsPage/>);
  if(key==="admin/mother-access") return admin(<MotherAccessRuntimePage/>);
  if(key==="admin/branding") return admin(<BrandingSettingsPage/>);
  if(key==="panel") return <CustomerDashboardPro/>;
  if(key==="panel/connection") return <CustomerConnectionModernPage/>;
  if(key==="reseller") return <ResellerDashboardRuntime/>;
  if(key==="store") return <StoreRuntime2027/>;

  if(key.startsWith("panel/")){
    const section=key.slice("panel/".length);
    if(customerSections.has(section)) return <CustomerSectionRuntime section={section}/>;
  }

  if(key.startsWith("reseller/")){
    const section=key.slice("reseller/".length);
    if(resellerSections.has(section)) return <ResellerSectionRuntime section={section}/>;
  }

  return <StoreRuntime2027/>;
}
