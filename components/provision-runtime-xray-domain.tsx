"use client";

import {FormEvent, useEffect, useState} from "react";

import {Badge, Card, Shell} from "./ui";
import {adminApi, type AdminNode} from "../lib/admin-api";
import {type AnyRow, parityApi, type ProvisionInstallPayload, type ProvisionProtocolSettings} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";


const BASE_ONLY_PROTOCOLS: ProvisionProtocolSettings = {
  install_cisco: false,
  cisco_port: 443,
  install_openvpn: false,
  openvpn_port: 1194,
  openvpn_transport: "udp",
  install_wireguard: false,
  wireguard_port: 51820,
  install_l2tp: false,
  install_v2ray: false,
  xray_port: 8443,
};

const defaultInstall: ProvisionInstallPayload = {
  host: "",
  port: 22,
  username: "root",
  password: "",
  name: "",
  node_type: "exit",
  country_code: "DE",
  capacity_users: 1000,
  ...BASE_ONLY_PROTOCOLS,
};

function Notice({error, warning, ok}: {error: string; warning: string; ok: string}) {
  return <>
    {error && <div className="runtime-error">{error}</div>}
    {warning && <div className="runtime-warning">{warning}</div>}
    {ok && <div className="runtime-success">{ok}</div>}
  </>;
}

function StatusBadge({value}: {value: unknown}) {
  const status = String(value || "unknown").toLowerCase();
  const tone = ["online", "active", "ok", "healthy", "paired"].includes(status)
    ? "ok"
    : ["offline", "failed", "error", "revoked"].includes(status)
      ? "bad"
      : "warn";
  return <Badge tone={tone}>{String(value || "—")}</Badge>;
}

