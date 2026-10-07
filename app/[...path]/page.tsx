import {AdminDashboard,AdminListPage,NotificationsPage,SupportPage} from "../../components/admin-screens";
import {BackupsPage,DiscountsPage,ResellersAdminPage,StoreSettingsPage,TelegramPage,WalletPage} from "../../components/admin-extra-screens";
import {AccountDeliveryPage,BrandingPage,DomainsPage,MotherAccessPage,ProvisionPage,SmsReaderPage,TelegramManagerPage,VpnSettingsPage} from "../../components/admin-control-screens";
import {SettingsPage2027} from "../../components/settings-2027";
import {LoginPage2027} from "../../components/login-2027";
import {CustomerDashboard2027,CustomerSectionPage,ResellerDashboard2027,ResellerSectionPage} from "../../components/portal-pages";
import {StorePage2027} from "../../components/store-2027";

const customerSections=new Set(["subscription","connection","usage","wallet","payments","support","notifications","profile"]);
const resellerSections=new Set(["customers","subscriptions","sales","wallet","orders","traffic","bot","notifications","settings"]);

const route=(key:string)=>{
  if(key==="login") return <LoginPage2027/>;
  if(key==="admin") return <AdminDashboard/>;
  if(key==="admin/settings") return <SettingsPage2027/>;
  if(key==="admin/notifications") return <NotificationsPage/>;
  if(key==="admin/support") return <SupportPage/>;
  if(key==="admin/telegram") return <TelegramPage/>;
  if(key==="admin/telegram-manager") return <TelegramManagerPage/>;
  if(key==="admin/sms-reader") return <SmsReaderPage/>;
  if(key==="admin/backups") return <BackupsPage/>;
  if(key==="admin/store-settings") return <StoreSettingsPage/>;
  if(key==="admin/wallet") return <WalletPage/>;
  if(key==="admin/discounts") return <DiscountsPage/>;
  if(key==="admin/resellers") return <ResellersAdminPage/>;
  if(key==="admin/domains") return <DomainsPage/>;
  if(key==="admin/provision") return <ProvisionPage/>;
  if(key==="admin/account-delivery") return <AccountDeliveryPage/>;
  if(key==="admin/vpn-settings") return <VpnSettingsPage/>;
  if(key==="admin/mother-access") return <MotherAccessPage/>;
  if(key==="admin/branding") return <BrandingPage/>;
  if(key==="panel") return <CustomerDashboard2027/>;
  if(key==="reseller") return <ResellerDashboard2027/>;
  if(key==="store") return <StorePage2027/>;

  if(key.startsWith("panel/")){
    const section=key.slice("panel/".length);
    if(customerSections.has(section)) return <CustomerSectionPage section={section}/>;
  }
  if(key.startsWith("reseller/")){
    const section=key.slice("reseller/".length);
    if(resellerSections.has(section)) return <ResellerSectionPage section={section}/>;
  }

  const map:Record<string,string>={
    "admin/users":"user",
    "admin/subscriptions":"subscription",
    "admin/plans":"plan",
    "admin/nodes":"node",
    "admin/tunnels":"tunnel",
    "admin/payments":"payment"
  };

  const kind=map[key];
  return kind?<AdminListPage kind={kind}/>:<StorePage2027/>;
};

export default async function Page({params}:{params:Promise<{path:string[]}>}){
  const {path}=await params;
  return route(path.join("/"));
}
