import {TelegramManagerPage,VpnSettingsPage} from "../../components/admin-control-screens";
import {TelegramRuntimePage,DiscountsRuntimePage,StoreSettingsRuntimePage} from "../../components/admin-parity-runtime";
import {AdminResellersLegacyV3} from "../../components/admin-resellers-legacy-v3";
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
import {CustomerWalletV2} from "../../components/customer-wallet-v2";
import {CustomerPanelEntry} from "../../components/customer-panel-entry";
import {CustomerBuyRuntime} from "../../components/customer-buy-runtime";
import {CustomerPaymentsRuntime} from "../../components/customer-payments-runtime";
import {CustomerSubscriptionsRuntime} from "../../components/customer-subscriptions-runtime";
import {DownloadAssetsRuntime} from "../../components/download-assets-runtime";
import {
  ResellerDashboardParityV2,
  ResellerCustomersParityV2,
  ResellerSalesParityV2,
  ResellerTrafficParityV2,
  ResellerNotificationsParityV2,
  ResellerSettingsParityV2,
} from "../../components/reseller-portal-parity-v2";
import {ResellerBotParityRuntime,ResellerOrdersParityRuntime,ResellerDiscountsParityRuntime} from "../../components/reseller-commerce-parity";
import {ResellerSubscriptionsParityRuntime} from "../../components/reseller-subscriptions-parity";
import {StoreRuntime2027} from "../../components/store-runtime";
import {AdminAuthGuard} from "../../components/admin-auth-guard";
import {AdminDashboardRuntime} from "../../components/admin-dashboard-runtime";
import {AdminPaymentsRuntime} from "../../components/admin-payments-runtime";
import {AdminPaymentMarketRates} from "../../components/admin-payment-market-rates";
import {AdminCryptoDiscountControl} from "../../components/admin-crypto-discount-control";
import {AdminSmsRelayDownload} from "../../components/admin-sms-relay-download";
import {AdminUsersWalletInline} from "../../components/admin-users-wallet-inline";
import {AdminPaymentsWalletTopups} from "../../components/admin-payments-wallet-topups";

const customerSections=new Set(["orders","notifications","profile"]);
const admin=(node:React.ReactNode)=><AdminAuthGuard>{node}</AdminAuthGuard>;
const usersWithWallet=()=>admin(<><LegacyUsersRuntimePage/><AdminUsersWalletInline/></>);

const route=(key:string)=>{
  if(key==="login") return <LoginPage2027/>;
  if(key==="register") return <RegisterPage2027/>;
  if(key==="admin") return admin(<AdminDashboardRuntime/>);
  if(key==="admin/users") return usersWithWallet();
  if(key==="admin/subscriptions") return admin(<LegacySubscriptionsRuntimePage/>);
  if(key==="admin/subscription-tools") return admin(<SubscriptionToolsRuntimePage/>);
  if(key==="admin/plans") return admin(<LegacyPlansRuntimePage/>);
  if(key==="admin/nodes") return admin(<LegacyNodesRuntimePage/>);
  if(key==="admin/tunnels") return admin(<LegacyTunnelsExactPage/>);
  if(key==="admin/tunnel-transports") return admin(<TunnelTransportRuntimePage/>);
  if(key==="admin/payments") return admin(<><AdminPaymentsRuntime/><AdminPaymentsWalletTopups/><AdminPaymentMarketRates/><AdminCryptoDiscountControl/></>);
  if(key==="admin/settings") return admin(<SettingsPage2027/>);
  if(key==="admin/system-health") return admin(<SystemHealthRuntimePage/>);
  if(key==="admin/notifications") return admin(<NotificationsRuntimePage/>);
  if(key==="admin/support") return admin(<SupportRuntimePage/>);
  if(key==="admin/telegram") return admin(<TelegramRuntimePage/>);
  if(key==="admin/telegram-manager") return admin(<TelegramManagerPage/>);
  if(key==="admin/sms-reader") return admin(<><SmsReaderRuntimePage/><AdminSmsRelayDownload/></>);
  if(key==="admin/backups") return admin(<BackupsFullRuntimePage/>);
  if(key==="admin/store-settings") return admin(<StoreSettingsRuntimePage/>);
  if(key==="admin/wallet") return usersWithWallet();
  if(key==="admin/discounts") return admin(<DiscountsRuntimePage/>);
  if(key==="admin/resellers") return admin(<AdminResellersLegacyV3/>);
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
  if(key==="panel/wallet") return <CustomerWalletV2/>;

  if(key==="reseller") return <ResellerDashboardParityV2/>;
  if(key==="reseller/customers") return <ResellerCustomersParityV2/>;
  if(key==="reseller/subscriptions") return <ResellerSubscriptionsParityRuntime/>;
  if(key==="reseller/sales") return <ResellerSalesParityV2/>;
  if(key==="reseller/traffic"||key==="reseller/wallet") return <ResellerTrafficParityV2/>;
  if(key==="reseller/orders") return <ResellerOrdersParityRuntime/>;
  if(key==="reseller/discounts") return <ResellerDiscountsParityRuntime/>;
  if(key==="reseller/bot") return <ResellerBotParityRuntime/>;
  if(key==="reseller/notifications") return <ResellerNotificationsParityV2/>;
  if(key==="reseller/settings") return <ResellerSettingsParityV2/>;

  if(key==="store") return <StoreRuntime2027/>;
  if(key.startsWith("panel/")){
    const section=key.slice("panel/".length);
    if(customerSections.has(section)) return <CustomerSectionRuntime section={section}/>;
  }
  return <StoreRuntime2027/>;
};

export default async function Page({params}:{params:Promise<{path:string[]}>}){
  const {path}=await params;
  return route(path.join("/"));
}
