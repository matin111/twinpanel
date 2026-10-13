"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  QRCodeSVG,
} from "qrcode.react";

import {
  Badge,
  Card,
  PageHead,
} from "./ui";
import {
  PortalShell,
} from "./portal-shells";
import {
  API_BASE,
} from "../lib/api";
import {
  customerApi,
  getCustomerToken,
  type CustomerConnectionInfo,
  type MySubscription,
} from "../lib/customer-api";
import {
  useI18n,
} from "../lib/i18n";


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


type ModernEnsureResponse = {
  ok?: boolean;
  skipped?: boolean;
  reason?: string;
  migrated_node_ids?: number[];
  errors?: Array<Record<string, unknown>>;
  connection?: CustomerConnectionInfo;
};


const protocolName = (value: string) => ({
  cisco: "Cisco / OpenConnect",
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
    return pick("XHTTP + REALITY", "XHTTP + REALITY");
  }

  if (id === "httpupgrade_tls") {
    return pick("HTTP Upgrade + TLS", "HTTP Upgrade + TLS");
  }

  if (id === "grpc_reality") {
    return pick("gRPC + REALITY", "gRPC + REALITY");
  }

  return profile.title || id || pick("اتصال Xray", "Xray connection");
}


function securityLabel(
  profile: XrayProfile,
  pick: (fa: string, en: string) => string,
) {
  const security = String(profile.security || "").toLowerCase();

  if (security === "reality") {
    return pick("REALITY", "REALITY");
  }

  if (security === "tls") {
    return "TLS";
  }

  return security || "—";
}


