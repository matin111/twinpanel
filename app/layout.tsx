import type {Metadata} from "next";
import "./core.css";
import "./pages.css";
export const metadata:Metadata={title:"TwinPanel 2027",description:"TwinPanel VPN Control"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="fa" dir="rtl"><body>{children}</body></html>}
