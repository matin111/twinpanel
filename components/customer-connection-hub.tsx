"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";
import {QRCodeSVG} from "qrcode.react";

import {PageHead} from "./ui";
import {PortalShell} from "./portal-shells";
import {API_BASE} from "../lib/api";
import {
  customerApi,
  getCustomerToken,
  type CustomerConnectionInfo,
  type MySubscription,
} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import styles from "./customer-connection-hub.module.css";


type XrayProfile = {
  id?: string;
  title?: string;
  recommended?: boolean;
  security?: string;
  transport?: string;
  server?: string;
  port?: number;
  uri?: string;
  sni?: string | null;
  qr?: string;
};


type CredentialItem = Record<string, unknown> & {
  node_id?: number;
  node?: string;
  server?: string;
  server_ip?: string;
  port?: number;
  uri?: string;
  profiles?: XrayProfile[];
};


type XrayCard = {
  node: string;
  profile: XrayProfile;
};


type ModernEnsureResponse = {
  ok?: boolean;
  skipped?: boolean;
  reason?: string;
  migrated_node_ids?: number[];
  errors?: Array<Record<string, unknown>>;
  connection?: CustomerConnectionInfo;
};


type Platform = "android" | "ios" | "windows" | "macos" | "other";


const protocolName = (value: string) => ({
  cisco: "Cisco / OpenConnect",
  openconnect: "Cisco / OpenConnect",
  openvpn: "OpenVPN",
  wireguard: "WireGuard",
  l2tp: "L2TP / IPsec",
  v2ray: "V2Ray / Xray",
  xray: "V2Ray / Xray",
} as Record<string, string>)[value.toLowerCase()] || value;


const statusFa = (status: string) => ({
  active: "فعال",
  pending: "در انتظار",
  suspended: "تعلیق",
  expired: "منقضی",
  canceled: "لغو شده",
} as Record<string, string>)[status] || status || "—";


function normalizeItems(value: unknown): CredentialItem[] {
  if (Array.isArray(value)) {
    return value.filter(
      item => Boolean(item) && typeof item === "object",
    ) as CredentialItem[];
  }

  if (value && typeof value === "object") {
    return [value as CredentialItem];
  }

  return [];
}


function profileLabel(
  profile: XrayProfile,
  pick: (fa: string, en: string) => string,
) {
  const id = String(profile.id || "").toLowerCase();

  if (id === "websocket_tls") {
    return pick("وب‌سوکت + TLS", "WebSocket + TLS");
  }
  if (id === "xhttp_reality") {
    return "XHTTP + REALITY";
  }
  if (id === "httpupgrade_tls") {
    return "HTTP Upgrade + TLS";
  }
  if (id === "grpc_reality") {
    return "gRPC + REALITY";
  }
  if (id === "legacy") {
    return pick("اتصال قدیمی Xray", "Legacy Xray connection");
  }

  return profile.title || id || pick("اتصال Xray", "Xray connection");
}


function securityLabel(profile: XrayProfile) {
  const security = String(profile.security || "").toLowerCase();
  if (security === "reality") return "REALITY";
  if (security === "tls") return "TLS";
  return security || "—";
}


function detectPlatform(): Platform {
  if (typeof navigator === "undefined") return "other";

  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("android")) return "android";
  if (/iphone|ipad|ipod/.test(ua)) return "ios";
  if (ua.includes("windows")) return "windows";
  if (ua.includes("macintosh") || ua.includes("mac os")) return "macos";
  return "other";
}


function platformLabel(
  platform: Platform,
  pick: (fa: string, en: string) => string,
) {
  if (platform === "android") return "Android";
  if (platform === "ios") return "iPhone / iPad";
  if (platform === "windows") return "Windows";
  if (platform === "macos") return "macOS";
  return pick("دستگاه شما", "your device");
}


function serializedCredential(value: unknown) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  }
  catch {
    return String(value ?? "");
  }
}


function usableUri(profile: XrayProfile | undefined) {
  return String(profile?.uri || "").trim();
}


