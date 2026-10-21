"use client";

import {useEffect, useMemo, useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge, PageHead, Shell} from "./ui";
import styles from "./modern-protocols-admin-v2.module.css";


type OptionDef = {
  value: string;
  label_fa: string;
  label_en: string;
};

type FieldDef = {
  key: string;
  label_fa: string;
  label_en: string;
  type: string;
  help_fa?: string;
  help_en?: string;
  options?: OptionDef[];
  min?: number | null;
  max?: number | null;
  advanced?: boolean;
  secret?: boolean;
};

type CatalogItem = {
  key: string;
  title: string;
  category: string;
  core: string;
  adapter: string;
  runtime_status: string;
  installable: boolean;
  transport: string;
  default_port: number;
  tls: boolean;
  recommended_for: string[];
  formats: Record<string, boolean>;
  platforms: string[];
  presets: Record<string, Record<string, unknown>>;
  fields: FieldDef[];
  warnings?: string[];
};

type ProtocolRow = {
  protocol: string;
  name: string;
  category: string;
  core: string;
  adapter: string;
  runtime_status: string;
  installable: boolean;
  port: number;
  transport: string;
  service: string;
  status: string;
  last_error?: string | null;
  checked_at?: string | null;
  preset: string;
  settings: Record<string, unknown>;
  effective_settings: Record<string, unknown>;
  warnings: string[];
  config_hash?: string | null;
  last_applied_at?: string | null;
};

type NodeRow = {
  id: number;
  name: string;
  public_ip: string;
  public_domain?: string | null;
  status: string;
  protocols: ProtocolRow[];
};

type Inventory = {
  ok: boolean;
  schema_version: number;
  catalog: CatalogItem[];
  nodes: NodeRow[];
};

type EditorState = {
  node: NodeRow;
  row: ProtocolRow;
  definition: CatalogItem;
  port: number;
  preset: string;
  settings: Record<string, unknown>;
  showAdvanced: boolean;
};

type PreviewResponse = {
  ok: boolean;
  protocol: string;
  preset: string;
  effective_settings: Record<string, unknown>;
  warnings: string[];
  preview: Record<string, unknown>;
  config_hash: string;
  runtime_status: string;
};


const CATEGORY_ORDER = ["recommended", "camouflage", "standalone", "experimental"];

const CATEGORY_LABELS: Record<string, [string, string]> = {
  recommended: ["پیشنهادی و سریع", "Recommended & fast"],
  camouflage: ["استتار و سازگاری شبکه", "Camouflage & network compatibility"],
  standalone: ["Core مستقل", "Standalone cores"],
  experimental: ["آزمایشی", "Experimental"],
};

const PRESET_LABELS: Record<string, [string, string]> = {
  recommended: ["پیشنهادی", "Recommended"],
  performance: ["سرعت", "Performance"],
  compatibility: ["سازگاری", "Compatibility"],
  custom: ["سفارشی", "Custom"],
};

const WARNING_LABELS: Record<string, [string, string]> = {
  trusted_tls_recommended: ["برای NaiveProxy گواهی TLS معتبر عمومی بهتر از Self-signed است.", "A publicly trusted TLS certificate is recommended for NaiveProxy."],
  security_audit_required: ["این Adapter قبل از فعال شدن نیاز به Audit امنیتی دارد.", "This adapter requires a security audit before activation."],
  client_ecosystem_limited: ["اکوسیستم کلاینت محدود است و فعلاً Production-Ready محسوب نمی‌شود.", "Client ecosystem is limited; not production-ready yet."],
  tuic_zero_rtt_replay_risk: ["TUIC 0-RTT ریسک Replay دارد؛ خاموش ماندن آن توصیه می‌شود.", "TUIC 0-RTT has replay risk; keeping it disabled is recommended."],
  obfs_password_will_be_generated: ["رمز Obfuscation به‌صورت امن و پایدار روی نود تولید می‌شود.", "A stable secure obfuscation password will be generated on the node."],
  saved_settings_need_review: ["تنظیم ذخیره‌شده با Schema جدید نیاز به بازبینی دارد.", "Saved settings need review against the new schema."],
};


