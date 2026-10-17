"use client";

import {
  FormEvent,
  useEffect,
  useState,
} from "react";

import {
  Badge,
  Card,
  Shell,
} from "./ui";

import {
  AdminPaymentMarketRates,
} from "./admin-payment-market-rates";

import {
  API_BASE,
} from "../lib/api";

import {
  getCustomerToken,
} from "../lib/customer-api";

import {
  useI18n,
} from "../lib/i18n";


type PaymentSettings = {
  card_enabled: boolean;
  card_number: string;
  card_holder: string;

  usdt_trc20_enabled?: boolean;
  usdt_trc20_address?: string;

  usdt_bep20_enabled: boolean;
  usdt_bep20_address: string;

  trx_tron_enabled: boolean;
  trx_tron_address: string;

  bnb_bsc_enabled: boolean;
  bnb_bsc_address: string;

  usdt_rate_toman: number;

  sms_reader_enabled: boolean;
  sms_auto_verify: boolean;
  sms_allowed_senders: string;

  unique_amount_max_extra: number;

  auto_rate_enabled: boolean;
  crypto_auto_verify: boolean;

  live_rate_toman?: number;
  live_rate_provider?: string | null;
  live_rate_updated_at?: string | null;
  live_rate_error?: string | null;
};


type LiveRate = {
  ok: boolean;

  auto_rate_enabled: boolean;
  crypto_auto_verify: boolean;

  rate_toman: number;

  provider?: string | null;
  updated_at?: string | null;
  error?: string | null;
};


const defaultSettings: PaymentSettings = {
  card_enabled: false,
  card_number: "",
  card_holder: "",

  usdt_trc20_enabled: false,
  usdt_trc20_address: "",

  usdt_bep20_enabled: false,
  usdt_bep20_address: "",

  trx_tron_enabled: false,
  trx_tron_address: "",

  bnb_bsc_enabled: false,
  bnb_bsc_address: "",

  usdt_rate_toman: 0,

  sms_reader_enabled: false,
  sms_auto_verify: false,
  sms_allowed_senders: "",

  unique_amount_max_extra: 999,

  auto_rate_enabled: true,
  crypto_auto_verify: true,
};


async function paymentRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {

  const token = getCustomerToken();

  if (!token) {
    throw new Error("AUTH_REQUIRED");
  }

  const headers = new Headers(
    init.headers,
  );

  headers.set(
    "Authorization",
    `Bearer ${token}`,
  );

  if (
    init.body &&
    !headers.has("Content-Type")
  ) {
    headers.set(
      "Content-Type",
      "application/json",
    );
  }

  const response = await fetch(
    `${API_BASE}${path}`,
    {
      ...init,
      headers,
      cache: "no-store",
    },
  );

  if (response.status === 204) {
    return undefined as T;
  }

  const raw = await response.text();

  let payload: unknown = null;

  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
  }

  if (!response.ok) {

    const detail =
      payload &&
      typeof payload === "object" &&
      "detail" in payload
        ? String(
            (
              payload as {
                detail: unknown;
              }
            ).detail,
          )
        : `API error ${response.status}`;

    throw new Error(detail);
  }

  return payload as T;
}


function Toggle({
  label,
  sub,
  checked,
  onChange,
}: {
  label: string;
  sub?: string;
  checked: boolean;
  onChange: (
    value: boolean,
  ) => void;
}) {

  return (
    <label className="payGatewayToggle">

      <span>
        <b>{label}</b>

        {sub && (
          <small>
            {sub}
          </small>
        )}
      </span>

      <input
        type="checkbox"
        checked={checked}
        onChange={(event) =>
          onChange(
            event.target.checked,
          )
        }
      />

      <i/>

    </label>
  );
}


