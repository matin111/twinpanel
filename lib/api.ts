const configuredApiBase=(process.env.NEXT_PUBLIC_API_BASE||"").trim().replace(/\/+$/,"");

// Public prebuilt releases are intentionally compiled without a customer-
// specific API URL. In the browser, an empty or loopback API base must resolve
// to the current TwinPanel origin so requests use the built-in /v1 proxy.
// This keeps one portable artifact working on IP installs and custom domains.
const isLoopbackApiBase=/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?$/i.test(configuredApiBase);
const browserOrigin=typeof window!=="undefined"?window.location.origin:"";

export const API_BASE=(!configuredApiBase||isLoopbackApiBase)
  ?browserOrigin
  :configuredApiBase;

export const api={
  health:"/health",

  auth:{
    login:"/v1/auth/login",
    register:"/v1/auth/register",
    me:"/v1/auth/me",
    email:"/v1/auth/me/email",
    changePassword:"/v1/auth/change-password",
    twoFactor:{
      status:"/v1/auth/2fa/status",
      setup:"/v1/auth/2fa/setup",
      enable:"/v1/auth/2fa/enable",
      disable:"/v1/auth/2fa/disable",
      verifyLogin:"/v1/auth/2fa/login/verify"
    }
  },

  admin:{
    stats:"/v1/admin/stats",
    dashboard:"/v1/admin/dashboard-summary",
    users:"/v1/admin/users",
    usersPage:"/v1/admin/users-page",
    systemHealth:"/v1/admin/system-health",
    securityOverview:"/v1/admin/security/overview",
    coreProtocols:"/v1/admin/core-protocols",
    backups:"/v1/admin/backups",
    telegramBot:"/v1/admin/telegram-bot",
    domains:"/v1/admin/domains",
    resellers:"/v1/admin/resellers",
    wallet:"/v1/admin/wallet",
    support:"/v1/admin/support/tickets",
    panelNotifications:"/v1/admin/panel-notifications"
  },

  plans:"/v1/plans",
  subscriptions:"/v1/subscriptions",
  nodes:"/v1/nodes",
  tunnels:"/v1/tunnels",
  provision:"/v1/provision",
  quotaHealth:"/v1/quota/health",

  payments:{
    methods:"/v1/payments/methods",
    intents:"/v1/payments/intents",
    mine:"/v1/payments/intents/me",
    adminIntents:"/v1/payments/admin/intents",
    adminSettings:"/v1/payments/admin/settings",
    smsRelay:"/v1/payments/sms-relay",
    smsReaderAdmin:"/v1/payments/admin/sms-reader",
    smsReaderPairCode:"/v1/payments/admin/sms-reader/pair-code",
    smsReaderPair:"/v1/payments/sms-reader/pair",
    smsReaderConfig:"/v1/payments/sms-reader/config",
    smsReaderHeartbeat:"/v1/payments/sms-reader/heartbeat",
    smsReaderEvents:"/v1/payments/sms-reader/events"
  },

  wallet:{
    me:"/v1/wallet/me",
    methods:"/v1/wallet/methods",
    transactions:"/v1/wallet/transactions",
    topups:"/v1/wallet/topups",
    myTopups:"/v1/wallet/topups/me",
    adminWallets:"/v1/admin/wallet/wallets",
    adminTopups:"/v1/admin/wallet/topups"
  },

  store:{
    orders:"/v1/store/orders",
    myOrders:"/v1/store/orders/me",
    adminOrders:"/v1/store/orders/admin",
    settings:"/v1/storefront/settings"
  },

  discounts:{
    admin:"/v1/discounts/admin",
    reseller:"/v1/discounts/reseller",
    validate:"/v1/discounts/store/validate"
  },

  reseller:{
    me:"/v1/reseller/me",
    dashboard:"/v1/reseller/dashboard",
    customers:"/v1/reseller/customers",
    subscriptions:"/v1/reseller/subscriptions",
    plans:"/v1/reseller/plans",
    walletTransactions:"/v1/reseller/wallet/transactions",
    traffic:"/v1/reseller/traffic",
    trafficPackages:"/v1/reseller/traffic/packages",
    trafficTransactions:"/v1/reseller/traffic/transactions",
    serverOptions:"/v1/reseller/server-options",
    bot:"/v1/reseller/bot",
    botCommerce:"/v1/reseller/bot-commerce",
    notifications:"/v1/reseller/notifications"
  },

  support:{
    categories:"/v1/support/categories",
    tickets:"/v1/support/tickets",
    mine:"/v1/support/tickets/me",
    admin:"/v1/admin/support/tickets"
  },

  notifications:"/v1/notifications",
  telegramLinks:"/v1/telegram",

  settings:{
    branding:"/v1/settings/branding",
    general:"/v1/settings/general",
    notifications:"/v1/settings/notifications",
    vpn:"/v1/settings/vpn",
    l2tp:"/v1/settings/vpn/l2tp"
  },

  motherAccess:"/v1/mother-access",
  accountDelivery:"/v1/subscriptions",
  publicConnect:"/v1/connect",
  customerSubscriptions:"/v1/customer/subscriptions"
} as const;