async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getCustomerToken();
  if (!token) throw new Error("AUTH_REQUIRED");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, {...init, headers, cache: "no-store"});
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try { payload = JSON.parse(text); }
    catch { payload = text; }
  }
  if (!response.ok) {
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as {detail?: unknown}).detail;
      if (typeof detail === "string") throw new Error(detail);
      if (detail && typeof detail === "object" && "message" in detail) {
        throw new Error(String((detail as {message?: unknown}).message || `API error ${response.status}`));
      }
    }
    throw new Error(`API error ${response.status}`);
  }
  return payload as T;
}


function tone(value: string): "ok" | "warn" | "bad" | "violet" {
  const status = String(value || "").toLowerCase();
  if (status === "online" || status === "ready") return "ok";
  if (status === "error" || status === "failed") return "bad";
  if (status === "not_installed" || status.includes("pending")) return "warn";
  return "violet";
}


function localizedPair(
  value: string,
  table: Record<string, [string, string]>,
): [string, string] {
  return table[value] ?? [value, value];
}


function shownValue(editor: EditorState, field: FieldDef): unknown {
  if (field.key in editor.settings) return editor.settings[field.key];
  const preset = editor.preset === "custom" ? "recommended" : editor.preset;
  return editor.definition.presets?.[preset]?.[field.key] ?? "";
}


function FieldControl({
  editor,
  field,
  pick,
  onChange,
}: {
  editor: EditorState;
  field: FieldDef;
  pick: (fa: string, en: string) => string;
  onChange: (value: unknown) => void;
}) {
  const value = shownValue(editor, field);
  const label = pick(field.label_fa, field.label_en);
  const help = pick(field.help_fa || "", field.help_en || "");
  const wide = field.type === "textarea";
  return (
    <div className={`${styles.field} ${wide ? styles.fieldWide : ""}`}>
      <label>{label}</label>
      {field.type === "boolean" ? (
        <div className={styles.switchRow}>
          <input type="checkbox" checked={Boolean(value)} onChange={event => onChange(event.target.checked)}/>
          <span>{Boolean(value) ? pick("فعال", "Enabled") : pick("غیرفعال", "Disabled")}</span>
        </div>
      ) : field.type === "select" ? (
        <select value={String(value ?? "")} onChange={event => onChange(event.target.value)}>
          {(field.options || []).map(option => (
            <option key={option.value} value={option.value}>{pick(option.label_fa, option.label_en)}</option>
          ))}
        </select>
      ) : field.type === "textarea" ? (
        <textarea rows={6} value={String(value ?? "")} onChange={event => onChange(event.target.value)}/>
      ) : (
        <input
          type={field.type === "number" ? "number" : field.secret ? "password" : "text"}
          min={field.min ?? undefined}
          max={field.max ?? undefined}
          value={String(value ?? "")}
          onChange={event => onChange(field.type === "number" ? Number(event.target.value) : event.target.value)}
        />
      )}
      {help && <small>{help}</small>}
    </div>
  );
}


