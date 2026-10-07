"use client";

import Link from "next/link";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";

export function LoginPage2027(){
  const {pick}=useI18n();
  return <div className="login login2027">
    <section className="login-art"><div className="brand big"><img src="/logo.svg" alt="TwinPanel"/><div><b>TwinPanel</b><small>SECURE CONTROL 2027</small></div></div><div className="planet"><span>T</span></div><h2>{pick("اتصال امن به دنیای بدون محدودیت","Secure access to a connected world")}</h2><p>{pick("مدیریت یکپارچه، سریع و قابل اعتماد","Unified, fast and reliable management")}</p></section>
    <section className="login-form"><div className="login-tools"><LanguageSwitch/><ThemeSwitch/></div><form><span className="eyebrow">TWINPANEL 2027</span><h1>{pick("به پنل خوش آمدید","Welcome to TwinPanel")}</h1><p>{pick("برای ادامه وارد حساب کاربری خود شوید.","Sign in to your account to continue.")}</p><label>{pick("ایمیل یا نام کاربری","Email or username")}<input placeholder="user@example.com"/></label><label>{pick("رمز عبور","Password")}<input type="password" placeholder="••••••••"/></label><div className="remember"><span><input type="checkbox"/> {pick("مرا به خاطر بسپار","Remember me")}</span><a>{pick("فراموشی رمز؟","Forgot password?")}</a></div><button className="primary full">{pick("ورود به پنل","Sign in")}</button><div className="sep">{pick("یا","or")}</div><div className="social"><button>Google</button><button>Telegram</button></div><small className="signup">{pick("حساب ندارید؟","No account?")} <Link href="/store">{pick("خرید سرویس","Buy service")}</Link></small></form></section>
  </div>;
}
