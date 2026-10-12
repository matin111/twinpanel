import {TelegramManagerPage,VpnSettingsPage} from "../../components/admin-control-screens";
import {TelegramRuntimePage,WalletRuntimePage,DiscountsRuntimePage,ResellersRuntimePage,StoreSettingsRuntimePage} from "../../components/admin-parity-runtime";
import {BackupsFullRuntimePage} from "../../components/backups-full-runtime";
import {ProvisionRuntimePage,SmsReaderRuntimePage,MotherAccessRuntimePage,AccountDeliveryRuntimePage} from "../../components/admin-infra-runtime";
import {SupportRuntimePage,NotificationsRuntimePage} from "../../components/admin-ops-runtime";
import {SystemHealthRuntimePage} from "../../components/system-health-runtime";
import {TunnelTransportRuntimePage} from "../../components/tunnel-transport-runtime";
import {SubscriptionToolsRuntimePage} from "../../components/subscription-tools-runtime";
import {LegacySubscriptionsRuntimePage} from "../../components/legacy-subscriptions-exact";
import {LegacyUsersRuntimePage} from "../../components/legacy-users-exact";
import {LegacyNodesRuntimePage} from "../../components/legacy-nodes-exact";
import {LegacyPlansRuntimePage} from "../../components/legacy-plans-exact";
import {LegacyTunnelsExactPage} from "../../components/legacy-tunnels-exact";
import {DomainsRuntimePage} from "../../components/domains-runtime";
import {BrandingSettingsPage} from "../../components/branding-settings";
import {L2tpSettingsPage} from "../../components/l2tp-settings";
import {SettingsPage2027} from "../../components/settings-2027";
import {LoginPage2027,RegisterPage2027} from "../../components/login-2027";
import {CustomerSectionRuntime} from "../../components/customer-runtime";
import {CustomerPanelEntry} from "../../components/customer-panel-entry";
import {CustomerBuyRuntime} from "../../components/customer-buy-runtime";
import {CustomerPaymentsRuntime} from "../../components/customer-payments-runtime";
import {CustomerSubscriptionsRuntime} from "../../components/customer-subscriptions-runtime";
import {DownloadAssetsRuntime} from "../../components/download-assets-runtime";
import {ResellerDashboardRuntime,ResellerSectionRuntime} from "../../components/reseller-runtime";
import {StoreRuntime2027} from "../../components/store-runtime";
import {AdminAuthGuard} from "../../components/admin-auth-guard";
import {AdminDashboardRuntime} from "../../components/admin-dashboard-runtime";
import {AdminCollectionRuntime} from "../../components/admin-collections-runtime";
import {AdminPaymentsRuntime} from "../../components/admin-payments-runtime";

const customerSections=new Set(["orders","wallet","notifications","profile"]);
const resellerSections=new Set(["customers","subscriptions","sales","wallet","orders","traffic","bot","notifications","settings"]);
const admin=(node:React.ReactNode)=><AdminAuthGuard>{node}</AdminAuthGuard>;

const route=(key:string)=>{
  if(key==="login") return <LoginPage2027/>;
  if(key==="register") return <RegisterPage2027/>;
  if(key==="admin") return admin(<AdminDashboardRuntime/>);
  if(key==="admin/users") return admin(<LegacyUsersRuntimePage/>);
  if(key==="admin/subscriptions") return admin(<LegacySubscriptionsRuntimePage/>);
  if(key==="admin/subscription-tools") return admin(<SubscriptionToolsRuntimePage/>);
  if(key==="admin/plans") return admin(<LegacyPlansRuntimePage/>);
  if(key==="admin/nodes") return admin(<LegacyNodesRuntimePage/>);
  if(key==="admin/tunnels") return admin(<LegacyTunnelsExactPage/>);
  if(key==="admin/tunnel-transports") return admin(<TunnelTransportRuntimePage/>);
  if(key==="admin/payments") return admin(<AdminPaymentsRuntime/>);
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
  if(key==="admin/downloads") return admin(<DownloadAssetsRuntime/>);
  if(key==="admin/vpn-settings") return admin(<VpnSettingsPage/>);
  if(key==="admin/l2tp") return admin(<L2tpSettingsPage/>);
  if(key==="admin/mother-access") return admin(<MotherAccessRuntimePage/>);
  if(key==="admin/branding") return admin(<BrandingSettingsPage/>);
  if(key==="panel") return <CustomerPanelEntry/>;
  if(key==="panel/buy") return <CustomerBuyRuntime/>;
  if(key==="panel/subscription") return <CustomerSubscriptionsRuntime/>;
  if(key==="panel/connection") return <CustomerSubscriptionsRuntime/>;
  if(key==="panel/usage"||key==="panel/support") return <CustomerPanelEntry/>;
  if(key==="panel/payments") return <CustomerPaymentsRuntime/>;
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
};

export default async function Page({params}:{params:Promise<{path:string[]}>}){
  const {path}=await params;
  return route(path.join("/"));
}
