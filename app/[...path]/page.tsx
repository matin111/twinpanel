import {NotificationsPage,SupportPage} from "../../components/admin-screens";
import {AccountDeliveryPage,MotherAccessPage,ProvisionPage,SmsReaderPage,TelegramManagerPage,VpnSettingsPage} from "../../components/admin-control-screens";
import {TelegramRuntimePage,BackupsRuntimePage,WalletRuntimePage,DiscountsRuntimePage,ResellersRuntimePage,StoreSettingsRuntimePage} from "../../components/admin-parity-runtime";
import {DomainsRuntimePage} from "../../components/domains-runtime";
import {BrandingSettingsPage} from "../../components/branding-settings";
import {L2tpSettingsPage} from "../../components/l2tp-settings";
import {SettingsPage2027} from "../../components/settings-2027";
import {LoginPage2027,RegisterPage2027} from "../../components/login-2027";
import {CustomerSectionRuntime} from "../../components/customer-runtime";
import {CustomerDashboardPro} from "../../components/customer-dashboard-pro";
import {ResellerDashboard2027,ResellerSectionPage} from "../../components/portal-pages";
import {StorePage2027} from "../../components/store-2027";
import {AdminAuthGuard} from "../../components/admin-auth-guard";
import {AdminDashboardRuntime} from "../../components/admin-dashboard-runtime";
import {AdminUsersRuntime} from "../../components/admin-users-runtime";
import {AdminCollectionRuntime} from "../../components/admin-collections-runtime";

const customerSections=new Set(["subscription","connection","usage","orders","wallet","payments","support","notifications","profile"]);
const resellerSections=new Set(["customers","subscriptions","sales","wallet","orders","traffic","bot","notifications","settings"]);
const admin=(node:React.ReactNode)=><AdminAuthGuard>{node}</AdminAuthGuard>;

const route=(key:string)=>{
  if(key==="login") return <LoginPage2027/>;
  if(key==="register") return <RegisterPage2027/>;
  if(key==="admin") return admin(<AdminDashboardRuntime/>);
  if(key==="admin/users") return admin(<AdminUsersRuntime/>);
  if(key==="admin/subscriptions") return admin(<AdminCollectionRuntime kind="subscriptions"/>);
  if(key==="admin/plans") return admin(<AdminCollectionRuntime kind="plans"/>);
  if(key==="admin/nodes") return admin(<AdminCollectionRuntime kind="nodes"/>);
  if(key==="admin/tunnels") return admin(<AdminCollectionRuntime kind="tunnels"/>);
  if(key==="admin/payments") return admin(<AdminCollectionRuntime kind="payments"/>);
  if(key==="admin/settings") return admin(<SettingsPage2027/>);
  if(key==="admin/notifications") return admin(<NotificationsPage/>);
  if(key==="admin/support") return admin(<SupportPage/>);
  if(key==="admin/telegram") return admin(<TelegramRuntimePage/>);
  if(key==="admin/telegram-manager") return admin(<TelegramManagerPage/>);
  if(key==="admin/sms-reader") return admin(<SmsReaderPage/>);
  if(key==="admin/backups") return admin(<BackupsRuntimePage/>);
  if(key==="admin/store-settings") return admin(<StoreSettingsRuntimePage/>);
  if(key==="admin/wallet") return admin(<WalletRuntimePage/>);
  if(key==="admin/discounts") return admin(<DiscountsRuntimePage/>);
  if(key==="admin/resellers") return admin(<ResellersRuntimePage/>);
  if(key==="admin/domains") return admin(<DomainsRuntimePage/>);
  if(key==="admin/provision") return admin(<ProvisionPage/>);
  if(key==="admin/account-delivery") return admin(<AccountDeliveryPage/>);
  if(key==="admin/vpn-settings") return admin(<VpnSettingsPage/>);
  if(key==="admin/l2tp") return admin(<L2tpSettingsPage/>);
  if(key==="admin/mother-access") return admin(<MotherAccessPage/>);
  if(key==="admin/branding") return admin(<BrandingSettingsPage/>);
  if(key==="panel") return <CustomerDashboardPro/>;
  if(key==="reseller") return <ResellerDashboard2027/>;
  if(key==="store") return <StorePage2027/>;
  if(key.startsWith("panel/")){
    const section=key.slice("panel/".length);
    if(customerSections.has(section)) return <CustomerSectionRuntime section={section}/>;
  }
  if(key.startsWith("reseller/")){
    const section=key.slice("reseller/".length);
    if(resellerSections.has(section)) return <ResellerSectionPage section={section}/>;
  }
  return <StorePage2027/>;
};

export default async function Page({params}:{params:Promise<{path:string[]}>}){
  const {path}=await params;
  return route(path.join("/"));
}