export function CustomerConnectionHubPage() {
  const {pick} = useI18n();

  const [subscriptions, setSubscriptions] = useState<MySubscription[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [info, setInfo] = useState<CustomerConnectionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionLoading, setConnectionLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [qrValue, setQrValue] = useState("");
  const [platform, setPlatform] = useState<Platform>("other");


  useEffect(() => {
    setPlatform(detectPlatform());
  }, []);


  useEffect(() => {
    const token = getCustomerToken();

    if (!token) {
      setLoading(false);
      setError("AUTH_REQUIRED");
      return;
    }

    customerApi
      .subscriptions(token)
      .then(rows => {
        setSubscriptions(rows);
        const preferred = rows.find(row => row.status === "active") || rows[0];
        setSelected(preferred?.id || null);
      })
      .catch(reason => {
        setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => setLoading(false));
  }, []);


  useEffect(() => {
    if (!selected) {
      setInfo(null);
      return;
    }

    const token = getCustomerToken();
    if (!token) return;

    let alive = true;

    const load = async () => {
      setConnectionLoading(true);
      setError("");
      setNotice("");
      setQrValue("");

      try {
        const response = await fetch(
          `${API_BASE}/v1/xray-modern/customer/${selected}/ensure`,
          {
            method: "POST",
            headers: {Authorization: `Bearer ${token}`},
            cache: "no-store",
          },
        );

        if (!response.ok) {
          const fallback = await customerApi.connectionInfo(token, selected);
          if (alive) {
            setInfo(fallback);
            setNotice(
              pick(
                "اطلاعات فعلی اتصال نمایش داده شد؛ آماده‌سازی خودکار Xray در این لحظه کامل نشد.",
                "Current credentials are shown; automatic Xray preparation did not complete at this moment.",
              ),
            );
          }
          return;
        }

        const payload = await response.json() as ModernEnsureResponse;
        const connection = payload.connection
          || await customerApi.connectionInfo(token, selected);

        if (alive) {
          setInfo(connection);
          if (Array.isArray(payload.migrated_node_ids) && payload.migrated_node_ids.length) {
            setNotice(
              pick(
                "اتصال‌های امن جدید Xray برای این اشتراک آماده شدند.",
                "New secure Xray connections are ready for this subscription.",
              ),
            );
          }
        }
      }
      catch (reason) {
        try {
          const fallback = await customerApi.connectionInfo(token, selected);
          if (alive) {
            setInfo(fallback);
            setNotice(
              pick(
                "اطلاعات اتصال فعلی نمایش داده شد.",
                "Current connection information is displayed.",
              ),
            );
          }
        }
        catch {
          if (alive) {
            setError(reason instanceof Error ? reason.message : String(reason));
          }
        }
      }
      finally {
        if (alive) setConnectionLoading(false);
      }
    };

    void load();
    return () => {
      alive = false;
    };
  }, [selected, pick]);


  const selectedSubscription = useMemo(
    () => subscriptions.find(row => row.id === selected) || null,
    [subscriptions, selected],
  );


  const xrayCards = useMemo(() => {
    if (!info) return [] as XrayCard[];

    const output: XrayCard[] = [];

    for (const credential of info.credentials) {
      if (String(credential.protocol).toLowerCase() !== "v2ray") continue;

      for (const item of normalizeItems(credential.items)) {
        const node = String(
          item.node
          || item.server
          || item.server_ip
          || pick("سرور Xray", "Xray server"),
        );

        if (Array.isArray(item.profiles)) {
          for (const profile of item.profiles) {
            if (profile && profile.uri) output.push({node, profile});
          }
        }
        else if (item.uri) {
          output.push({
            node,
            profile: {
              id: "legacy",
              title: pick("اتصال قدیمی", "Legacy connection"),
              recommended: false,
              security: "legacy",
              transport: "legacy",
              server: item.server,
              port: item.port,
              uri: String(item.uri),
            },
          });
        }
      }
    }

    return output.sort((a, b) => {
      const aScore = a.profile.recommended ? 1 : 0;
      const bScore = b.profile.recommended ? 1 : 0;
      return bScore - aScore;
    });
  }, [info, pick]);


  const otherCredentials = useMemo(
    () => info?.credentials.filter(
      row => !["v2ray", "xray"].includes(String(row.protocol).toLowerCase()),
    ) || [],
    [info],
  );


  const smartCard = useMemo(
    () => (
      xrayCards.find(row => row.profile.recommended && row.profile.id !== "legacy")
      || xrayCards.find(row => row.profile.id !== "legacy")
      || xrayCards[0]
      || null
    ),
    [xrayCards],
  );


  const copy = async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(""), 1500);
    }
    catch {
      setNotice(
        pick(
          "کپی خودکار انجام نشد؛ متن را دستی انتخاب کنید.",
          "Automatic copy failed; select the text manually.",
        ),
      );
    }
  };


  const openConnection = (uri: string) => {
    if (!uri) return;
    window.location.href = uri;
  };


  const modernRoadmap = [
    {
      key: "hysteria2",
      name: "Hysteria2",
      transport: "UDP / QUIC",
      note: pick("مناسب شبکه‌های پرنوسان و موبایل", "Designed for variable and mobile networks"),
    },
    {
      key: "tuic",
      name: "TUIC v5",
      transport: "UDP / QUIC",
      note: pick("اتصال مدرن با تأخیر پایین", "Modern low-latency transport"),
    },
    {
      key: "anytls",
      name: "AnyTLS",
      transport: "TCP / TLS",
      note: pick("گزینه TLS برای شبکه‌های محدودتر", "TLS option for more restricted networks"),
    },
  ];


  return (
    <PortalShell type="customer" active="/panel/connection">
      <div className={`page customer-runtime ${styles.hub}`}>
        <PageHead title={pick("اتصال", "Connection")} />

        <div className={styles.intro}>
          <div>
            <span className={styles.eyebrow}>{pick("مرکز اتصال", "Connection Hub")}</span>
            <h2>{pick("ساده برای شروع، کامل برای حرفه‌ای‌ها", "Simple to start, complete for advanced users")}</h2>
            <p>
              {pick(
                "بهترین اتصال آماده را مستقیم استفاده کنید؛ جزئیات فنی و همه پروتکل‌ها فقط وقتی لازم باشد نمایش داده می‌شوند.",
                "Use the best ready connection directly; technical details and the full protocol list stay out of the way until you need them.",
              )}
            </p>
          </div>
          <div className={styles.platformPill}>
            <span>{pick("دستگاه", "Device")}</span>
            <b>{platformLabel(platform, pick)}</b>
          </div>
        </div>

        {loading && (
          <div className={styles.stateBox}>
            <span className="customer-loader" />
            {pick("در حال دریافت اشتراک‌ها...", "Loading subscriptions...")}
          </div>
        )}

        {error && <div className={styles.warning}>{error}</div>}
        {notice && <div className={styles.notice}>{notice}</div>}

        {!loading && subscriptions.length > 0 && (
          <section className={styles.subscriptionStrip} aria-label={pick("انتخاب اشتراک", "Select subscription")}>
            <div className={styles.sectionTitleCompact}>
              <span>{pick("اشتراک فعال", "Subscription")}</span>
              <small>{pick("اتصال‌ها بر اساس اشتراک انتخاب‌شده نمایش داده می‌شوند", "Connections follow the selected subscription")}</small>
            </div>
            <div className={styles.subscriptionList}>
              {subscriptions.map(subscription => (
                <button
                  key={subscription.id}
                  type="button"
                  className={selected === subscription.id ? styles.subscriptionActive : styles.subscriptionButton}
                  onClick={() => setSelected(subscription.id)}
                >
                  <span>{subscription.plan_name || `#${subscription.id}`}</span>
                  <small>{statusFa(subscription.status)}</small>
                </button>
              ))}
            </div>
          </section>
        )}

        {connectionLoading && (
          <div className={styles.stateBox}>
            <span className="customer-loader" />
            {pick("در حال آماده‌سازی امن‌ترین اتصال‌های موجود...", "Preparing the available secure connections...")}
          </div>
        )}

        {info && !connectionLoading && (
          <>
            <section className={styles.smartSection}>
              <div className={styles.smartCopy}>
                <div className={styles.sectionKicker}>
                  <span className={styles.spark}>✦</span>
                  {pick("اتصال هوشمند", "Smart Connect")}
                </div>

                {smartCard ? (
                  <>
                    <h2>{pick("اتصال پیشنهادی برای شروع", "Recommended connection to start")}</h2>
                    <p>
                      {pick(
                        "این گزینه از بین پروفایل‌های آماده و سالم حساب شما انتخاب شده است. اگر روی شبکه شما مناسب نبود، گزینه‌های سریع پایین را امتحان کنید.",
                        "This option is selected from the ready profiles on your account. If it is not ideal on your network, try a quick alternative below.",
                      )}
                    </p>

                    <div className={styles.smartMeta}>
                      <span>{profileLabel(smartCard.profile, pick)}</span>
                      <span>{smartCard.node}</span>
                      <span>{securityLabel(smartCard.profile)}</span>
                    </div>

                    <div className={styles.primaryActions}>
                      <button
                        type="button"
                        className={styles.primaryButton}
                        onClick={() => openConnection(usableUri(smartCard.profile))}
                      >
                        <span>⚡</span>
                        {pick("اتصال سریع", "Quick connect")}
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        onClick={() => void copy("smart", usableUri(smartCard.profile))}
                      >
                        {copied === "smart" ? "✓" : "⧉"}
                        {copied === "smart" ? pick("کپی شد", "Copied") : pick("کپی لینک", "Copy link")}
                      </button>
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        onClick={() => setQrValue(current => current === usableUri(smartCard.profile) ? "" : usableUri(smartCard.profile))}
                      >
                        ▦ {pick("QR", "QR")}
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <h2>{pick("اتصال هوشمند هنوز آماده نیست", "Smart Connect is not ready yet")}</h2>
                    <p>
                      {pick(
                        "برای این اشتراک پروفایل Xray قابل استفاده پیدا نشد. اطلاعات پروتکل‌های کلاسیک در بخش اتصال سریع و تنظیمات حرفه‌ای حفظ شده‌اند.",
                        "No usable Xray profile was found for this subscription. Classic protocol credentials remain available below.",
                      )}
                    </p>
                  </>
                )}
              </div>

              <div className={styles.smartSide}>
                {qrValue ? (
                  <div className={styles.qrPanel}>
                    <div className={styles.qrCanvas}>
                      <QRCodeSVG value={qrValue} size={166} level="M" />
                    </div>
                    <b>{pick("اسکن برای ورود کانفیگ", "Scan to import config")}</b>
                    <small>{pick("QR فقط برای اتصال انتخاب‌شده است", "QR belongs to the selected connection")}</small>
                  </div>
                ) : (
                  <div className={styles.healthPanel}>
                    <div className={styles.healthIcon}>✓</div>
                    <b>{pick("پروفایل واقعی حساب", "Real account profile")}</b>
                    <p>{pick("بدون ساخت کانفیگ نمایشی یا دکمه جعلی", "No placeholder configs or fake actions")}</p>
                    {selectedSubscription && (
                      <div className={styles.subscriptionFacts}>
                        <span>
                          <small>{pick("حجم باقی‌مانده", "Traffic left")}</small>
                          <b>{Math.max(Number(selectedSubscription.traffic_remaining_gb || 0), 0).toFixed(2)} GB</b>
                        </span>
                        <span>
                          <small>{pick("روز باقی‌مانده", "Days left")}</small>
                          <b>{Math.max(Number(selectedSubscription.days_remaining || 0), 0)}</b>
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>

            <section className={styles.quickSection}>
              <div className={styles.sectionHeading}>
                <div>
                  <span className={styles.sectionKicker}>{pick("اتصال سریع", "Quick Connect")}</span>
                  <h2>{pick("جایگزین‌های آماده", "Ready alternatives")}</h2>
                  <p>{pick("فقط اتصال‌هایی که همین حالا اطلاعات واقعی دارند نمایش داده می‌شوند.", "Only connections with real, currently available credentials are shown.")}</p>
                </div>
              </div>

              <div className={styles.quickGrid}>
                {xrayCards.slice(0, 4).map(({node, profile}, index) => {
                  const key = `quick-${node}-${profile.id || index}-${index}`;
                  const uri = usableUri(profile);
                  return (
                    <article className={styles.quickCard} key={key}>
                      <div className={styles.protocolIcon}>X</div>
                      <div className={styles.quickBody}>
                        <div className={styles.quickTitleRow}>
                          <b>{profileLabel(profile, pick)}</b>
                          <span className={profile.recommended ? styles.readyBadge : styles.altBadge}>
                            {profile.recommended ? pick("پیشنهادی", "Recommended") : pick("جایگزین", "Alternative")}
                          </span>
                        </div>
                        <small>{node} · {securityLabel(profile)}</small>
                        <div className={styles.quickActions}>
                          <button type="button" onClick={() => openConnection(uri)}>{pick("باز کردن", "Open")}</button>
                          <button type="button" onClick={() => void copy(key, uri)}>{copied === key ? "✓" : "⧉"}</button>
                          <button type="button" onClick={() => setQrValue(current => current === uri ? "" : uri)}>▦</button>
                        </div>
                      </div>
                    </article>
                  );
                })}

                {otherCredentials.map((row, index) => {
                  const value = serializedCredential(row.items);
                  const key = `classic-${row.protocol}-${index}`;
                  return (
                    <article className={styles.quickCard} key={key}>
                      <div className={styles.protocolIcon}>{protocolName(row.protocol).slice(0, 1)}</div>
                      <div className={styles.quickBody}>
                        <div className={styles.quickTitleRow}>
                          <b>{protocolName(row.protocol)}</b>
                          <span className={styles.readyBadge}>{pick("آماده", "Ready")}</span>
                        </div>
                        <small>{row.username || info.account?.username || pick("اطلاعات حساب موجود است", "Account credentials available")}</small>
                        <div className={styles.quickActions}>
                          {value && (
                            <button type="button" onClick={() => void copy(key, value)}>
                              {copied === key ? pick("کپی شد", "Copied") : pick("کپی تنظیمات", "Copy config")}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}

                {xrayCards.length === 0 && otherCredentials.length === 0 && (
                  <div className={styles.emptyCard}>
                    {pick("برای این اشتراک هنوز اطلاعات اتصال قابل استفاده ثبت نشده است.", "No usable connection credentials are registered for this subscription yet.")}
                  </div>
                )}
              </div>
            </section>

            <section className={styles.advancedSection}>
              <button
                type="button"
                className={styles.advancedToggle}
                onClick={() => setAdvancedOpen(value => !value)}
                aria-expanded={advancedOpen}
              >
                <span>
                  <b>{pick("تنظیمات حرفه‌ای", "Advanced settings")}</b>
                  <small>{pick("همه پروتکل‌ها، اطلاعات حساب، QR و جزئیات فنی", "All protocols, account data, QR codes and technical details")}</small>
                </span>
                <span className={styles.chevron}>{advancedOpen ? "⌃" : "⌄"}</span>
              </button>

              {advancedOpen && (
                <div className={styles.advancedContent}>
                  <div className={styles.accountPanel}>
                    <div className={styles.advancedHeading}>
                      <div>
                        <span className={styles.sectionKicker}>{pick("حساب اتصال", "Connection account")}</span>
                        <h3>{pick("اطلاعات عمومی اشتراک", "Subscription credentials")}</h3>
                      </div>
                    </div>

                    <div className={styles.secretGrid}>
                      <div className={styles.secretRow}>
                        <span>{pick("نام کاربری", "Username")}</span>
                        <code>{info.account?.username || "—"}</code>
                        {info.account?.username && (
                          <button type="button" onClick={() => void copy("username", info.account.username!)}>{copied === "username" ? "✓" : "⧉"}</button>
                        )}
                      </div>
                      <div className={styles.secretRow}>
                        <span>{pick("رمز عبور", "Password")}</span>
                        <code>{info.account?.password || "—"}</code>
                        {info.account?.password && (
                          <button type="button" onClick={() => void copy("password", info.account.password!)}>{copied === "password" ? "✓" : "⧉"}</button>
                        )}
                      </div>
                      {info.subscription_link && (
                        <div className={`${styles.secretRow} ${styles.secretWide}`}>
                          <span>{pick("لینک اشتراک", "Subscription link")}</span>
                          <code>{info.subscription_link}</code>
                          <button type="button" onClick={() => void copy("subscription", info.subscription_link)}>{copied === "subscription" ? "✓" : "⧉"}</button>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={styles.protocolGroup}>
                    <div className={styles.groupHead}>
                      <div>
                        <span className={styles.sectionKicker}>{pick("پیشنهادی", "Recommended")}</span>
                        <h3>V2Ray / Xray</h3>
                      </div>
                      <span className={styles.liveBadge}>{pick("فعال", "Live")}</span>
                    </div>

                    <div className={styles.detailGrid}>
                      {xrayCards.map(({node, profile}, index) => {
                        const key = `advanced-${node}-${profile.id || index}-${index}`;
                        const uri = usableUri(profile);
                        return (
                          <article className={styles.detailCard} key={key}>
                            <div className={styles.detailHeader}>
                              <div>
                                <b>{profileLabel(profile, pick)}</b>
                                <small>{node}</small>
                              </div>
                              <span className={profile.recommended ? styles.readyBadge : styles.altBadge}>
                                {profile.recommended ? pick("پیشنهادی", "Recommended") : pick("جایگزین", "Alternative")}
                              </span>
                            </div>
                            <div className={styles.techFacts}>
                              <span><small>{pick("Transport", "Transport")}</small><b>{String(profile.transport || "—")}</b></span>
                              <span><small>{pick("امنیت", "Security")}</small><b>{securityLabel(profile)}</b></span>
                              <span><small>{pick("سرور", "Server")}</small><b dir="ltr">{profile.server || "—"}:{profile.port || "—"}</b></span>
                            </div>
                            <div className={styles.detailActions}>
                              <button type="button" onClick={() => openConnection(uri)}>{pick("باز کردن", "Open")}</button>
                              <button type="button" onClick={() => void copy(key, uri)}>{copied === key ? "✓" : pick("کپی لینک", "Copy link")}</button>
                              <button type="button" onClick={() => setQrValue(current => current === uri ? "" : uri)}>QR</button>
                            </div>
                          </article>
                        );
                      })}
                      {xrayCards.length === 0 && <div className={styles.emptyCard}>{pick("پروفایل Xray فعالی وجود ندارد.", "No active Xray profile is available.")}</div>}
                    </div>
                  </div>

                  <div className={styles.protocolGroup}>
                    <div className={styles.groupHead}>
                      <div>
                        <span className={styles.sectionKicker}>{pick("VPN کلاسیک", "Classic VPN")}</span>
                        <h3>{pick("پروتکل‌های سازگار", "Compatibility protocols")}</h3>
                      </div>
                    </div>

                    <div className={styles.detailGrid}>
                      {otherCredentials.map((row, index) => {
                        const value = serializedCredential(row.items);
                        const key = `advanced-classic-${row.protocol}-${index}`;
                        return (
                          <article className={styles.detailCard} key={key}>
                            <div className={styles.detailHeader}>
                              <div>
                                <b>{protocolName(row.protocol)}</b>
                                <small>{row.username || info.account?.username || ""}</small>
                              </div>
                              <span className={styles.liveBadge}>{pick("فعال", "Live")}</span>
                            </div>
                            <pre className={styles.configPreview}>{value}</pre>
                            {value && (
                              <div className={styles.detailActions}>
                                <button type="button" onClick={() => void copy(key, value)}>{copied === key ? "✓" : pick("کپی تنظیمات", "Copy config")}</button>
                              </div>
                            )}
                          </article>
                        );
                      })}
                      {otherCredentials.length === 0 && <div className={styles.emptyCard}>{pick("پروتکل کلاسیک فعالی برای این اشتراک ثبت نشده است.", "No classic protocol is active for this subscription.")}</div>}
                    </div>
                  </div>

                  <div className={styles.protocolGroup}>
                    <div className={styles.groupHead}>
                      <div>
                        <span className={styles.sectionKicker}>{pick("نسل جدید", "Next generation")}</span>
                        <h3>{pick("پروتکل‌های در حال آماده‌سازی", "Protocols in preparation")}</h3>
                      </div>
                      <span className={styles.progressBadge}>{pick("در حال تکمیل", "In progress")}</span>
                    </div>

                    <div className={styles.modernGrid}>
                      {modernRoadmap.map(item => (
                        <article className={styles.modernCard} key={item.key}>
                          <div className={styles.modernTop}>
                            <div className={styles.modernIcon}>◈</div>
                            <span className={styles.progressBadge}>{pick("در حال آماده‌سازی", "Preparing")}</span>
                          </div>
                          <b>{item.name}</b>
                          <small>{item.transport}</small>
                          <p>{item.note}</p>
                          <div className={styles.readinessNote}>
                            {pick(
                              "هسته سرور اضافه شده؛ تحویل حساب و کنترل حجم هنوز برای کاربران عمومی فعال نشده است.",
                              "Server runtime is added; customer account delivery and quota enforcement are not public yet.",
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </PortalShell>
  );
}
