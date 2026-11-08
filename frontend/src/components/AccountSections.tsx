"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

export type ConnectionMethod = "metaapi" | "local_mt5" | "webhook" | "pocketoption" | "blockchain" | "mining";

export type Probe = {
  ok: boolean;
  status: string;
  error_code: string;
  detail: string;
  region: string;
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
}: {
  method: ConnectionMethod;
  onMethod: (method: ConnectionMethod) => void;
  allowWebhook: boolean;
  onProbe: (probe: Probe | null) => void;
  metaApiOptional?: boolean;
  onMetaAccountId?: (accountId: string) => void;
}) {
  const [tokenSource, setTokenSource] = useState<"default" | "own">("default");
  const [token, setToken] = useState("");
  const [accountId, setAccountId] = useState("");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [server, setServer] = useState("");
  const [phase, setPhase] = useState<"idle" | "checking" | "done">("idle");
  const [result, setResult] = useState<Probe | null>(null);
  const [pocketId, setPocketId] = useState("");
  const [pocketDetail, setPocketDetail] = useState("");

  useEffect(() => {
    onProbe(null);
    setResult(null);
    setPhase("idle");
  }, [method, onProbe]);

  useEffect(() => {
    if (!pocketId || method !== "pocketoption") return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      apiJson<{ status: string; detail: string; uid: string; demo: { balance: string; currency: string } | null; real: { balance: string; currency: string } | null }>(`/api/v1/connections/pocketoption/login/${pocketId}`)
        .then((status) => {
          if (cancelled) return;
          setPocketDetail(status.detail);
          if (!status.demo && !status.real) return;
          const parts = [
            status.demo ? `Demo ${status.demo.balance} ${status.demo.currency}` : "",
            status.real ? `Real ${status.real.balance} ${status.real.currency}` : "",
          ].filter(Boolean);
          const probe: Probe = {
            ok: true,
            status: "connected",
            error_code: "",
            detail: parts.join(" · "),
            region: "",
            account: {
              display_name: "Pocket Option",
              account_number: status.uid,
              broker: "Pocket Option",
              server: status.demo && status.real ? "demo+real" : status.demo ? "demo" : "real",
              currency: status.real?.currency || status.demo?.currency || "USD",
              leverage: "1",
              equity: status.real?.balance || status.demo?.balance,
            },
          };
          setResult(probe);
          setPhase("done");
          onProbe(probe);
        })
        .catch((err: Error) => {
          if (!cancelled) setPocketDetail(err.message);
        });
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pocketId, method, onProbe]);

  async function openPocket() {
    setPocketDetail("");
    setPhase("checking");
    onProbe(null);
    try {
      const opened = await apiJson<{ id: string; detail: string }>("/api/v1/connections/pocketoption/login", { method: "POST" });
      setPocketId(opened.id);
      setPocketDetail(opened.detail);
    } catch (err) {
      setPhase("done");
      setPocketDetail(err instanceof Error ? err.message : "The Pocket Option window did not open");
    }
  }

  useEffect(() => {
    if (method === "webhook" || method === "pocketoption" || method === "blockchain" || method === "mining") return;
    const credentials = method === "metaapi"
      ? tokenSource === "default"
        ? { token_source: "default", metaapi_account_id: accountId.trim() }
        : { token: token.trim(), metaapi_account_id: accountId.trim() }
      : { login: login.trim(), password, server: server.trim() };
    const ready = method === "metaapi"
      ? credentials.metaapi_account_id.length >= 8 && (tokenSource === "default" || token.trim().length >= 20)
      : Boolean(credentials.login && credentials.password && credentials.server);
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
  }, [method, tokenSource, token, accountId, login, password, server, onProbe]);

  return (
    <div className="flex flex-col gap-4">
      <fieldset className="section">
        <legend>1. Connection</legend>
        <div className="grid sm:grid-cols-2 gap-2">
          <label className={`choice ${method === "metaapi" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="metaapi" checked={method === "metaapi"} onChange={() => onMethod("metaapi")} />
            <span>
              <strong>MetaAPI</strong>
              <span className="block text-xs text-muted">Cloud terminal. The region is read from the token and account id.</span>
            </span>
          </label>
          <label className={`choice ${method === "local_mt5" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="local_mt5" checked={method === "local_mt5"} onChange={() => onMethod("local_mt5")} />
            <span>
              <strong>MetaTrader 5</strong>
              <span className="block text-xs text-muted">The terminal must be running and logged in on this same computer.</span>
            </span>
          </label>
          <label className={`choice ${method === "pocketoption" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="pocketoption" checked={method === "pocketoption"} onChange={() => onMethod("pocketoption")} />
            <span>
              <strong>Pocket Option</strong>
              <span className="block text-xs text-muted">A login window opens. Sign in there. Maestro reads the demo and real balances.</span>
            </span>
          </label>
          <label className={`choice ${method === "blockchain" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="blockchain" checked={method === "blockchain"} onChange={() => onMethod("blockchain")} />
            <span>
              <strong>Blockchain contracts</strong>
              <span className="block text-xs text-muted">A separate page reads a public wallet and one contract. No private key.</span>
            </span>
          </label>
          <label className={`choice ${method === "mining" ? "on" : ""}`}>
            <input type="radio" name="connection_method" value="mining" checked={method === "mining"} onChange={() => onMethod("mining")} />
            <span>
              <strong>Mining</strong>
              <span className="block text-xs text-muted">A separate page reads a mining payout address. No private key.</span>
            </span>
          </label>
          {allowWebhook ? (
            <label className={`choice ${method === "webhook" ? "on" : ""}`}>
              <input type="radio" name="connection_method" value="webhook" checked={method === "webhook"} onChange={() => onMethod("webhook")} />
              <span>
                <strong>Webhook</strong>
                <span className="block text-xs text-muted">An Expert Advisor posts events. Credentials are shown once after save.</span>
              </span>
            </label>
          ) : null}
        </div>
      </fieldset>
      <fieldset className="section">
        <legend>2. Credentials</legend>
        {method === "metaapi" ? (
          <div className="grid gap-3">
            <input type="hidden" name="token_source" value={tokenSource} />
            <div className="grid gap-2">
              <label className={`choice ${tokenSource === "default" ? "on" : ""}`}>
                <input type="radio" name="metaapi_token_choice" checked={tokenSource === "default"} onChange={() => setTokenSource("default")} />
                <span>
                  <strong>Default MetaAPI token</strong>
                  <span className="block text-sm text-muted">Maestro uses the server token. It is not shown here. Enter the account id for the terminal you want to connect.</span>
                </span>
              </label>
              <label className={`choice ${tokenSource === "own" ? "on" : ""}`}>
                <input type="radio" name="metaapi_token_choice" checked={tokenSource === "own"} onChange={() => setTokenSource("own")} />
                <span>
                  <strong>Use my token</strong>
                  <span className="block text-sm text-muted">Enter the MetaAPI token from your own account.</span>
                </span>
              </label>
            </div>
            {tokenSource === "own" ? (
              <input name="token" type="password" placeholder="MetaAPI token" value={token} onChange={(event) => setToken(event.target.value)} required autoComplete="off" />
            ) : null}
            <input
              name="metaapi_account_id"
              placeholder={metaApiOptional ? "MetaAPI account id, optional" : "MetaAPI account id"}
              value={accountId}
              onChange={(event) => {
                setAccountId(event.target.value);
                onMetaAccountId?.(event.target.value);
              }}
              required={!metaApiOptional}
            />
            {metaApiOptional ? <p className="text-sm text-muted">Leave the account id empty and add it later in Settings.</p> : null}
          </div>
        ) : null}
        {method === "local_mt5" ? (
          <div className="grid gap-3">
            <p className="text-sm text-muted">Open MetaTrader 5 on this computer before continuing. Login, password, and server are used only for the live check. Name, account number, broker, currency, and leverage are read from the terminal.</p>
            <input name="login" placeholder="MT5 login" value={login} onChange={(event) => setLogin(event.target.value)} required />
            <input name="mt5_password" type="password" placeholder="MT5 password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="new-password" />
            <input name="server" placeholder="Server" value={server} onChange={(event) => setServer(event.target.value)} required />
          </div>
        ) : null}
        {method === "pocketoption" ? (
          <div className="grid gap-3">
            <input type="hidden" name="pocket_session_id" value={pocketId} />
            <p className="text-sm text-muted">Sign in yourself in the Pocket Option window. Switch between Demo and Real so both balances are read. The session token stays on the server and is not shown here.</p>
            <button className="primary" type="button" onClick={openPocket}>Open Pocket Option login</button>
            {pocketDetail ? <p className="text-sm">{pocketDetail}</p> : null}
            {result?.ok ? <p className="text-sm text-profit">{result.detail}</p> : null}
          </div>
        ) : null}
        {method === "blockchain" ? (
          <p className="text-sm text-muted">Contracts have their own page. <Link className="text-accent" href="/contracts">Open contracts</Link>.</p>
        ) : null}
        {method === "mining" ? (
          <p className="text-sm text-muted">Mining has its own page. <Link className="text-accent" href="/mining">Open mining</Link>.</p>
        ) : null}
        {method === "webhook" ? (
          <div className="grid sm:grid-cols-2 gap-3">
            <p className="text-sm text-muted sm:col-span-2">A webhook has no terminal to read, so the name and account number are entered here. The path, API key, and signing secret are shown once after save.</p>
            <input name="display_name" placeholder="Display name" required />
            <input name="account_number" placeholder="Account number" required />
          </div>
        ) : null}
        {method !== "webhook" && method !== "blockchain" && method !== "mining" && phase === "checking" ? <p className="text-sm text-muted mt-3">Checking the live connection…</p> : null}
        {method !== "webhook" && method !== "blockchain" && method !== "mining" && phase === "done" && result?.ok && result.account ? (
          <div className="mt-3 text-sm">
            <p className="text-profit">Connected{result.region ? ` · ${result.region}` : ""}</p>
            <p className="mt-1">{result.account.display_name} · {result.account.account_number}</p>
            <p className="text-muted">{[result.account.broker, result.account.server, result.account.currency, `1:${result.account.leverage}`].filter(Boolean).join(" · ")}</p>
            {result.account.equity ? <p className="num mt-1">Equity {result.account.equity}</p> : null}
          </div>
        ) : null}
        {method !== "webhook" && method !== "blockchain" && method !== "mining" && phase === "done" && result && !result.ok ? <p className="text-sm text-loss mt-3">{result.detail || "Connection check failed"}</p> : null}
      </fieldset>
    </div>
  );
}

export function accountBody(form: FormData, method: ConnectionMethod, probe: Probe | null, options?: { allowSkipMetaApi?: boolean }) {
  if (method === "webhook") {
    return {
      display_name: form.get("display_name"),
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
      throw new Error("Sign in through the Pocket Option window first");
    }
    return {
      display_name: probe.account.display_name,
      account_number: probe.account.account_number,
      broker: probe.account.broker,
      server: probe.account.server,
      connection_method: method,
      currency: probe.account.currency || "USD",
      leverage: probe.account.leverage || "1",
      trading_day_timezone: "UTC",
      credentials: { pocket_session_id: String(form.get("pocket_session_id") || "") },
    };
  }
  if (method === "blockchain" || method === "mining") {
    return null;
  }
  if (method === "metaapi" && options?.allowSkipMetaApi && !String(form.get("metaapi_account_id") || "").trim()) {
    return null;
  }
  if (!probe?.ok || !probe.account) {
    throw new Error("Wait until the live connection check succeeds");
  }
  const credentials = method === "metaapi"
    ? form.get("token_source") === "default"
      ? {
          token_source: "default",
          metaapi_account_id: String(form.get("metaapi_account_id") || ""),
          region: probe.region,
        }
      : {
          token: String(form.get("token") || ""),
          metaapi_account_id: String(form.get("metaapi_account_id") || ""),
          region: probe.region,
        }
    : {
        login: String(form.get("login") || ""),
        password: String(form.get("mt5_password") || ""),
        server: String(form.get("server") || probe.account.server),
      };
  return {
    display_name: probe.account.display_name,
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
