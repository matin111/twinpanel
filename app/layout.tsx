import type {Metadata} from "next";
import {I18nProvider} from "../lib/i18n";
import {ThemeProvider} from "../lib/theme";
import {BrandingProvider} from "../lib/branding";
import "./core.css";
import "./pages.css";
import "./i18n.css";
import "./shell.css";
import "./modules.css";
import "./control-plane.css";
import "./theme.css";
import "./store-2027.css";
import "./dashboard-2027.css";

export const metadata:Metadata={
  title:"VPN Control 2027",
  description:"VPN management control panel"
};

export default function RootLayout({children}:{children:React.ReactNode}){
  return <html lang="fa" dir="rtl" data-theme="dark" suppressHydrationWarning>
    <body><ThemeProvider><BrandingProvider><I18nProvider>{children}</I18nProvider></BrandingProvider></ThemeProvider></body>
  </html>;
}
