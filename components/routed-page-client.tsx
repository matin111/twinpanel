"use client";

import dynamic from "next/dynamic";
import {AdminAuthGuard} from "./admin-auth-guard";
import {AdminOperationFeedback} from "./admin-operation-feedback";
import {AdminManualSubscriptionCreate} from "./admin-manual-subscription-create";
import {Card,Shell} from "./ui";

const TelegramManagerPage=dynamic(()=>import("./admin-control-screens").then(m=>m.TelegramManagerPage));
const AdminTelegramLegacyPage=dynamic(()=>import("./admin-telegram-legacy-parity").then(m=>m.AdminTelegramLegacyPage));
const WalletRuntimePage=dynamic(()=>import("./admin-parity-runtime").then(m=>m.WalletRuntimePage));
const DiscountsRuntimePage=dynamic(()=>import("./admin-parity-runtime").then(m=>m.DiscountsRuntimePage));
const AdminResellersManagementRuntime=dynamic(()=>import("./admin-resellers-management-runtime").then(m=>m.AdminResellersManagementRuntime));
const AdminResellerTrafficPlans=dynamic(()=>import("./admin-reseller-traffic-plans").then(m=>m.AdminResellerTrafficPlans));
const StoreSettingsManager=dynamic(()=>import("./store-settings-manager").then(m=>m.StoreSettingsManager));
const BackupsFullRuntimePage=dynamic(()=>import("./backups-full-runtime").then(m=>m.BackupsFullRuntimePage));
const ProvisionRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.ProvisionRuntimePage));
const SmsReaderRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.SmsReaderRuntimePage));
const AdminSmsRelayDownload=dynamic(()=>import("./admin-sms-relay-download").then(m=>m.AdminSmsRelayDownload));
const MotherAccessRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.MotherAccessRuntimePage));
const AccountDeliveryRuntimePage=dynamic(()=>import("./admin-infra-runtime").then(m=>m.AccountDeliveryRuntimePage));
const SupportRuntimePage=dynamic(()=>import("./admin-ops-runtime").then(m=>m.SupportRuntimePage));
const NotificationsRuntimePage=dynamic(()=>import("./admin-ops-runtime").then(m=>m.NotificationsRuntimePage));
const SystemHealthRuntimePage=dynamic(()=>import("./system-health-runtime").then(m=>m.SystemHealthRuntimePage));
const SubscriptionToolsRuntimePage=dynamic(()=>import("./subscription-tools-runtime").then(m=>m.SubscriptionToolsRuntimePage));
const LegacySubscriptionsRuntimePage=dynamic(()=>import("./legacy-subscriptions-exact").then(m=>m.LegacySubscriptionsRuntimePage));
const AdminUsersRuntime=dynamic(()=>import("./admin-users-runtime").then(m=>m.AdminUsersRuntime));
const LegacyNodesRuntimePage=dynamic(()=>import("./legacy-nodes-exact").then(m=>m.LegacyNodesRuntimePage));
const LegacyPlansRuntimePage=dynamic(()=>import("./legacy-plans-exact").then(m=>m.LegacyPlansRuntimePage));
const TunnelsSimpleRuntimePage=dynamic(()=>import("./tunnels-simple-runtime").then(m=>m.TunnelsSimpleRuntimePage));
const SmartTransportsRuntimeV25=dynamic(()=>import("./smart-transports-runtime-v25").then(m=>m.SmartTransportsRuntimeV25));
const DomainsRuntimePage=dynamic(()=>import("./domains-runtime").then(m=>m.DomainsRuntimePage));
const BrandingSettingsPage=dynamic(()=>import("./branding-settings").then(m=>m.BrandingSettingsPage));
const L2tpSettingsPage=dynamic(()=>import("./l2tp-settings").then(m=>m.L2tpSettingsPage));
const SettingsPage2027=dynamic(()=>import("./settings-2027").then(m=>m.SettingsPage2027));
const LoginPage2027=dynamic(()=>import("./login-2027").then(m=>m.LoginPage2027));
const RegisterPage2027=dynamic(()=>import("./login-2027").then(m=>m.RegisterPage2027));
const CustomerSectionRuntime=dynamic(()=>import("./customer-runtime").then(m=>m.CustomerSectionRuntime));
const CustomerConnectionModernPage=dynamic(()=>import("./customer-connection-modern").then(m=>m.CustomerConnectionModernPage));
const VpnSettingsModernPage=dynamic(()=>import("./vpn-settings-modern").then(m=>m.VpnSettingsModernPage));
const CustomerDashboardPro=dynamic(()=>import("./customer-dashboard-pro").then(m=>m.CustomerDashboardPro));
const ResellerDashboardRuntime=dynamic(()=>import("./reseller-runtime").then(m=>m.ResellerDashboardRuntime));
const ResellerSectionRuntime=dynamic(()=>import("./reseller-runtime").then(m=>m.ResellerSectionRuntime));
const StoreRuntime2027=dynamic(()=>import("./store-runtime").then(m=>m.StoreRuntime2027));
const AdminDashboardRuntime=dynamic(()=>import("./admin-dashboard-runtime").then(m=>m.AdminDashboardRuntime));
const PaymentsReviewRuntime=dynamic(()=>import("./payments-review-runtime").then(m=>m.PaymentsReviewRuntime));
const AdminPaymentsRuntime=dynamic(()=>import("./admin-payments-runtime").then(m=>m.AdminPaymentsRuntime));
const DownloadAssetsRuntime=dynamic(()=>import("./download-assets-runtime").then(m=>m.DownloadAssetsRuntime));

