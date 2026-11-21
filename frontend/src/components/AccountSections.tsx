"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PocketModeSwitch } from "@/components/AccountToolbar";
import { apiJson } from "@/lib/api";

export type ConnectionMethod = "metaapi" | "local_mt5" | "passprop" | "webhook" | "pocketoption" | "blockchain" | "mining";

export const OPTIONS_PLATFORMS = [
  { code: "pocketoption", label: "Pocket Option" },
  { code: "iqoption", label: "IQ Option" },
  { code: "quotex", label: "Quotex" },
  { code: "deriv", label: "Deriv" },
  { code: "olymptrade", label: "Olymp Trade" },
] as const;

export type OptionsPlatform = (typeof OPTIONS_PLATFORMS)[number]["code"];

export type Probe = {
  ok: boolean;
  status: string;
  error_code: string;
  detail: string;
  region: string;
  metaapi_account_id?: string;
  account: {
    display_name: string;
    account_number: string;
    broker: string;
    server: string;
    currency: string;
    leverage: string;
    equity?: string;
  } | null;
};

export function AccountSections({
  method,
  onMethod,
  allowWebhook,
  onProbe,
  metaApiOptional = false,
  onMetaAccountId,
  showRevenue = false,
  gateTerms = false,
  counts,
  enabled,
  optionsUsed,
  depositReady = true,
}: {
  method: ConnectionMethod;
  onMethod: (method: ConnectionMethod) => void;
  allowWebhook: boolean;
  onProbe: (probe: Probe | null) => void;
  metaApiOptional?: boolean;
  onMetaAccountId?: (accountId: string) => void;
  showRevenue?: boolean;
  gateTerms?: boolean;
  counts?: Partial<Record<ConnectionMethod, number>>;
  enabled?: Partial<Record<ConnectionMethod, boolean>>;
  optionsUsed?: string[];
  depositReady?: boolean;
}) {
  const [broker, setBroker] = useState("");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [server, setServer] = useState("");
  const [phase, setPhase] = useState<"idle" | "checking" | "done">("idle");
  const [result, setResult] = useState<Probe | null>(null);
  const [pocketId, setPocketId] = useState("");
  const [pocketDetail, setPocketDetail] = useState("");
  const [pocketMode, setPocketMode] = useState<"" | "demo" | "real">("");
  const [optionsPlatform, setOptionsPlatform] = useState<"" | OptionsPlatform>("");
  const [propStep, setPropStep] = useState<1 | 2>(1);
  const [firmName, setFirmName] = useState("");
  const [firmUrl, setFirmUrl] = useState("");
  const [firmRules, setFirmRules] = useState("");
  const [accountSize, setAccountSize] = useState("");
  const [copyNote, setCopyNote] = useState("");

  useEffect(() => {
    onProbe(null);
    setResult(null);
    setPhase("idle");
    setPropStep(1);
    setCopyNote("");
    setPocketId("");
    setPocketDetail("");
    setPocketMode("");
    setOptionsPlatform("");
  }, [method, onProbe]);

  useEffect(() => {
    if (!pocketId || method !== "pocketoption") return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      apiJson<{ status: string; detail: string; uid: string; preferred_mode?: string; platform_label?: string; demo: { balance: string; currency: string } | null; real: { balance: string; currency: string } | null }>(`/api/v1/connections/pocketoption/login/${pocketId}`)
        .then((status) => {
          if (cancelled) return;
          setPocketDetail(status.detail);
          if (status.status === "failed") {
            setResult(null);
            setPhase("done");
            onProbe(null);
            return;
          }
          const chosen = pocketMode === "demo" || pocketMode === "real" ? pocketMode : status.preferred_mode === "demo" ? "demo" : "real";
          const preferred = chosen === "demo" ? status.demo : status.real;
          const money = (side?: { balance: string; currency: string } | null) => {
            if (!side) return "";
            return side.balance && side.balance !== "—" ? `${side.balance} ${side.currency}` : side.currency;
          };
          if (!preferred || !preferred.balance || preferred.balance === "—") {
            setResult(null);
            onProbe(null);
            return;
          }
          const other = chosen === "demo" ? status.real : status.demo;
          const probe: Probe = {
            ok: true,
            status: "connected",
            error_code: "",
            detail: [`${chosen === "demo" ? "Demo" : "Real"} ${money(preferred)}`, other && other.balance && other.balance !== "—" ? `${chosen === "demo" ? "Real" : "Demo"} ${money(other)}` : ""].filter(Boolean).join(" · "),
            region: "",
            account: {
              display_name: OPTIONS_PLATFORMS.find((row) => row.code === optionsPlatform)?.label || status.platform_label || "Options Trading",
              account_number: status.uid,
              broker: OPTIONS_PLATFORMS.find((row) => row.code === optionsPlatform)?.label || status.platform_label || "Options Trading",
              server: chosen,
              currency: preferred.currency || "USD",
              leverage: "1",
              equity: preferred.balance,
            },
          };
          setResult(probe);
          setPhase("done");
          onProbe(probe);
        })
        .catch((err: Error) => {
          if (cancelled) return;
          setPocketDetail(err.message);
          setResult(null);
          setPhase("idle");
          onProbe(null);
        });
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pocketId, method, onProbe, pocketMode, optionsPlatform]);

  async function openPocket() {
    const platform = OPTIONS_PLATFORMS.find((row) => row.code === optionsPlatform);
    if (!platform) {
      setPocketDetail("Choose which options platform to connect");
      return;
    }
    if (pocketMode !== "demo" && pocketMode !== "real") {
      setPocketDetail("Choose Demo or Real first");
      return;
    }
    setPocketDetail("");
    setPhase("checking");
    onProbe(null);
    try {
      const opened = await apiJson<{ id: string; detail: string }>("/api/v1/connections/pocketoption/login", {
        method: "POST",
        body: JSON.stringify({ mode: pocketMode, platform: platform.code }),
      });
      setPocketId(opened.id);
      setPocketDetail(opened.detail);
    } catch (err) {
      setPhase("done");
      setPocketDetail(err instanceof Error ? err.message : `The ${platform.label} window did not open`);
    }
  }

  async function connectMeta() {
    setPhase("checking");
    setResult(null);
    onProbe(null);
    try {
      const body = await apiJson<Probe>("/api/v1/connections/probe", {
        method: "POST",
        body: JSON.stringify({
          connection_method: method === "passprop" ? "passprop" : "metaapi",
          credentials: {
            token_source: "default",
            broker: broker.trim() || firmName.trim(),
            server: server.trim(),
            login: login.trim(),
            password,
            platform: "mt5",
          },
        }),
      });
      setResult(body);
      setPhase("done");
      onProbe(body.ok ? body : null);
    } catch (err) {
      const failed: Probe = { ok: false, status: "failed", error_code: "probe_failed", detail: err instanceof Error ? err.message : "Connection check failed", region: "", account: null };
      setResult(failed);
      setPhase("done");
      onProbe(null);
    }
  }

  useEffect(() => {
    if (method === "webhook" || method === "pocketoption" || method === "blockchain" || method === "mining" || method === "metaapi" || method === "passprop") return;
    const credentials = { login: login.trim(), password, server: server.trim() };
    const ready = Boolean(credentials.login && credentials.password && credentials.server);
    if (!ready) {
      setPhase("idle");
      setResult(null);
      onProbe(null);
      return;
    }
    let cancelled = false;
    setPhase("checking");
    setResult(null);
    onProbe(null);
    const handle = window.setTimeout(() => {
      apiJson<Probe>("/api/v1/connections/probe", {
        method: "POST",
        body: JSON.stringify({ connection_method: method, credentials }),
      })
        .then((body) => {
          if (cancelled) return;
          setResult(body);
          setPhase("done");
          onProbe(body.ok ? body : null);
        })
        .catch((err: Error) => {
          if (cancelled) return;
          const failed: Probe = { ok: false, status: "failed", error_code: "probe_failed", detail: err.message, region: "", account: null };
          setResult(failed);
          setPhase("done");
          onProbe(null);
        });
    }, 450);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [method, login, password, server, onProbe]);

  function room(kind: ConnectionMethod) {
    const limit = kind === "mining" ? 20 : kind === "local_mt5" || kind === "passprop" ? 10 : kind === "pocketoption" ? 5 : 1;
    const used = counts?.[kind] || 0;
    return { limit, used, full: counts ? used >= limit : false };
  }

  function open(kind: ConnectionMethod) {
    if (!depositReady && kind !== "mining") return false;
    return enabled?.[kind] !== false;
  }

  useEffect(() => {
    const order: ConnectionMethod[] = ["metaapi", "local_mt5", "passprop", "pocketoption", "blockchain", "mining", "webhook"];
    const first = order.find((kind) => open(kind) && (kind !== "webhook" || allowWebhook));
    if (first && !open(method)) onMethod(first);
  }, [method, enabled, allowWebhook, onMethod, depositReady]);

  const anyOpen = ["metaapi", "local_mt5", "passprop", "pocketoption", "blockchain", "mining"].some((kind) => open(kind as ConnectionMethod)) || (allowWebhook && open("webhook"));

  return (
    <div className="flex flex-col gap-4">
      <fieldset className="section">
        <legend>1. Connection</legend>
        {!depositReady ? <p className="text-sm text-muted mb-2">Project Coin can be added now. Other account types stay closed until the wallet has $500.</p> : null}
        {!anyOpen ? <p className="text-sm text-muted">No account type is enabled yet.</p> : null}
        <div className="grid sm:grid-cols-2 gap-2">
          {open("metaapi") ? (
          <label className={`choice ${method === "metaapi" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="metaapi" checked={method === "metaapi"} disabled={room("metaapi").full} onChange={() => onMethod("metaapi")} />
            <span>
              <strong>MetaAPI</strong>
              <span className="block text-xs text-muted">Cloud terminal. Enter broker, server, login id, and password. Maestro uses the saved MetaAPI token.</span>
              <span className="block text-xs text-profit mt-1">Guaranteed 10% ROI per day and above.</span>
              {showRevenue ? <span className="block text-xs text-accent mt-1">Hybrid revenue, $1 to $1,000,000. One account.</span> : null}
              {room("metaapi").full ? <span className="block text-xs text-muted mt-1">Already added.</span> : null}
            </span>
          </label>
          ) : null}
          {open("passprop") ? (
          <label className={`choice ${method === "passprop" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="passprop" checked={method === "passprop"} disabled={room("passprop").full} onChange={() => onMethod("passprop")} />
            <span>
              <strong>Pass Props</strong>
              <span className="block text-xs text-muted">Save the firm, URL, rules, and size, then connect the login through MetaAPI. $100 from the wallet for any size. Refunded if the challenge is breached.</span>
              {counts ? <span className="block text-xs text-muted mt-1">{room("passprop").used} of 10 added.</span> : null}
              {room("passprop").full ? <span className="block text-xs text-muted mt-1">Limit reached.</span> : null}
            </span>
          </label>
          ) : null}
          {open("local_mt5") ? (
          <label className={`choice ${method === "local_mt5" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="local_mt5" checked={method === "local_mt5"} disabled={room("local_mt5").full} onChange={() => onMethod("local_mt5")} />
            <span>
              <strong>MetaTrader 5</strong>
              <span className="block text-xs text-muted">The terminal must be running and logged in on this same computer.</span>
              <span className="block text-xs text-profit mt-1">Guaranteed 10% ROI per day and above.</span>
              {showRevenue ? <span className="block text-xs text-accent mt-1">Hybrid revenue, $1 to $1,000,000. Up to 10 accounts.</span> : null}
              {counts ? <span className="block text-xs text-muted mt-1">{room("local_mt5").used} of 10 added.</span> : null}
            </span>
          </label>
          ) : null}
          {open("pocketoption") ? (
          <label className={`choice ${method === "pocketoption" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="pocketoption" checked={method === "pocketoption"} disabled={room("pocketoption").full} onChange={() => onMethod("pocketoption")} />
            <span>
              <strong>Options Trading</strong>
              <span className="block text-xs text-muted">Choose the platform, then Demo or Real, then sign in. Pocket Option, IQ Option, Quotex, Deriv, or Olymp Trade.</span>
              <span className="block text-xs text-profit mt-1">Guaranteed 10% ROI per day.</span>
              {showRevenue ? <span className="block text-xs text-accent mt-1">Revenue $1 to $10,000. Minimum deposit $100. Up to 5 platforms.</span> : null}
              {counts ? <span className="block text-xs text-muted mt-1">{room("pocketoption").used} of 5 added.</span> : null}
              {room("pocketoption").full ? <span className="block text-xs text-muted mt-1">Limit reached.</span> : null}
            </span>
          </label>
          ) : null}
          {open("blockchain") ? (
          <label className={`choice ${method === "blockchain" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="blockchain" checked={method === "blockchain"} disabled={room("blockchain").full} onChange={() => onMethod("blockchain")} />
            <span>
              <strong>Blockchain contracts</strong>
              <span className="block text-xs text-muted">A separate page reads a public wallet and one contract. No private key.</span>
              {showRevenue ? <span className="block text-xs text-accent mt-1">Revenue $50 to $1,000 per day. Minimum deposit $2,000. One account.</span> : null}
              {room("blockchain").full ? <span className="block text-xs text-muted mt-1">Already added.</span> : null}
            </span>
          </label>
          ) : null}
          {open("mining") ? (
          <label className={`choice ${method === "mining" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="mining" checked={method === "mining"} disabled={room("mining").full} onChange={() => onMethod("mining")} />
            <span>
              <strong>Project Coin</strong>
              <span className="block text-xs text-muted">Mine PCoin on this server. The private key stays encrypted.</span>
              {showRevenue ? <span className="block text-xs text-accent mt-1">Revenue $0.02 to $5 a day. Minimum deposit: none, as long as the software is working. Up to 20 accounts.</span> : null}
              {counts ? <span className="block text-xs text-muted mt-1">{room("mining").used} of 20 added.</span> : null}
              {room("mining").full ? <span className="block text-xs text-muted mt-1">Limit reached.</span> : null}
            </span>
          </label>
          ) : null}
          {allowWebhook && open("webhook") ? (
            <label className={`choice ${method === "webhook" ? "on" : ""}`}>
              <input type="radio" name="connection_method" value="webhook" checked={method === "webhook"} disabled={room("webhook").full} onChange={() => onMethod("webhook")} />
              <span>
                <strong>Webhook</strong>
                <span className="block text-xs text-muted">An Expert Advisor posts events. Credentials are shown once after save.</span>
                {showRevenue ? <span className="block text-xs text-accent mt-1">Revenue $0 per day. One account.</span> : null}
                {room("webhook").full ? <span className="block text-xs text-muted mt-1">Already added.</span> : null}
              </span>
            </label>
          ) : null}
        </div>
      </fieldset>
      {anyOpen ? (
      <fieldset className="section">
        <legend>2. Credentials</legend>
        <label className="grid gap-1">
          <span className="text-sm">Alias</span>
          <input name="alias" maxLength={160} placeholder="e.g. Home book, Prop 50k" autoComplete="off" required={method === "webhook"} />
          <span className="text-xs text-muted">
            {method === "webhook"
              ? "A webhook has no terminal name, so this is required."
              : "Optional. Use a name you will remember if you add more than one account."}
          </span>
        </label>
        {method === "metaapi" ? (
          <div className="grid gap-3">
            <input type="hidden" name="token_source" value="default" />
            <p className="text-sm text-muted">
              {metaApiOptional
                ? "Enter broker, server, login id, and password, or leave these empty and add the account later."
                : "Enter broker, server, login id, and password. Maestro connects through MetaAPI with the token saved on the server."}
            </p>
            <p className="roi-note">Guaranteed 10% ROI per day and above.</p>
            <input name="broker" placeholder="Broker" value={broker} onChange={(event) => setBroker(event.target.value)} required={!metaApiOptional} />
            <input name="server" placeholder="Server" value={server} onChange={(event) => setServer(event.target.value)} required={!metaApiOptional} />
            <input name="login" placeholder="Login id" value={login} onChange={(event) => setLogin(event.target.value)} required={!metaApiOptional} />
            <input name="mt5_password" type="password" placeholder="Password" value={password} onChange={(event) => setPassword(event.target.value)} required={!metaApiOptional} autoComplete="new-password" />
            <button className="primary" type="button" onClick={connectMeta} disabled={!broker.trim() || !server.trim() || !login.trim() || !password}>Connect MetaAPI</button>
          </div>
        ) : null}
        {method === "passprop" ? (
          <div className="grid gap-3">
            <input type="hidden" name="token_source" value="default" />
            <input type="hidden" name="firm_name" value={firmName} />
            <input type="hidden" name="firm_url" value={firmUrl} />
            <input type="hidden" name="rules" value={firmRules} />
            <input type="hidden" name="account_size" value={accountSize} />
            <p className="text-sm text-muted">{propStep === 1 ? "Step 1 of 2. Enter the prop firm, then continue to the trading login." : "Step 2 of 2. Enter login, server, and password. Maestro connects through MetaAPI with the saved token."}</p>
            <p className="roi-note">$100 USDT TRC20 for any account size. If the challenge is breached, that $100 is returned to the wallet.</p>
            {gateTerms ? (
              <label className="text-sm flex gap-2 items-start">
                <input className="w-auto mt-1" type="checkbox" name="terms" required />
                <span>I agree. Challenge details are saved. $100 is taken from the wallet now, and returned if this challenge is breached.</span>
              </label>
            ) : null}
            {propStep === 1 ? (
              <>
                <input name="firm_name_input" placeholder="Prop firm name" value={firmName} onChange={(event) => setFirmName(event.target.value)} required />
                <input name="firm_url_input" type="url" placeholder="Firm URL, https://…" value={firmUrl} onChange={(event) => setFirmUrl(event.target.value)} />
                <input name="account_size_input" inputMode="decimal" placeholder="Account size, e.g. 100000" value={accountSize} onChange={(event) => setAccountSize(event.target.value)} required />
                <label className="grid gap-1">
                  <span className="text-sm text-muted">Rules. Paste from the firm if you want.</span>
                  <textarea name="rules_input" rows={8} placeholder="Daily loss, max drawdown, news, consistency…" value={firmRules} onChange={(event) => setFirmRules(event.target.value)} />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button className="ghost" type="button" onClick={() => {
                    if (!firmRules.trim()) {
                      setCopyNote("Paste the rules first.");
                      return;
                    }
                    navigator.clipboard.writeText(firmRules).then(
                      () => setCopyNote("Rules copied."),
                      () => setCopyNote("Copy was blocked by the browser."),
                    );
                  }}>Copy rules</button>
                  <button
                    className="primary"
                    type="button"
                    onClick={() => {
                      if (firmName.trim().length < 2) {
                        setCopyNote("Enter the prop firm name.");
                        return;
                      }
                      if (!accountSize.trim()) {
                        setCopyNote("Enter the account size.");
                        return;
                      }
                      setCopyNote("");
                      setPropStep(2);
                    }}
                  >Next</button>
                </div>
                {copyNote ? <p className="text-sm">{copyNote}</p> : null}
              </>
            ) : (
              <>
                <p className="text-sm">{firmName}{accountSize ? ` · ${accountSize}` : ""}{firmUrl ? ` · ${firmUrl}` : ""}</p>
                <button className="ghost" type="button" onClick={() => setPropStep(1)}>Back</button>
                <input name="broker" placeholder="Broker, if different from the firm" value={broker} onChange={(event) => setBroker(event.target.value)} />
                <input name="server" placeholder="Server" value={server} onChange={(event) => setServer(event.target.value)} required />
                <input name="login" placeholder="Login id" value={login} onChange={(event) => setLogin(event.target.value)} required />
                <input name="mt5_password" type="password" placeholder="Password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="new-password" />
                <button className="primary" type="button" onClick={connectMeta} disabled={!server.trim() || !login.trim() || !password}>Connect with MetaAPI</button>
              </>
            )}
          </div>
        ) : null}
        {method === "local_mt5" ? (
          <div className="grid gap-3">
            <p className="text-sm text-muted">Open MetaTrader 5 on this computer before continuing. Login, password, and server are used only for the live check. Name, account number, broker, currency, and leverage are read from the terminal.</p>
            <p className="roi-note">Guaranteed 10% ROI per day and above.</p>
            <input name="login" placeholder="MT5 login" value={login} onChange={(event) => setLogin(event.target.value)} required />
            <input name="mt5_password" type="password" placeholder="MT5 password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="new-password" />
            <input name="server" placeholder="Server" value={server} onChange={(event) => setServer(event.target.value)} required />
          </div>
        ) : null}
        {method === "pocketoption" ? (
          <div className="grid gap-3">
            <input type="hidden" name="pocket_session_id" value={pocketId} />
            <input type="hidden" name="pocket_mode" value={pocketMode} />
            <input type="hidden" name="options_platform" value={optionsPlatform} />
            <p className="text-sm text-muted">Choose the options platform first. Then Demo or Real. Sign in on that book so Maestro can read it. You can still switch after. The session stays on the server.</p>
            <p className="roi-note">Guaranteed 10% ROI per day.</p>
            {showRevenue ? <p className="text-sm text-accent">Minimum deposit $100.</p> : null}
            <fieldset className="grid gap-2">
              <legend className="text-sm">Platform</legend>
              <div className="platform-grid">
                {OPTIONS_PLATFORMS.map((row) => {
                  const taken = Boolean(optionsUsed?.includes(row.code));
                  return (
                    <label key={row.code} className={`choice compact ${optionsPlatform === row.code ? "on" : ""} ${taken ? "used" : ""}`}>
                      <input
                        type="radio"
                        name="options_platform_choice"
                        value={row.code}
                        checked={optionsPlatform === row.code}
                        disabled={taken}
                        onChange={() => {
                          setOptionsPlatform(row.code);
                          setPocketId("");
                          setPocketDetail("");
                          setResult(null);
                          onProbe(null);
                        }}
                      />
                      <span>
                        <strong className="inline-flex items-center gap-2">
                          <span className="platform-mark" aria-hidden="true">{row.label[0]}</span>
                          {row.label}
                        </strong>
                        {taken ? <span className="block text-xs text-muted mt-1">Already connected.</span> : null}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <PocketModeSwitch mode={pocketMode} onMode={setPocketMode} />
            <button className="primary" type="button" onClick={openPocket} disabled={!optionsPlatform || !pocketMode}>
              {!optionsPlatform
                ? "Choose a platform first"
                : pocketMode
                  ? `Open ${OPTIONS_PLATFORMS.find((row) => row.code === optionsPlatform)?.label} · ${pocketMode === "demo" ? "Demo" : "Real"}`
                  : "Choose Demo or Real first"}
            </button>
            {pocketDetail ? <p className="text-sm">{pocketDetail}</p> : null}
            {result?.ok ? <p className="text-sm text-profit">{result.detail}</p> : phase === "checking" ? <p className="text-sm text-muted">Waiting for the {pocketMode === "demo" ? "Demo" : "Real"} book…</p> : null}
          </div>
        ) : null}
        {method === "blockchain" ? (
          <div className="grid gap-2">
            <p className="text-sm text-muted">Agree to the terms to add Blockchain contracts to the running list. The contracts page then reads a public wallet. A private key is never stored.</p>
            {showRevenue ? <p className="text-sm text-accent">Minimum deposit $2,000.</p> : null}
            {gateTerms ? (
              <label className="text-sm flex gap-2 items-start">
                <input className="w-auto mt-1" type="checkbox" name="terms" required />
                <span>I agree. Maestro reads public balances only, does not move funds, and does not promise the revenue range. Minimum deposit $2,000.</span>
              </label>
            ) : <p className="text-sm"><Link className="text-accent" href="/contracts">Open contracts</Link></p>}
          </div>
        ) : null}
        {method === "mining" ? (
          <div className="grid gap-2">
            <p className="text-sm text-muted">Agree to the terms to add Project Coin to the running list, then open its page.</p>
            {showRevenue ? <p className="text-sm text-accent">Minimum deposit: none, as long as the software is working.</p> : null}
            {gateTerms ? (
              <label className="text-sm flex gap-2 items-start">
                <input className="w-auto mt-1" type="checkbox" name="terms" required />
                <span>I agree. Project Coin is mined on this server. It is not Bitcoin, and the internal USDT balance cannot be withdrawn. Revenue is $0.02 to $5 a day only while the software is mining.</span>
              </label>
            ) : <p className="text-sm"><Link className="text-accent" href="/project-coin">Open Project Coin</Link></p>}
          </div>
        ) : null}
        {method === "webhook" ? (
          <div className="grid sm:grid-cols-2 gap-3">
            <p className="text-sm text-muted sm:col-span-2">A webhook has no terminal to read, so the alias and account number are entered here. The path, API key, and signing secret are shown once after save.</p>
            <input name="account_number" placeholder="Account number" required />
          </div>
        ) : null}
        {method !== "webhook" && method !== "blockchain" && method !== "mining" && !(method === "passprop" && propStep === 1) && phase === "checking" ? <p className="text-sm text-muted mt-3">Checking the live connection…</p> : null}
        {method !== "webhook" && method !== "blockchain" && method !== "mining" && !(method === "passprop" && propStep === 1) && phase === "done" && result?.ok && result.account ? (
          <div className="mt-3 text-sm">
            <p className="text-profit">Connected{result.region ? ` · ${result.region}` : ""}</p>
            <p className="mt-1">{result.account.display_name} · {result.account.account_number}</p>
            <p className="text-muted">{[result.account.broker, result.account.server, result.account.currency, `1:${result.account.leverage}`].filter(Boolean).join(" · ")}</p>
            {result.account.equity ? <p className="num mt-1">Equity {result.account.equity}</p> : null}
          </div>
        ) : null}
        {method !== "webhook" && method !== "blockchain" && method !== "mining" && !(method === "passprop" && propStep === 1) && phase === "done" && result && !result.ok ? <p className="text-sm text-loss mt-3">{result.detail || "Connection check failed"}</p> : null}
      </fieldset>
      ) : null}
    </div>
  );
}

function named(form: FormData, fallback: string) {
  return String(form.get("alias") || "").trim().slice(0, 160) || fallback;
}

export function accountBody(form: FormData, method: ConnectionMethod, probe: Probe | null, options?: { allowSkipMetaApi?: boolean }) {
  if (method === "webhook") {
    const alias = named(form, "");
    if (!alias) throw new Error("Enter an alias for this account");
    return {
      display_name: alias,
      account_number: form.get("account_number"),
      broker: "",
      server: "",
      connection_method: method,
      currency: "USD",
      leverage: "100",
      trading_day_timezone: "UTC",
    };
  }
  if (method === "pocketoption") {
    if (!probe?.ok || !probe.account) {
      throw new Error("Sign in through the options window first");
    }
    const platform = String(form.get("options_platform") || "").trim();
    if (!OPTIONS_PLATFORMS.some((row) => row.code === platform)) {
      throw new Error("Choose which options platform to connect");
    }
    return {
      display_name: named(form, probe.account.display_name),
      account_number: probe.account.account_number,
      broker: probe.account.broker,
      server: probe.account.server,
      connection_method: method,
      currency: probe.account.currency || "USD",
      leverage: probe.account.leverage || "1",
      trading_day_timezone: "UTC",
      credentials: {
        pocket_session_id: String(form.get("pocket_session_id") || ""),
        options_platform: platform,
        active_mode: String(form.get("pocket_mode") || "").trim().toLowerCase() === "demo" ? "demo" : "real",
      },
    };
  }
  if (method === "blockchain" || method === "mining") {
    if (form.get("terms") !== "on") throw new Error("Agree to the terms before continuing.");
    const mining = method === "mining";
    return {
      display_name: named(form, mining ? "Project Coin" : "Blockchain contracts"),
      account_number: mining ? "project-coin" : "contracts",
      broker: mining ? "Project Coin" : "Blockchain",
      server: "maestro",
      connection_method: method,
      currency: mining ? "PCOIN" : "USD",
      leverage: "1",
      trading_day_timezone: "UTC",
      credentials: { accepted_terms: true },
    };
  }
  if (method === "passprop") {
    if (!probe?.ok || !probe.account) {
      throw new Error("Connect the login with MetaAPI before saving");
    }
    const firm = String(form.get("firm_name") || "").trim();
    const size = String(form.get("account_size") || "").trim();
    if (firm.length < 2) throw new Error("Enter the prop firm name");
    if (!size) throw new Error("Enter the account size");
    if (form.get("terms") !== "on") throw new Error("Agree to the $100 challenge fee before saving.");
    return {
      display_name: named(form, `${firm} · ${size}`),
      account_number: probe.account.account_number,
      broker: firm,
      server: probe.account.server,
      connection_method: method,
      currency: probe.account.currency,
      leverage: probe.account.leverage,
      trading_day_timezone: "UTC",
      credentials: {
        token_source: "default",
        firm_name: firm,
        firm_url: String(form.get("firm_url") || "").trim(),
        rules: String(form.get("rules") || ""),
        account_size: size,
        broker: String(form.get("broker") || probe.account.broker || firm),
        server: String(form.get("server") || probe.account.server),
        login: String(form.get("login") || probe.account.account_number),
        password: String(form.get("mt5_password") || ""),
        accepted_terms: true,
        platform: "mt5",
        metaapi_account_id: probe.metaapi_account_id || "",
        region: probe.region,
      },
    };
  }
  if (method === "metaapi" && options?.allowSkipMetaApi) {
    const login = String(form.get("login") || "").trim();
    const password = String(form.get("mt5_password") || "");
    const server = String(form.get("server") || "").trim();
    const broker = String(form.get("broker") || "").trim();
    if (!login && !password && !server && !broker) return null;
  }
  if (!probe?.ok || !probe.account) {
    throw new Error("Wait until the live connection check succeeds");
  }
  const credentials = method === "metaapi"
    ? {
        token_source: "default",
        broker: String(form.get("broker") || probe.account.broker),
        server: String(form.get("server") || probe.account.server),
        login: String(form.get("login") || probe.account.account_number),
        password: String(form.get("mt5_password") || ""),
        platform: "mt5",
        metaapi_account_id: probe.metaapi_account_id || "",
        region: probe.region,
      }
    : {
        login: String(form.get("login") || ""),
        password: String(form.get("mt5_password") || ""),
        server: String(form.get("server") || probe.account.server),
      };
  return {
    display_name: named(form, probe.account.display_name),
    account_number: probe.account.account_number,
    broker: probe.account.broker,
    server: probe.account.server,
    connection_method: method,
    currency: probe.account.currency,
    leverage: probe.account.leverage,
    trading_day_timezone: "UTC",
    credentials,
  };
}
