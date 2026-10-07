import type {Metadata} from "next";
import {I18nProvider} from "../lib/i18n";
import {ThemeProvider} from "../lib/theme";
import {BrandingProvider} from "../lib/branding";
import {SupportChatWidget} from "../components/support-chat-widget";
import {ChatOpenBridge} from "../components/chat-open-bridge";
import {StoreMobileAccess} from "../components/store-mobile-access";
import {StoreEnhancements} from "../components/store-enhancements";
import {StorePublicNavigation} from "../components/store-public-navigation";
import {CustomerDeliveryEnhancement} from "../components/customer-delivery-enhancement";
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
import "./dashboard-2027.css";
import "./support-chat.css";
import "./support-chat-emoji.css";
import "./customer-runtime.css";
import "./customer-dashboard-pro.css";
import "./domains-runtime.css";
import "./store-mobile-access.css";
import "./readability.css";
import "./admin-runtime.css";
import "./store-enhancements.css";
import "./store-public-navigation.css";
import "./customer-delivery-enhancement.css";
import "./parity-runtime.css";

export const metadata:Metadata={title:"VPN Control 2027",description:"VPN management control panel"};

export default function RootLayout({children}:{children:React.ReactNode}){
  return <html lang="fa" dir="rtl" data-theme="dark" suppressHydrationWarning>
    <body><ThemeProvider><BrandingProvider><I18nProvider>{children}<StoreMobileAccess/><StoreEnhancements/><StorePublicNavigation/><CustomerDeliveryEnhancement/><SupportChatWidget/><ChatOpenBridge/></I18nProvider></BrandingProvider></ThemeProvider></body>
  </html>;
}