export function CustomerConnectionModernPage() {
  const {pick} = useI18n();

  const [subscriptions, setSubscriptions] = useState<MySubscription[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [info, setInfo] = useState<CustomerConnectionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionLoading, setConnectionLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState("");


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

        const preferred = (
          rows.find(row => row.status === "active")
          || rows[0]
        );

        setSelected(preferred?.id || null);
      })
      .catch(reason => {
        setError(
          reason instanceof Error
            ? reason.message
            : String(reason),
        );
      })
      .finally(() => setLoading(false));
  }, []);


  useEffect(() => {
    if (!selected) {
      setInfo(null);
      return;
    }

    const token = getCustomerToken();
    if (!token) {
      return;
    }

    let alive = true;

    const load = async () => {
      setConnectionLoading(true);
      setError("");
      setNotice("");

      try {
        const response = await fetch(
          `${API_BASE}/v1/xray-modern/customer/${selected}/ensure`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
            },
            cache: "no-store",
          },
        );

        if (!response.ok) {
          const fallback = await customerApi.connectionInfo(
            token,
            selected,
          );

          if (alive) {
            setInfo(fallback);
            setNotice(
              pick(
                "اطلاعات فعلی نمایش داده شد؛ آماده‌سازی خودکار اتصال‌های جدید در این لحظه کامل نشد.",
                "Current credentials are shown; automatic modern Xray preparation did not complete at this moment.",
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

          if (
            Array.isArray(payload.migrated_node_ids)
            && payload.migrated_node_ids.length
          ) {
            setNotice(
              pick(
                "اتصال‌های امن جدید Xray برای حساب شما آماده شدند.",
                "New secure Xray connections are ready for your account.",
              ),
            );
          }
        }
      }
      catch (reason) {
        try {
          const fallback = await customerApi.connectionInfo(
            token,
            selected,
          );

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
            setError(
              reason instanceof Error
                ? reason.message
                : String(reason),
            );
          }
        }
      }
      finally {
        if (alive) {
          setConnectionLoading(false);
        }
      }
    };

    void load();

    return () => {
      alive = false;
    };
  }, [selected, pick]);


  const xrayCards = useMemo(() => {
    if (!info) {
      return [] as Array<{
        node: string;
        profile: XrayProfile;
      }>;
    }

    const output: Array<{
      node: string;
      profile: XrayProfile;
    }> = [];

    for (const credential of info.credentials) {
      if (String(credential.protocol).toLowerCase() !== "v2ray") {
        continue;
      }

      for (const item of normalizeItems(credential.items)) {
        const node = String(
          item.node
          || item.server
          || item.server_ip
          || pick("سرور Xray", "Xray server"),
        );

        if (Array.isArray(item.profiles)) {
          for (const profile of item.profiles) {
            if (profile && profile.uri) {
              output.push({node, profile});
            }
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

    return output;
  }, [info, pick]);


  const otherCredentials = useMemo(
    () => (
      info?.credentials.filter(
        row => String(row.protocol).toLowerCase() !== "v2ray",
      ) || []
    ),
    [info],
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


  return (
    <PortalShell
      type="customer"
      active="/panel/connection"
    >
      <div className="page customer-runtime">
        <PageHead
          title={pick("اتصال و کانفیگ", "Connection & Config")}
        />

        {loading && (
          <div className="customer-loading">
            <span className="customer-loader" />
            {pick("در حال دریافت اطلاعات...", "Loading...")}
          </div>
        )}

        {error && (
          <div className="customer-inline-warning">
            {error}
          </div>
        )}

        {notice && (
          <div className="customer-inline-warning">
            {notice}
          </div>
        )}

        {!loading && (
          <Card>
            <div className="customer-sub-select">
              {subscriptions.map(subscription => (
                <button
                  key={subscription.id}
                  type="button"
                  className={selected === subscription.id ? "active" : ""}
                  onClick={() => setSelected(subscription.id)}
                >
                  {subscription.plan_name || `#${subscription.id}`}
                  <small>{statusFa(subscription.status)}</small>
                </button>
              ))}
            </div>
          </Card>
        )}

        {connectionLoading && (
          <div className="customer-loading">
            <span className="customer-loader" />
            {pick(
              "در حال آماده‌سازی اتصال‌های امن...",
              "Preparing secure connections...",
            )}
          </div>
        )}

        {info && !connectionLoading && (
          <>
            <div className="module-grid two">
              <Card>
                <div className="card-head">
                  <div>
                    <b>{pick("حساب اتصال", "Connection account")}</b>
                    <small>
                      {pick(
                        "اطلاعات عمومی حساب شما",
                        "Your common account information",
                      )}
                    </small>
                  </div>
                </div>

                <div className="customer-secret-row">
                  <span>{pick("نام کاربری", "Username")}</span>
                  <code>{info.account?.username || "—"}</code>
                  {info.account?.username && (
                    <button
                      type="button"
                      onClick={() => void copy("username", info.account.username!)}
                    >
                      {copied === "username" ? "✓" : "⧉"}
                    </button>
                  )}
                </div>

                <div className="customer-secret-row">
                  <span>{pick("رمز عبور", "Password")}</span>
                  <code>{info.account?.password || "—"}</code>
                  {info.account?.password && (
                    <button
                      type="button"
                      onClick={() => void copy("password", info.account.password!)}
                    >
                      {copied === "password" ? "✓" : "⧉"}
                    </button>
                  )}
                </div>

                {info.subscription_link && (
                  <div className="customer-secret-row">
                    <span>{pick("لینک اشتراک", "Subscription link")}</span>
                    <code className="truncate">{info.subscription_link}</code>
                    <button
                      type="button"
                      onClick={() => void copy("subscription", info.subscription_link)}
                    >
                      {copied === "subscription" ? "✓" : "⧉"}
                    </button>
                  </div>
                )}
              </Card>

              <Card>
                <div className="card-head">
                  <div>
                    <b>{pick("راهنمای انتخاب", "Connection guide")}</b>
                    <small>
                      {pick(
                        "در شبکه‌های مختلف ممکن است یک مدل بهتر از دیگری باشد.",
                        "Different networks may perform better with different profiles.",
                      )}
                    </small>
                  </div>
                </div>

                <div className="runtime-info-list">
                  <div>
                    <span>{pick("اول امتحان کنید", "Try first")}</span>
                    <b>{pick("WebSocket یا XHTTP", "WebSocket or XHTTP")}</b>
                  </div>
                  <div>
                    <span>{pick("مسیر جایگزین", "Alternative")}</span>
                    <b>{pick("HTTP Upgrade یا gRPC", "HTTP Upgrade or gRPC")}</b>
                  </div>
                  <div>
                    <span>{pick("امنیت", "Security")}</span>
                    <b>TLS / REALITY</b>
                  </div>
                </div>
              </Card>
            </div>

            {xrayCards.length > 0 && (
              <Card className="span-two">
                <div className="card-head">
                  <div>
                    <b>{pick("اتصال‌های امن Xray", "Secure Xray connections")}</b>
                    <small>
                      {pick(
                        "چند مدل اتصال برای سازگاری بهتر با شبکه‌های مختلف",
                        "Multiple profiles for better compatibility across networks",
                      )}
                    </small>
                  </div>
                  <Badge tone="ok">
                    {pick("چندمسیره", "Multi-profile")}
                  </Badge>
                </div>

                <div className="module-grid two">
                  {xrayCards.map(({node, profile}, index) => {
                    const key = `${node}-${profile.id || index}-${index}`;
                    const uri = String(profile.uri || "");
                    const legacy = String(profile.id || "") === "legacy";

                    return (
                      <Card
                        key={key}
                        className="customer-credential"
                      >
                        <div className="card-head">
                          <div>
                            <b>{profileLabel(profile, pick)}</b>
                            <small>{node}</small>
                          </div>

                          <Badge
                            tone={
                              legacy
                                ? "warn"
                                : profile.recommended
                                  ? "ok"
                                  : "violet"
                            }
                          >
                            {legacy
                              ? pick("قدیمی", "Legacy")
                              : profile.recommended
                                ? pick("پیشنهادی", "Recommended")
                                : pick("جایگزین", "Alternative")}
                          </Badge>
                        </div>

                        <div className="runtime-info-list">
                          <div>
                            <span>{pick("نوع", "Transport")}</span>
                            <b>{String(profile.transport || "—")}</b>
                          </div>
                          <div>
                            <span>{pick("امنیت", "Security")}</span>
                            <b>{securityLabel(profile, pick)}</b>
                          </div>
                          <div>
                            <span>{pick("سرور", "Server")}</span>
                            <b dir="ltr">
                              {profile.server || "—"}:{profile.port || "—"}
                            </b>
                          </div>
                        </div>

                        {uri && (
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "minmax(0,1fr) auto",
                              gap: 14,
                              alignItems: "center",
                              marginTop: 14,
                            }}
                          >
                            <div className="customer-secret-row">
                              <span>{pick("لینک اتصال", "Connection link")}</span>
                              <code className="truncate">{uri}</code>
                              <button
                                type="button"
                                onClick={() => void copy(key, uri)}
                              >
                                {copied === key ? "✓" : "⧉"}
                              </button>
                            </div>

                            <div
                              style={{
                                padding: 8,
                                background: "white",
                                borderRadius: 12,
                                lineHeight: 0,
                              }}
                            >
                              <QRCodeSVG
                                value={uri}
                                size={118}
                                level="M"
                              />
                            </div>
                          </div>
                        )}
                      </Card>
                    );
                  })}
                </div>
              </Card>
            )}

            {otherCredentials.length > 0 && (
              <Card className="span-two">
                <div className="card-head">
                  <b>{pick("سایر پروتکل‌ها", "Other protocols")}</b>
                </div>

                <div className="module-grid two">
                  {otherCredentials.map((row, rowIndex) => (
                    <Card
                      key={`${row.protocol}-${rowIndex}`}
                      className="customer-credential"
                    >
                      <div className="card-head">
                        <div>
                          <b>{protocolName(row.protocol)}</b>
                          <small>{row.username || ""}</small>
                        </div>
                      </div>

                      <pre>
                        {typeof row.items === "string"
                          ? row.items
                          : JSON.stringify(row.items, null, 2)}
                      </pre>
                    </Card>
                  ))}
                </div>
              </Card>
            )}
          </>
        )}
      </div>
    </PortalShell>
  );
}
