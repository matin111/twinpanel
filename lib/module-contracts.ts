export const moduleContracts={
  telegram:["telegram_bot","telegram_manager","reseller_bot"],
  backups:["backups","backup_service","backup_worker"],
  store:["store","storefront_settings"],
  wallet:["customer_wallet","reseller_wallet"],
  discounts:["discounts","discount_service"],
  resellers:["resellers","reseller_portal","reseller_bot_orders"]
} as const;