export function ProvisionRuntimeXrayDomainPage() {
  const {pick} = useI18n();
  const [nodes, setNodes] = useState<AdminNode[]>([]);
  const [draft, setDraft] = useState<ProvisionInstallPayload>(defaultInstall);
  const [selected, setSelected] = useState(0);
  const [lastNodeId, setLastNodeId] = useState(0);
  const [result, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [ok, setOk] = useState("");

  const load = async () => {
    setError("");
    try {
      const data = await adminApi.nodes();
      setNodes(data);
      setSelected(current => current && data.some(row => row.id === current) ? current : (data[0]?.id || 0));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const act = async (label: string, fn: () => Promise<unknown>, refresh = true) => {
    if (busy) return undefined;
    setBusy(true);
    setError("");
    setWarning("");
    setOk("");
    try {
      const out = await fn();
      setResult(out);
      setOk(label);
      if (refresh) await load();
      return out;
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      return undefined;
    }
    finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void act(
      pick("زیرساخت سرور با موفقیت راه‌اندازی شد.", "Server infrastructure was provisioned successfully."),
      async () => {
        const payload: ProvisionInstallPayload = {
          ...draft,
          country_code: draft.node_type === "iran" ? "IR" : draft.country_code.trim().toUpperCase(),
          ...BASE_ONLY_PROTOCOLS,
        };

        const output = await parityApi.provisionInstall(payload) as AnyRow;
        const nodeId = Number(output.node_id || 0);
        if (nodeId > 0) {
          setLastNodeId(nodeId);
          setSelected(nodeId);
        }
        return output;
      },
    );
  };

  const selectedNode = nodes.find(node => node.id === selected);
  const onlineNodes = nodes.filter(node => String(node.status).toLowerCase() === "online").length;
  const iranNodes = nodes.filter(node => node.node_type === "iran").length;
  const exitNodes = nodes.filter(node => node.node_type === "exit").length;
  const protocolsHref = `/admin/modern-protocols${lastNodeId ? `?node=${lastNodeId}` : selected ? `?node=${selected}` : ""}`;

  return <Shell active="/admin/provision">
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{pick("افزودن سرور", "Add Server")}</h1>
          <small>{pick(
            "اینجا فقط زیرساخت سرور، SSH، Agent و Fabric آماده می‌شود؛ نصب و تنظیم همه پروتکل‌ها از صفحه «پروتکل‌ها» انجام می‌شود.",
            "This page prepares only server infrastructure, SSH, Agent and Fabric; all protocol installation and configuration is managed from the Protocols page.",
          )}</small>
        </div>
        <button className="ghost" type="button" onClick={() => void load()}>{pick("بروزرسانی", "Refresh")}</button>
      </div>

      <Notice error={error} warning={warning} ok={ok}/>

      {lastNodeId > 0 && <Card>
        <div className="module-row">
          <div className="grow">
            <b>{pick("سرور آماده مدیریت پروتکل است", "Server is ready for protocol management")}</b>
            <small>{pick(
              "زیرساخت پایه نصب شده است. حالا پروتکل‌های موردنیاز همین سرور را در مرکز پروتکل‌ها انتخاب و نصب کنید.",
              "Base infrastructure is installed. Now choose and install the protocols for this server in Protocol Studio.",
            )}</small>
          </div>
          <a className="primary" href={protocolsHref}>{pick("مدیریت پروتکل‌ها", "Manage protocols")}</a>
        </div>
      </Card>}

      {result !== null && <Card>
        <div className="card-head">
          <div>
            <b>{pick("آخرین نتیجه عملیات", "Latest operation result")}</b>
            <small>{pick("جزئیات فنی فقط برای بررسی و عیب‌یابی نمایش داده می‌شوند.", "Technical details are available only for inspection and troubleshooting.")}</small>
          </div>
          <button className="mini-btn" type="button" onClick={() => setResult(null)}>×</button>
        </div>
        <details className="runtime-choice-section">
          <summary>{pick("نمایش جزئیات فنی", "Show technical details")}</summary>
          <pre className="runtime-log" dir="ltr">{JSON.stringify(result, null, 2)}</pre>
        </details>
      </Card>}

      <Card>
        <div className="module-row">
          <div className="grow">
            <b>{pick("وضعیت زیرساخت", "Infrastructure status")}</b>
            <small>{pick("خلاصه نودهای ثبت‌شده", "Registered node summary")}</small>
          </div>
          <Badge tone="warn">{pick("کل", "Total")} · {nodes.length}</Badge>
          <Badge tone="ok">{pick("آنلاین", "Online")} · {onlineNodes}</Badge>
          <Badge tone="warn">{pick("ایران", "Iran")} · {iranNodes}</Badge>
          <Badge tone="warn">{pick("خروجی", "Exit")} · {exitNodes}</Badge>
        </div>
      </Card>

      <div className="module-grid two" style={{alignItems: "start"}}>
        <Card>
          <div className="card-head">
            <div>
              <b>{pick("سرور جدید", "New server")}</b>
              <small>{pick(
                "اتصال SSH تست می‌شود و سپس Base، دسترسی امن، Node Agent و Tunnel Fabric نصب می‌شوند.",
                "SSH is verified, then the Base layer, secure access, Node Agent and Tunnel Fabric are installed.",
              )}</small>
            </div>
          </div>

          <form onSubmit={submit}>
            <div className="setting-grid">
              <label className="field">
                <span>{pick("نام سرور", "Server name")}</span>
                <input required value={draft.name} onChange={event => setDraft(current => ({...current, name: event.target.value}))}/>
              </label>

              <label className="field">
                <span>IP / Host</span>
                <input required dir="ltr" value={draft.host} onChange={event => setDraft(current => ({...current, host: event.target.value}))}/>
              </label>

              <label className="field">
                <span>{pick("نقش سرور", "Server role")}</span>
                <select
                  value={draft.node_type}
                  onChange={event => setDraft(current => ({
                    ...current,
                    node_type: event.target.value as "iran" | "exit",
                    country_code: event.target.value === "iran" ? "IR" : current.country_code === "IR" ? "DE" : current.country_code,
                  }))}
                >
                  <option value="iran">{pick("ایران · Relay / Tunnel", "Iran · Relay / Tunnel")}</option>
                  <option value="exit">{pick("خارج · Exit / VPN Access", "Exit · VPN Access")}</option>
                </select>
              </label>

              <label className="field">
                <span>{pick("کد کشور", "Country code")}</span>
                <input
                  required
                  dir="ltr"
                  maxLength={2}
                  minLength={2}
                  pattern="[A-Za-z]{2}"
                  disabled={draft.node_type === "iran"}
                  value={draft.node_type === "iran" ? "IR" : draft.country_code}
                  onChange={event => setDraft(current => ({...current, country_code: event.target.value.toUpperCase()}))}
                />
              </label>

              <label className="field">
                <span>SSH Port</span>
                <input type="number" min={1} max={65535} value={draft.port} onChange={event => setDraft(current => ({...current, port: Number(event.target.value)}))}/>
              </label>

              <label className="field">
                <span>SSH Username</span>
                <input required dir="ltr" value={draft.username} onChange={event => setDraft(current => ({...current, username: event.target.value}))}/>
              </label>

              <label className="field">
                <span>SSH Password</span>
                <input required type="password" autoComplete="new-password" value={draft.password} onChange={event => setDraft(current => ({...current, password: event.target.value}))}/>
              </label>

              <label className="field">
                <span>{pick("ظرفیت کاربر", "User capacity")}</span>
                <input type="number" min={1} value={draft.capacity_users} onChange={event => setDraft(current => ({...current, capacity_users: Number(event.target.value)}))}/>
              </label>
            </div>

            <div className="runtime-info-list">
              <div><span>{pick("پروتکل‌های کاربری", "Access protocols")}</span><b>{pick("در این مرحله نصب نمی‌شوند", "Not installed at this stage")}</b></div>
              <div><span>{pick("مرحله بعد", "Next step")}</span><b>{pick("پروتکل‌ها → انتخاب سرور → نصب", "Protocols → choose server → install")}</b></div>
            </div>

            <div className="action-row">
              <button
                type="button"
                className="ghost"
                disabled={busy || !draft.host || !draft.password}
                onClick={() => void act(
                  pick("اتصال SSH موفق بود", "SSH connection passed"),
                  () => parityApi.provisionTest({host: draft.host, port: draft.port, username: draft.username, password: draft.password}),
                  false,
                )}
              >
                {pick("تست SSH", "Test SSH")}
              </button>
              <button className="primary" disabled={busy || !draft.host || !draft.password || !draft.name}>
                {busy ? "…" : pick("افزودن و آماده‌سازی سرور", "Add & prepare server")}
              </button>
            </div>
          </form>
        </Card>

        <Card>
          <div className="card-head">
            <div>
              <b>{pick("عملیات زیرساخت نود موجود", "Existing node infrastructure")}</b>
              <small>{pick(
                "عملیات مربوط به Agent و Tunnel Fabric؛ مدیریت پروتکل‌ها عمداً از این بخش حذف شده است.",
                "Agent and Tunnel Fabric operations only; protocol management is intentionally removed from this section.",
              )}</small>
            </div>
          </div>

          <label className="field">
            <span>{pick("نود", "Node")}</span>
            <select value={selected} onChange={event => setSelected(Number(event.target.value))}>
              {nodes.map(node => <option key={node.id} value={node.id}>{node.name} · {node.public_ip} · {node.status}</option>)}
            </select>
          </label>

          {selectedNode && <div className="module-row">
            <div className="grow">
              <b>{selectedNode.name}</b>
              <small dir="ltr">{selectedNode.public_ip}</small>
            </div>
            <StatusBadge value={selectedNode.status}/>
          </div>}

          <div className="action-grid">
            <button className="ghost" type="button" disabled={!selected || busy} onClick={() => void act(pick("Agent ارتقا یافت", "Agent upgraded"), () => parityApi.provisionUpgradeAgent(selected))}>{pick("ارتقا Agent", "Upgrade agent")}</button>
            <button className="ghost" type="button" disabled={!selected || busy} onClick={() => void act(pick("Fabric نصب شد", "Fabric installed"), () => parityApi.provisionInstallFabric(selected))}>{pick("نصب Fabric", "Install fabric")}</button>
            <button className="ghost" type="button" disabled={!selected || busy} onClick={() => void act(pick("وضعیت Fabric دریافت شد", "Fabric status loaded"), () => parityApi.provisionFabricStatus(selected), false)}>{pick("وضعیت Fabric", "Fabric status")}</button>
            <a className="primary" href={protocolsHref}>{pick("مدیریت پروتکل‌ها", "Manage protocols")}</a>
          </div>
        </Card>
      </div>
    </div>
  </Shell>;
}
