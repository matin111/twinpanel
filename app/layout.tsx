import type {Metadata} from "next";
import {I18nProvider} from "../lib/i18n";
import "./core.css";
import "./pages.css";
import "./i18n.css";
import "./shell.css";

export const metadata:Metadata={
  title:"TwinPanel 2027",
  description:"TwinPanel VPN Control"
};

export default function RootLayout({children}:{children:React.ReactNode}){
  return <html lang="fa" dir="rtl" suppressHydrationWarning>
    <body><I18nProvider>{children}</I18nProvider></body>
  </html>;
}