export function AdminPaymentsRuntime() {

  const {
    pick,
  } = useI18n();

  const [
    settings,
    setSettings,
  ] = useState<PaymentSettings>(
    defaultSettings,
  );

  const [
    liveRate,
    setLiveRate,
  ] = useState<LiveRate | null>(
    null,
  );

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    busy,
    setBusy,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState("");

  const [
    ok,
    setOk,
  ] = useState("");


  const refreshLiveRate =
    async () => {

      try {

        const rate =
          await paymentRequest<LiveRate>(
            "/v1/payments/admin/live-rate",
          );

        setLiveRate(rate);

      } catch {
        // Keep last known value.
      }
    };


  const load =
    async () => {

      setLoading(true);
      setError("");

      try {

        const [
          paymentSettings,
          rate,
        ] = await Promise.all([

          paymentRequest<
            Partial<PaymentSettings>
          >(
            "/v1/payments/admin/settings",
          ),

          paymentRequest<LiveRate>(
            "/v1/payments/admin/live-rate",
          ),

        ]);

        setSettings({
          ...defaultSettings,
          ...paymentSettings,
        });

        setLiveRate(rate);

      } catch (reason) {

        setError(
          reason instanceof Error
            ? reason.message
            : String(reason),
        );

      } finally {

        setLoading(false);
      }
    };


  useEffect(() => {

    void load();

  }, []);


  useEffect(() => {

    const timer =
      window.setInterval(
        () => {
          void refreshLiveRate();
        },
        10000,
      );

    return () =>
      window.clearInterval(timer);

  }, []);


  const saveSettings =
    async (
      event: FormEvent,
    ) => {

      event.preventDefault();

      if (busy) {
        return;
      }

      setBusy(true);
      setError("");
      setOk("");

      try {

        const updated =
          await paymentRequest<
            Partial<PaymentSettings>
          >(
            "/v1/payments/admin/settings",
            {
              method: "PUT",

              body: JSON.stringify(
                settings,
              ),
            },
          );

        setSettings({
          ...defaultSettings,
          ...updated,
        });

        setOk(
          pick(
            "تنظیمات پرداخت ذخیره شد.",
            "Payment settings saved.",
          ),
        );

        await refreshLiveRate();

      } catch (reason) {

        setError(
          reason instanceof Error
            ? reason.message
            : String(reason),
        );

      } finally {

        setBusy(false);
      }
    };


  const forceRateRefresh =
    async () => {

      if (busy) {
        return;
      }

      setBusy(true);
      setError("");
      setOk("");

      try {

        await paymentRequest(
          "/v1/payments/admin/market-rates/refresh",
          {
            method: "POST",
          },
        );

        await refreshLiveRate();

        setOk(
          pick(
            "نرخ ارزها بروزرسانی شد.",
            "Crypto rates refreshed.",
          ),
        );

      } catch (reason) {

        setError(
          reason instanceof Error
            ? reason.message
            : String(reason),
        );

      } finally {

        setBusy(false);
      }
    };


  const activeGateways = [
    settings.card_enabled,
    settings.usdt_bep20_enabled,
    settings.trx_tron_enabled,
    settings.bnb_bsc_enabled,
  ].filter(Boolean).length;


  const displayedRate = Number(
    liveRate?.rate_toman ||
    settings.live_rate_toman ||
    settings.usdt_rate_toman ||
    0,
  );


  return (
    <Shell active="/admin/payment-settings">

      <div className="page adminPayments2027">

        <div className="payPageHead">

          <div>
            <span>
              {pick(
                "فروش و مالی",
                "Sales & Finance",
              )}
            </span>

            <h1>
              {pick(
                "تنظیمات پرداخت",
                "Payment Settings",
              )}
            </h1>
          </div>

          <button
            className="ghost"
            type="button"
            disabled={
              loading ||
              busy
            }
            onClick={() =>
              void load()
            }
          >
            {pick(
              "بروزرسانی",
              "Refresh",
            )}
          </button>

        </div>


        {error && (
          <div className="runtime-error">
            {error}
          </div>
        )}

        {ok && (
          <div className="runtime-success">
            {ok}
          </div>
        )}


        <Card>

          <div className="card-head">

            <div>
              <b>
                {pick(
                  "وضعیت درگاه‌ها",
                  "Gateway status",
                )}
              </b>
            </div>

            <Badge
              tone={
                activeGateways
                  ? "ok"
                  : "warn"
              }
            >
              {activeGateways.toLocaleString(
                "fa-IR",
              )}{" "}
              {pick(
                "درگاه فعال",
                "active gateways",
              )}
            </Badge>

          </div>

        </Card>


        <form
          className="payGateways"
          onSubmit={saveSettings}
        >

          <div className="gatewayGrid">


            <Card
              className={`gatewayCard ${
                settings.card_enabled
                  ? "enabled"
                  : ""
              }`}
            >

              <div className="gatewayHead">

                <div className="gatewayIcon">
                  ◫
                </div>

                <div>
                  <b>
                    {pick(
                      "کارت به کارت",
                      "Card to card",
                    )}
                  </b>

                  <small>
                    {pick(
                      "پرداخت ریالی",
                      "Toman payment",
                    )}
                  </small>
                </div>

                <Badge
                  tone={
                    settings.card_enabled
                      ? "ok"
                      : "bad"
                  }
                >
                  {settings.card_enabled
                    ? pick(
                        "فعال",
                        "Active",
                      )
                    : pick(
                        "غیرفعال",
                        "Inactive",
                      )}
                </Badge>

              </div>


              <Toggle
                label={pick(
                  "فعال بودن کارت به کارت",
                  "Enable card to card",
                )}
                checked={
                  settings.card_enabled
                }
                onChange={(value) =>
                  setSettings(
                    current => ({
                      ...current,
                      card_enabled: value,
                    }),
                  )
                }
              />


              <label className="payField">

                <span>
                  {pick(
                    "شماره کارت",
                    "Card number",
                  )}
                </span>

                <input
                  dir="ltr"
                  value={
                    settings.card_number ||
                    ""
                  }
                  onChange={(event) =>
                    setSettings(
                      current => ({
                        ...current,
                        card_number:
                          event.target.value,
                      }),
                    )
                  }
                />

              </label>


              <label className="payField">

                <span>
                  {pick(
                    "نام صاحب کارت",
                    "Card holder",
                  )}
                </span>

                <input
                  value={
                    settings.card_holder ||
                    ""
                  }
                  onChange={(event) =>
                    setSettings(
                      current => ({
                        ...current,
                        card_holder:
                          event.target.value,
                      }),
                    )
                  }
                />

              </label>


              <label className="payField">

                <span>
                  {pick(
                    "حداکثر مبلغ اضافه برای مبلغ یکتا",
                    "Maximum unique amount extra",
                  )}
                </span>

                <div className="inputSuffix">

                  <input
                    type="number"
                    min={10}
                    max={999}
                    value={
                      settings
                        .unique_amount_max_extra ||
                      999
                    }
                    onChange={(event) =>
                      setSettings(
                        current => ({
                          ...current,
                          unique_amount_max_extra:
                            Number(
                              event.target.value,
                            ),
                        }),
                      )
                    }
                  />

                  <em>
                    {pick(
                      "تومان",
                      "Toman",
                    )}
                  </em>

                </div>

              </label>

            </Card>


            <Card
              className={`gatewayCard ${
                settings.usdt_bep20_enabled
                  ? "enabled"
                  : ""
              }`}
            >

              <div className="gatewayHead">

                <div className="gatewayIcon">
                  ₮
                </div>

                <div>
                  <b>
                    USDT · BEP20
                  </b>

                  <small>
                    BNB Smart Chain
                  </small>
                </div>

                <Badge
                  tone={
                    settings.usdt_bep20_enabled
                      ? "ok"
                      : "bad"
                  }
                >
                  {settings.usdt_bep20_enabled
                    ? pick(
                        "فعال",
                        "Active",
                      )
                    : pick(
                        "غیرفعال",
                        "Inactive",
                      )}
                </Badge>

              </div>


              <Toggle
                label={pick(
                  "فعال بودن USDT",
                  "Enable USDT",
                )}
                checked={
                  settings
                    .usdt_bep20_enabled
                }
                onChange={(value) =>
                  setSettings(
                    current => ({
                      ...current,
                      usdt_bep20_enabled:
                        value,
                    }),
                  )
                }
              />


              <label className="payField">

                <span>
                  {pick(
                    "آدرس کیف پول",
                    "Wallet address",
                  )}
                </span>

                <textarea
                  dir="ltr"
                  rows={3}
                  value={
                    settings
                      .usdt_bep20_address ||
                    ""
                  }
                  onChange={(event) =>
                    setSettings(
                      current => ({
                        ...current,
                        usdt_bep20_address:
                          event.target.value,
                      }),
                    )
                  }
                />

              </label>

            </Card>


            <Card
              className={`gatewayCard ${
                settings.trx_tron_enabled
                  ? "enabled"
                  : ""
              }`}
            >

              <div className="gatewayHead">

                <div className="gatewayIcon">
                  T
                </div>

                <div>
                  <b>
                    TRX · TRON
                  </b>

                  <small>
                    TRON Network
                  </small>
                </div>

                <Badge
                  tone={
                    settings.trx_tron_enabled
                      ? "ok"
                      : "bad"
                  }
                >
                  {settings.trx_tron_enabled
                    ? pick(
                        "فعال",
                        "Active",
                      )
                    : pick(
                        "غیرفعال",
                        "Inactive",
                      )}
                </Badge>

              </div>


              <Toggle
                label={pick(
                  "فعال بودن TRX",
                  "Enable TRX",
                )}
                checked={
                  settings
                    .trx_tron_enabled
                }
                onChange={(value) =>
                  setSettings(
                    current => ({
                      ...current,
                      trx_tron_enabled:
                        value,
                    }),
                  )
                }
              />


              <label className="payField">

                <span>
                  {pick(
                    "آدرس کیف پول TRON",
                    "TRON wallet address",
                  )}
                </span>

                <textarea
                  dir="ltr"
                  rows={3}
                  value={
                    settings
                      .trx_tron_address ||
                    ""
                  }
                  onChange={(event) =>
                    setSettings(
                      current => ({
                        ...current,
                        trx_tron_address:
                          event.target.value,
                      }),
                    )
                  }
                />

              </label>

            </Card>


            <Card
              className={`gatewayCard ${
                settings.bnb_bsc_enabled
                  ? "enabled"
                  : ""
              }`}
            >

              <div className="gatewayHead">

                <div className="gatewayIcon">
                  B
                </div>

                <div>
                  <b>
                    BNB · BSC
                  </b>

                  <small>
                    BNB Smart Chain
                  </small>
                </div>

                <Badge
                  tone={
                    settings.bnb_bsc_enabled
                      ? "ok"
                      : "bad"
                  }
                >
                  {settings.bnb_bsc_enabled
                    ? pick(
                        "فعال",
                        "Active",
                      )
                    : pick(
                        "غیرفعال",
                        "Inactive",
                      )}
                </Badge>

              </div>


              <Toggle
                label={pick(
                  "فعال بودن BNB",
                  "Enable BNB",
                )}
                checked={
                  settings
                    .bnb_bsc_enabled
                }
                onChange={(value) =>
                  setSettings(
                    current => ({
                      ...current,
                      bnb_bsc_enabled:
                        value,
                    }),
                  )
                }
              />


              <label className="payField">

                <span>
                  {pick(
                    "آدرس کیف پول BSC",
                    "BSC wallet address",
                  )}
                </span>

                <textarea
                  dir="ltr"
                  rows={3}
                  value={
                    settings
                      .bnb_bsc_address ||
                    ""
                  }
                  onChange={(event) =>
                    setSettings(
                      current => ({
                        ...current,
                        bnb_bsc_address:
                          event.target.value,
                      }),
                    )
                  }
                />

              </label>

            </Card>


            <Card className="gatewayCard gatewayAutomation">

              <div className="gatewayHead">

                <div className="gatewayIcon">
                  ⌁
                </div>

                <div>
                  <b>
                    {pick(
                      "نرخ ارز و تأیید خودکار",
                      "Rates & automation",
                    )}
                  </b>
                </div>

                <Badge
                  tone={
                    settings.auto_rate_enabled
                      ? "ok"
                      : "warn"
                  }
                >
                  {settings.auto_rate_enabled
                    ? pick(
                        "خودکار",
                        "Automatic",
                      )
                    : pick(
                        "دستی",
                        "Manual",
                      )}
                </Badge>

              </div>


              <label className="payField">

                <span>
                  {pick(
                    "نرخ فعلی USDT",
                    "Current USDT rate",
                  )}
                </span>

                <div className="inputSuffix">

                  <input
                    type="text"
                    readOnly
                    value={
                      displayedRate
                        ? displayedRate
                            .toLocaleString(
                              "fa-IR",
                            )
                        : "—"
                    }
                  />

                  <em>
                    {pick(
                      "تومان",
                      "Toman",
                    )}
                  </em>

                </div>

              </label>


              <Toggle
                label={pick(
                  "دریافت خودکار نرخ ارزها",
                  "Automatic crypto rates",
                )}
                checked={
                  settings
                    .auto_rate_enabled
                }
                onChange={(value) =>
                  setSettings(
                    current => ({
                      ...current,
                      auto_rate_enabled:
                        value,
                    }),
                  )
                }
              />


              {!settings.auto_rate_enabled && (

                <label className="payField">

                  <span>
                    {pick(
                      "نرخ دستی USDT",
                      "Manual USDT rate",
                    )}
                  </span>

                  <div className="inputSuffix">

                    <input
                      type="number"
                      min={0}
                      value={
                        settings
                          .usdt_rate_toman ||
                        0
                      }
                      onChange={(event) =>
                        setSettings(
                          current => ({
                            ...current,
                            usdt_rate_toman:
                              Number(
                                event
                                  .target
                                  .value,
                              ),
                          }),
                        )
                      }
                    />

                    <em>
                      {pick(
                        "تومان",
                        "Toman",
                      )}
                    </em>

                  </div>

                </label>

              )}


              <button
                type="button"
                className="ghost"
                disabled={busy}
                onClick={() =>
                  void forceRateRefresh()
                }
              >
                {pick(
                  "بروزرسانی نرخ‌ها",
                  "Refresh rates",
                )}
              </button>


              <Toggle
                label={pick(
                  "تأیید خودکار ارز دیجیتال",
                  "Automatic crypto verification",
                )}
                checked={
                  settings
                    .crypto_auto_verify
                }
                onChange={(value) =>
                  setSettings(
                    current => ({
                      ...current,
                      crypto_auto_verify:
                        value,
                    }),
                  )
                }
              />

            </Card>

          </div>


          <AdminPaymentMarketRates/>


          <div className="gatewaySaveBar">

            <div>
              <b>
                {pick(
                  "تنظیمات پرداخت",
                  "Payment settings",
                )}
              </b>

              <small>
                {pick(
                  "مبلغ ارز هر سفارش هنگام ایجاد پرداخت با نرخ همان لحظه محاسبه می‌شود.",
                  "Crypto amount is calculated using the live rate when payment is created.",
                )}
              </small>
            </div>

            <button
              className="primary"
              disabled={busy}
            >
              {busy
                ? "…"
                : pick(
                    "ذخیره تنظیمات",
                    "Save settings",
                  )}
            </button>

          </div>

        </form>

      </div>

    </Shell>
  );
}