export function ModernProtocolsAdminPage() {
  const {pick} = useI18n();
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [ports, setPorts] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);

  const load = async () => {
    setError("");
    const payload = await request<Inventory>("/v1/settings/vpn/modern-protocols");
    setInventory(payload);
    setPorts(current => {
      const next = {...current};
      for (const node of payload.nodes || []) {
        for (const protocol of node.protocols || []) {
          const key = `${node.id}:${protocol.protocol}`;
          if (!(key in next)) next[key] = protocol.port;
        }
      }
      return next;
    });
  };

  useEffect(() => {
    void load().catch(reason => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const catalogMap = useMemo(() => {
    const result = new Map<string, CatalogItem>();
    for (const item of inventory?.catalog || []) result.set(item.key, item);
    return result;
  }, [inventory]);

  const stats = useMemo(() => {
    const nodes = inventory?.nodes || [];
    const rows = nodes.flatMap(node => node.protocols || []);
    return {
      nodes: nodes.length,
      online: rows.filter(row => row.status === "online").length,
      ready: (inventory?.catalog || []).filter(item => item.installable).length,
      planned: (inventory?.catalog || []).filter(item => !item.installable).length,
    };
  }, [inventory]);

  const openEditor = (node: NodeRow, row: ProtocolRow) => {
    const definition = catalogMap.get(row.protocol);
    if (!definition) return;
    setPreview(null);
    setError("");
    setEditor({
      node,
      row,
      definition,
      port: ports[`${node.id}:${row.protocol}`] ?? row.port,
      preset: row.preset || "recommended",
      settings: {...(row.settings || {})},
      showAdvanced: false,
    });
  };

  const apply = async (state: EditorState) => {
    if (busy) return;
    if (!state.definition.installable) {
      setError(pick("Adapter رسمی این پروتکل هنوز آماده نصب نیست.", "The official adapter for this protocol is not installable yet."));
      return;
    }
    const key = `${state.node.id}:${state.row.protocol}`;
    setBusy(`apply:${key}`);
    setError("");
    setNotice("");
    try {
      await request(`/v1/settings/vpn/modern-protocols/${state.node.id}/install`, {
        method: "POST",
        body: JSON.stringify({
          protocols: [state.row.protocol],
          ports: {[state.row.protocol]: state.port},
          profiles: {
            [state.row.protocol]: {preset: state.preset, settings: state.settings},
          },
        }),
      });
      setNotice(pick(`${state.row.name} روی ${state.node.name} اعمال و Health Check شد.`, `${state.row.name} was applied and health-checked on ${state.node.name}.`));
      setEditor(null);
      setPreview(null);
      await load();
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally { setBusy(""); }
  };

  const quickApply = async (node: NodeRow, row: ProtocolRow) => {
    const definition = catalogMap.get(row.protocol);
    if (!definition) return;
    await apply({
      node,
      row,
      definition,
      port: ports[`${node.id}:${row.protocol}`] ?? row.port,
      preset: row.preset || "recommended",
      settings: {...(row.settings || {})},
      showAdvanced: false,
    });
  };

  const runPreview = async () => {
    if (!editor || busy) return;
    setBusy("preview");
    setError("");
    try {
      const result = await request<PreviewResponse>(`/v1/settings/vpn/modern-protocols/${editor.node.id}/preview`, {
        method: "POST",
        body: JSON.stringify({
          protocol: editor.row.protocol,
          port: editor.port,
          preset: editor.preset,
          settings: editor.settings,
        }),
      });
      setPreview(result);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(""); }
  };

  const health = async (node: NodeRow) => {
    if (busy) return;
    setBusy(`health:${node.id}`);
    setError("");
    try {
      await request(`/v1/settings/vpn/modern-protocols/${node.id}/health`, {method: "POST", body: JSON.stringify({})});
      setNotice(pick(`Health Check نود ${node.name} انجام شد.`, `Health check completed for ${node.name}.`));
      await load();
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(""); }
  };

  const remove = async (node: NodeRow, row: ProtocolRow) => {
    if (busy || !row.installable) return;
    if (!window.confirm(pick(`${row.name} از ${node.name} حذف شود؟`, `Remove ${row.name} from ${node.name}?`))) return;
    const key = `${node.id}:${row.protocol}`;
    setBusy(`remove:${key}`);
    setError("");
    try {
      await request(`/v1/settings/vpn/modern-protocols/${node.id}/${row.protocol}`, {method: "DELETE"});
      setNotice(pick(`${row.name} حذف شد.`, `${row.name} was removed.`));
      await load();
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(""); }
  };

  return (
    <Shell active="/admin/modern-protocols">
      <div className="page legacy-control-page">
        <PageHead
          title={pick("استودیوی پروتکل‌ها", "Protocol Studio")}
          sub={pick(
            "Preset پیشنهادی، تنظیمات حرفه‌ای، Preview، Validation و Runtime امن برای پروتکل‌های مدرن",
            "Recommended presets, advanced settings, preview, validation and safe runtimes for modern protocols",
          )}
        />

        <div className={styles.studio}>
          {error && <div className={styles.errorBox}>{error}</div>}
          {notice && <div className={styles.successBox}>{notice}</div>}

          <div className={styles.summaryGrid}>
            <div className={styles.summaryCard}><small>{pick("نود خروجی", "Exit nodes")}</small><strong>{stats.nodes.toLocaleString("fa-IR")}</strong></div>
            <div className={styles.summaryCard}><small>{pick("Runtime آماده نصب", "Installable runtimes")}</small><strong>{stats.ready.toLocaleString("fa-IR")}</strong></div>
            <div className={styles.summaryCard}><small>{pick("Listener آنلاین", "Online listeners")}</small><strong>{stats.online.toLocaleString("fa-IR")}</strong></div>
            <div className={styles.summaryCard}><small>{pick("Adapter بعدی", "Upcoming adapters")}</small><strong>{stats.planned.toLocaleString("fa-IR")}</strong></div>
          </div>

          {(inventory?.nodes || []).map(node => (
            <section className={styles.nodeCard} key={node.id}>
              <div className={styles.nodeHead}>
                <div className={styles.nodeTitle}>
                  <strong>{node.name}</strong>
                  <span>{node.public_domain || node.public_ip}</span>
                </div>
                <div className={styles.nodeActions}>
                  <Badge tone={tone(node.status)}>{node.status}</Badge>
                  <button className={styles.secondary} disabled={!!busy} onClick={() => void health(node)}>
                    {busy === `health:${node.id}` ? "…" : pick("بررسی سلامت", "Health check")}
                  </button>
                </div>
              </div>

              {CATEGORY_ORDER.map(category => {
                const rows = node.protocols.filter(row => row.category === category);
                if (!rows.length) return null;
                const [fa, en] = CATEGORY_LABELS[category] || [category, category];
                return (
                  <div className={styles.category} key={category}>
                    <div className={styles.categoryHead}>
                      <h3>{pick(fa, en)}</h3>
                      <span>{rows.length.toLocaleString("fa-IR")} {pick("پروتکل", "protocols")}</span>
                    </div>
                    <div className={styles.protocolGrid}>
                      {rows.map(row => {
                        const definition = catalogMap.get(row.protocol);
                        const key = `${node.id}:${row.protocol}`;
                        if (!definition) return null;
                        const presetLabels = localizedPair(row.preset, PRESET_LABELS);
                        return (
                          <article className={styles.protocolCard} key={row.protocol}>
                            <div className={styles.protocolTop}>
                              <div className={styles.protocolName}>
                                <strong>{row.name}</strong>
                                <small>{row.core} · {row.transport.toUpperCase()}</small>
                              </div>
                              <Badge tone={tone(row.status)}>{row.status}</Badge>
                            </div>

                            <div className={styles.chips}>
                              <span className={`${styles.chip} ${row.installable ? styles.chipReady : styles.chipPending}`}>
                                {row.installable ? pick("Runtime آماده", "Runtime ready") : pick("Adapter در راه", "Adapter pending")}
                              </span>
                              <span className={styles.chip}>{pick(presetLabels[0], presetLabels[1])}</span>
                              {Object.entries(definition.formats).filter(([, enabled]) => enabled).slice(0, 3).map(([format]) => (
                                <span className={styles.chip} key={format}>{format.replace("_", "-")}</span>
                              ))}
                            </div>

                            <div className={styles.portRow}>
                              <label>{pick("پورت Listener", "Listener port")}</label>
                              <input
                                type="number"
                                min={1}
                                max={65535}
                                value={ports[key] ?? row.port}
                                onChange={event => setPorts(current => ({...current, [key]: Number(event.target.value)}))}
                              />
                            </div>

                            {row.last_error && <div className={styles.errorBox}>{row.last_error}</div>}

                            <div className={styles.cardActions}>
                              <button className={styles.secondary} onClick={() => openEditor(node, row)}>
                                {pick("تنظیمات حرفه‌ای", "Advanced settings")}
                              </button>
                              <button
                                className={styles.primary}
                                disabled={!!busy || !row.installable}
                                onClick={() => void quickApply(node, row)}
                              >
                                {busy === `apply:${key}` ? "…" : row.status === "not_installed" ? pick("نصب پیشنهادی", "Install recommended") : pick("اعمال / تعمیر", "Apply / repair")}
                              </button>
                              {row.status !== "not_installed" && row.installable && (
                                <button className={styles.danger} disabled={!!busy} onClick={() => void remove(node, row)}>{pick("حذف", "Remove")}</button>
                              )}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </section>
          ))}
        </div>
      </div>

      {editor && (
        <div className={styles.modalBackdrop} onMouseDown={event => { if (event.target === event.currentTarget) setEditor(null); }}>
          <aside className={styles.drawer}>
            <div className={styles.drawerHead}>
              <div>
                <h2>{editor.row.name}</h2>
                <p>{editor.node.name} · {editor.definition.core} · {editor.definition.transport.toUpperCase()}</p>
              </div>
              <button className={styles.iconButton} onClick={() => setEditor(null)}>✕</button>
            </div>

            <div className={styles.presetGrid}>
              {Object.keys(PRESET_LABELS).map(name => {
                const [fa, en] = PRESET_LABELS[name];
                return (
                  <button
                    key={name}
                    className={`${styles.preset} ${editor.preset === name ? styles.presetActive : ""}`}
                    onClick={() => { setPreview(null); setEditor(current => current ? {...current, preset: name, settings: {}} : current); }}
                  >{pick(fa, en)}</button>
                );
              })}
            </div>

            <div className={styles.portRow}>
              <label>{pick("پورت", "Port")}</label>
              <input type="number" min={1} max={65535} value={editor.port} onChange={event => setEditor(current => current ? {...current, port: Number(event.target.value)} : current)}/>
            </div>

            <div className={styles.fields}>
              {editor.definition.fields.filter(field => !field.advanced).map(field => (
                <FieldControl
                  key={field.key}
                  editor={editor}
                  field={field}
                  pick={pick}
                  onChange={value => { setPreview(null); setEditor(current => current ? {...current, preset: "custom", settings: {...current.settings, [field.key]: value}} : current); }}
                />
              ))}
            </div>

            {editor.definition.fields.some(field => field.advanced) && (
              <>
                <button className={`${styles.secondary} ${styles.advancedToggle}`} onClick={() => setEditor(current => current ? {...current, showAdvanced: !current.showAdvanced} : current)}>
                  {editor.showAdvanced ? pick("− بستن تنظیمات پیشرفته", "− Hide advanced settings") : pick("+ تنظیمات پیشرفته", "+ Advanced settings")}
                </button>
                {editor.showAdvanced && (
                  <div className={styles.fields}>
                    {editor.definition.fields.filter(field => field.advanced).map(field => (
                      <FieldControl
                        key={field.key}
                        editor={editor}
                        field={field}
                        pick={pick}
                        onChange={value => { setPreview(null); setEditor(current => current ? {...current, preset: "custom", settings: {...current.settings, [field.key]: value}} : current); }}
                      />
                    ))}
                  </div>
                )}
              </>
            )}

            <div className={styles.chips}>
              {editor.definition.platforms.map(platform => <span className={styles.chip} key={platform}>{platform}</span>)}
              {Object.entries(editor.definition.formats).filter(([, enabled]) => enabled).map(([format]) => <span className={styles.chip} key={format}>{format}</span>)}
            </div>

            {(preview?.warnings || editor.row.warnings || []).map(code => {
              const labels: [string, string] = WARNING_LABELS[code] ?? [code, code];
              return <div className={styles.warningBox} key={code}>{pick(labels[0], labels[1])}</div>;
            })}

            {preview && (
              <div className={styles.previewBox}>
                <strong>{pick("Preview امن قبل از Apply", "Safe preview before apply")}</strong>
                <pre>{JSON.stringify(preview.preview, null, 2)}</pre>
              </div>
            )}

            {!editor.definition.installable && (
              <div className={styles.warningBox}>
                {pick("Schema و Preset این پروتکل آماده است، اما Adapter رسمی هنوز Production-Ready نشده و نصب عمداً غیرفعال است.", "The schema and presets are ready, but the official adapter is not production-ready yet, so installation is intentionally disabled.")}
              </div>
            )}

            <div className={styles.drawerFooter}>
              <button className={styles.secondary} disabled={!!busy} onClick={() => void runPreview()}>{busy === "preview" ? "…" : pick("Preview / اعتبارسنجی", "Preview / validate")}</button>
              <button className={styles.primary} disabled={!!busy || !editor.definition.installable} onClick={() => void apply(editor)}>{pick("اعمال تنظیمات", "Apply settings")}</button>
            </div>
          </aside>
        </div>
      )}
    </Shell>
  );
}
