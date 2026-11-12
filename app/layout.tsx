import type {Metadata} from "next";
import {I18nProvider} from "../lib/i18n";
import {ThemeProvider} from "../lib/theme";
import {BrandingProvider,DEFAULT_BRANDING,type BrandingConfig} from "../lib/branding";
import {unstable_cache} from "next/cache";
import {readFile} from "node:fs/promises";
import {SupportChatRuntime} from "../components/support-chat-runtime";
import {ChatOpenBridge} from "../components/chat-open-bridge";
import {CustomerDeliveryEnhancement} from "../components/customer-delivery-enhancement";
import {CustomerStoreRedirect} from "../components/customer-store-redirect";
import {PortalTopNavBehavior} from "../components/portal-topnav-behavior";
import {RuntimeVersionConvergence} from "../components/runtime-version-convergence";
import {SystemUpdateRecoveryBootstrap} from "../components/system-update-recovery-bootstrap";
import {AdminLogoutControl} from "../components/admin-logout-control";
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
import "./store-conversion-2027-pro.css";
import "./dashboard-2027.css";
import "./support-chat.css";
import "./support-chat-emoji.css";
import "./store-template-support.css";
import "./support-center.css";
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
import "./node-observability-v1.css";
import "./admin-telegram-legacy.css";
import "./admin-telegram-broadcast.css";
import "./customer-delivery-enhancement.css";
import "./parity-runtime.css";
import "./subscriptions-full-runtime.css";
import "./legacy-parity-batch1.css";
import "./admin-payments-runtime.css";
import "./reseller-parity.css";
import "./reseller-parity-v2.css";
import "./reseller-subscriptions-compact.css";
import "./admin-resellers-v2.css";
import "./admin-resellers-volume-v2.css";
import "./store-admin.css";
import "./store-real-guides-v4.css";
import "./customer-shell-final.css";
import "./portal-topnav-2027.css";
import "./admin-shell-final.css";
import "./admin-modal-layer-final.css";
import "./admin-nav-attention.css";
import "./system-release.css";
import "./system-release-theme.css";
import "./system-release-dialog-v76.css";
import "./storefront-polish-v5.css";
import "./storefront-mobile-hero-v6.css";
import "./storefront-mobile-hero-v8.css";
import "./storefront-protocol-art-v9.css";
import "./panel-copy-density-final.css";
import "./subscription-link-modal.css";
import "./subscription-link-modal-v96.css";
import "./branding-runtime.css";
import "./branding-admin.css";
import "./login-professional.css";
import "./tunnel-transports-2027.css";
import "./admin-overlay-fixes.css";
import "./store-orbit-public-cleanup.css";
import "./admin-notification-readability.css";
import "./trial-settings.css";
import "./subscription-light-actions.css";

// The public login/register pages must start with the saved brand before client
// hydration. Fetch via the local backend (no user credential required), rather
// than temporarily showing the hard-coded legacy TwinPanel identity.
const loadPublicBrand=unstable_cache(async():Promise<BrandingConfig|null>=>{
  // Persisted by the branding API after every save/asset change. Do not
  // depend on a busy FastAPI worker before drawing the public sign-in page.
  let row:Record<string,unknown>|null=null;
  try{
    const file=process.env.TWINPANEL_PUBLIC_BRANDING_FILE||"/var/lib/twinpanel/branding/public-branding.json";
    row=JSON.parse(await readFile(file,"utf8")) as Record<string,unknown>;
  }catch{/* First boot: fall back to the public branding endpoint. */}
  const backend=(process.env.TWINPANEL_BACKEND_URL||"http://127.0.0.1:8095").replace(/\/+$/,"");
  try{
    if(!row){
      const response=await fetch(`${backend}/v1/settings/branding`,{
        signal:AbortSignal.timeout(2500),cache:"no-store"
      });
      if(!response.ok)return null;
      row=await response.json() as Record<string,unknown>;
    }
    const hex=(value:unknown,fallback:string)=>{
      const text=String(value||"").trim();
      return /^#[0-9a-fA-F]{6}$/.test(text)?text.toUpperCase():fallback;
    };
    const name=String(row.brand_name||row.site_title||"").trim()||DEFAULT_BRANDING.name;
    const parts=name.split(/\s+/).filter(Boolean);
    const shortName=parts.length>1?parts.slice(0,2).map(x=>x[0]).join("").toUpperCase():name.slice(0,2).toUpperCase();
    return {
      name,shortName,
      tagline:String(row.site_description||"").trim(),
      logoUrl:String(row.logo_url||DEFAULT_BRANDING.logoUrl),
      faviconUrl:String(row.favicon_url||DEFAULT_BRANDING.faviconUrl),
      supportLink:String(row.telegram_url||DEFAULT_BRANDING.supportLink),
      accent:hex(row.primary_color,DEFAULT_BRANDING.accent),
      secondaryColor:hex(row.secondary_color,DEFAULT_BRANDING.secondaryColor)
    };
  }catch{return null;}
},["twinpanel-public-branding-initial-v1"],{revalidate:30});

export async function generateMetadata():Promise<Metadata>{
  const brand=await loadPublicBrand();
  return {
    title:brand?.name||"VPN Control",
    description:brand?.tagline||"VPN management portal",
    icons:brand?.faviconUrl?{icon:brand.faviconUrl}:undefined
  };
}

export default async function RootLayout({children}:{children:React.ReactNode}){
  const initialBrand=(await loadPublicBrand())||undefined;
  return <html lang="fa" dir="rtl" data-theme="dark" suppressHydrationWarning>
    <body><SystemUpdateRecoveryBootstrap/><ThemeProvider><BrandingProvider initialBrand={initialBrand}><I18nProvider>{children}<AdminLogoutControl/><RuntimeVersionConvergence/><PortalTopNavBehavior/><CustomerStoreRedirect/><CustomerDeliveryEnhancement/><SupportChatRuntime/><ChatOpenBridge/></I18nProvider></BrandingProvider></ThemeProvider></body>
  </html>;
}