import {AdminDashboard,AdminListPage,NotificationsPage,SettingsPage,SupportPage} from "../../components/admin-screens";
import {BackupsPage,DiscountsPage,ResellersAdminPage,StoreSettingsPage,TelegramPage,WalletPage} from "../../components/admin-extra-screens";
import {AccountDeliveryPage,BrandingPage,DomainsPage,MotherAccessPage,ProvisionPage,SmsReaderPage,TelegramManagerPage,VpnSettingsPage} from "../../components/admin-control-screens";
import {LoginPage,PanelPage,ResellerPage,StorePage} from "../../components/public-screens";

const route=(key:string)=>{
  if(key==="login") return <LoginPage/>;
  if(key==="admin") return <AdminDashboard/>;
  if(key==="admin/settings") return <SettingsPage/>;
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
  if(key==="panel") return <PanelPage/>;
  if(key==="reseller") return <ResellerPage/>;
  if(key==="store") return <StorePage/>;

  const map:Record<string,string>={
    "admin/users":"user",
    "admin/subscriptions":"subscription",
    "admin/plans":"plan",
    "admin/nodes":"node",
    "admin/tunnels":"tunnel",
    "admin/payments":"payment"
  };

  const kind=map[key];
  return kind?<AdminListPage kind={kind}/>:<StorePage/>;
};

export default async function Page({params}:{params:Promise<{path:string[]}>}){
  const {path}=await params;
  return route(path.join("/"));
}