// Compatibility aliases used by early UI modules. Keep until every screen is wired.
export const legacyApi={
  health:api.health,
  login:api.auth.login,
  me:api.auth.me,
  users:api.admin.users,
  stats:api.admin.stats,
  dashboard:api.admin.dashboard,
  plans:api.plans,
  subscriptions:api.subscriptions,
  nodes:api.nodes,
  tunnels:api.tunnels,
  provision:api.provision,
  quota:api.quotaHealth,
  payments:api.payments.adminIntents,
  support:api.support.admin,
  notifications:api.admin.panelNotifications,
  store:api.store.orders,
  wallet:api.wallet.me,
  reseller:api.reseller.dashboard,
  branding:api.settings.branding
} as const;

export const endpoint={
  adminUser:(id:number|string)=>`${api.admin.users}/${id}`,
  adminUserToggle:(id:number|string)=>`${api.admin.users}/${id}/toggle-active`,
  adminUserResetPassword:(id:number|string)=>`${api.admin.users}/${id}/reset-password`,
  node:(id:number|string)=>`${api.nodes}/${id}`,
  nodeHealth:(id:number|string)=>`${api.nodes}/${id}/health`,
  nodeProtocols:(id:number|string)=>`${api.nodes}/${id}/protocols`,
  tunnel:(id:number|string)=>`${api.tunnels}/${id}`,
  tunnelHealth:(id:number|string)=>`${api.tunnels}/${id}/health`,
  subscription:(id:number|string)=>`${api.subscriptions}/${id}`,
  subscriptionConnectionInfo:(id:number|string)=>`${api.accountDelivery}/${id}/connection-info`,
  customerConnectionInfo:(id:number|string)=>`${api.customerSubscriptions}/${id}/connection-info`,
  domain:(id:number|string)=>`${api.admin.domains}/${id}`,
  domainSsl:(id:number|string)=>`${api.admin.domains}/${id}/ssl`,
  reseller:(id:number|string)=>`${api.admin.resellers}/${id}`,
  resellerToggle:(id:number|string)=>`${api.admin.resellers}/${id}/toggle-active`,
  paymentIntent:(id:number|string)=>`${api.payments.intents}/${id}`,
  paymentApprove:(id:number|string)=>`${api.payments.adminIntents}/${id}/approve`,
  paymentReject:(id:number|string)=>`${api.payments.adminIntents}/${id}/reject`,
  backupInfo:(filename:string)=>`${api.admin.backups}/${encodeURIComponent(filename)}/info`,
  backupRestore:(filename:string)=>`${api.admin.backups}/${encodeURIComponent(filename)}/restore`,
  publicUsage:(token:string)=>`${api.publicConnect}/${encodeURIComponent(token)}/usage`,
  publicQr:(token:string)=>`${api.publicConnect}/${encodeURIComponent(token)}/qr`
} as const;

export async function apiFetch<T>(path:string,init?:RequestInit):Promise<T>{
  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers:{"Content-Type":"application/json",...(init?.headers||{})},
    cache:"no-store"
  });
  if(!response.ok){
    let detail="";
    try{detail=JSON.stringify(await response.json());}catch{}
    throw new Error(`TwinPanel API ${response.status}${detail?`: ${detail}`:""}`);
  }
  if(response.status===204) return undefined as T;
  return response.json() as Promise<T>;
}