const customerSections=new Set(["subscription","connection","usage","orders","wallet","payments","support","notifications","profile"]);
const resellerSections=new Set(["customers","subscriptions","sales","wallet","orders","traffic","bot","notifications","settings"]);
const admin=(node:React.ReactNode)=><AdminAuthGuard><AdminOperationFeedback/>{node}</AdminAuthGuard>;

function AdminUnknownRoute(){
  return (
    <Shell active="">
      <div className="page">
        <div className="page-head">
          <div><h1>صفحه پیدا نشد</h1></div>
        </div>
        <Card><b>این مسیر در پنل مدیریت وجود ندارد.</b></Card>
      </div>
    </Shell>
  );
}

export function RoutedPageClient({routeKey}:{routeKey:string}){
  const key=routeKey;

  if(key==="login") return <LoginPage2027/>;
  if(key==="register") return <RegisterPage2027/>;
  if(key==="admin") return admin(<AdminDashboardRuntime/>);
  if(key==="admin/users") return admin(<AdminUsersRuntime/>);
  if(key==="admin/subscriptions") return admin(<><AdminManualSubscriptionCreate/><LegacySubscriptionsRuntimePage/></>);
  if(key==="admin/subscription-tools") return admin(<SubscriptionToolsRuntimePage/>);
  if(key==="admin/plans") return admin(<LegacyPlansRuntimePage/>);
  if(key==="admin/nodes") return admin(<LegacyNodesRuntimePage/>);
  if(key==="admin/network") return admin(<LegacyNodesRuntimePage/>);
  if(key==="admin/tunnels") return admin(<TunnelsSimpleRuntimePage/>);
  if(key==="admin/tunnel-transports") return admin(<SmartTransportsRuntimeV25/>);
  if(key==="admin/payments") return admin(<PaymentsReviewRuntime/>);
  if(key==="admin/payment-settings") return admin(<AdminPaymentsRuntime/>);
  if(key==="admin/settings") return admin(<SettingsPage2027/>);
  if(key==="admin/system-health") return admin(<SystemHealthRuntimePage/>);
  if(key==="admin/notifications") return admin(<NotificationsRuntimePage/>);
  if(key==="admin/support") return admin(<SupportRuntimePage/>);
  if(key==="admin/telegram") return admin(<AdminTelegramLegacyPage/>);
  if(key==="admin/telegram-manager") return admin(<TelegramManagerPage/>);
  if(key==="admin/sms-reader") return admin(<><SmsReaderRuntimePage/><AdminSmsRelayDownload/></>);
  if(key==="admin/backups") return admin(<BackupsFullRuntimePage/>);
  if(key==="admin/store-settings") return admin(<StoreSettingsManager/>);
  if(key==="admin/wallet") return admin(<WalletRuntimePage/>);
  if(key==="admin/discounts") return admin(<DiscountsRuntimePage/>);
  if(key==="admin/resellers") return admin(<AdminResellersManagementRuntime/>);
  if(key==="admin/reseller-traffic-plans") return admin(<AdminResellerTrafficPlans/>);
  if(key==="admin/domains") return admin(<DomainsRuntimePage/>);
  if(key==="admin/provision") return admin(<ProvisionRuntimePage/>);
  if(key==="admin/account-delivery") return admin(<AccountDeliveryRuntimePage/>);
  if(key==="admin/downloads") return admin(<DownloadAssetsRuntime/>);
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

  if(key.startsWith("admin/")) return admin(<AdminUnknownRoute/>);
  return <StoreRuntime2027/>;
}
