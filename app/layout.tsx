import type {Metadata} from "next";
import {I18nProvider} from "../lib/i18n";
import {ThemeProvider} from "../lib/theme";
import {BrandingProvider} from "../lib/branding";
import {SupportChatRuntime} from "../components/support-chat-runtime";
import {SupportMenuBadgeRuntime} from "../components/support-menu-badge-runtime";
import {ChatOpenBridge} from "../components/chat-open-bridge";
import {CustomerDeliveryEnhancement} from "../components/customer-delivery-enhancement";
import {CustomerStoreRedirect} from "../components/customer-store-redirect";
import "./core.css";
import "./pages.css";
import "./i18n.css";
import "./shell.css";
import "./mobile-navigation.css";
import "./modules.css";
import "./control-plane.css";
import "./theme.css";
import "./store-2027.css";
import "./store-light.css";
import "./store-light-final.css";
import "./store-conversion-2027-v2.css";
import "./store-conversion-2027-v2-chat.css";
import "./dashboard-2027.css";
import "./support-chat.css";
import "./support-chat-emoji.css";
import "./support-center.css";
import "./support-menu-badge.css";
import "./customer-runtime.css";
import "./customer-dashboard-pro.css";
import "./customer-buy-runtime.css";
import "./customer-payments-runtime.css";
import "./customer-subscriptions-runtime.css";
import "./customer-notification-center.css";
import "./download-assets-runtime.css";
import "./domains-runtime.css";
import "./readability.css";
import "./admin-runtime.css";
import "./admin-telegram-legacy.css";
import "./admin-telegram-broadcast.css";
import "./customer-delivery-enhancement.css";
import "./parity-runtime.css";
import "./subscriptions-full-runtime.css";
import "./legacy-parity-batch1.css";
import "./subscription-link-modal.css";
import "./admin-payments-runtime.css";
import "./reseller-parity.css";
import "./reseller-parity-v2.css";
import "./reseller-subscriptions-compact.css";
import "./admin-resellers-v2.css";
import "./admin-resellers-volume-v2.css";
import "./store-admin.css";
import "./store-real-guides-v4.css";
import "./customer-shell-final.css";
import "./admin-shell-final.css";
import "./storefront-polish-v5.css";
import "./storefront-mobile-hero-v6.css";
import "./storefront-mobile-hero-v8.css";
import "./storefront-protocol-art-v9.css";

export const metadata:Metadata={title:"VPN Control 2027",description:"VPN management control panel"};

export default function RootLayout({children}:{children:React.ReactNode}){
  return <html lang="fa" dir="rtl" data-theme="dark" suppressHydrationWarning>
    <body><ThemeProvider><BrandingProvider><I18nProvider>{children}<CustomerStoreRedirect/><CustomerDeliveryEnhancement/><SupportMenuBadgeRuntime/><SupportChatRuntime/><ChatOpenBridge/></I18nProvider></BrandingProvider></ThemeProvider></body>
  </html>;
}
