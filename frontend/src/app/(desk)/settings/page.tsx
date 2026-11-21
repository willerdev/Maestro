"use client";

import { FormEvent, useEffect, useState } from "react";
import { AuthenticatorQr } from "@/components/AuthenticatorQr";
import { PageTitle } from "@/components/Shell";
import { apiJson, isSystemAdmin, type User } from "@/lib/api";

type Connectors = {
  metaapi_token_set: boolean;
  wallet_key_set: boolean;
  email: { configured: boolean; from: string };
  telegram_bot_set: boolean;
  telegram_app_id: string;
  openai_set: boolean;
  deepseek_set: boolean;
};
type AccountType = { code: string; label: string; enabled: boolean; limit: number };

export default function SettingsPage() {
  const [me, setMe] = useState<User | null>(null);
  const [message, setMessage] = useState("");
  const [key, setKey] = useState("");
  const [keys, setKeys] = useState<{ id: string; name: string; prefix: string; revoked: boolean }[]>([]);
  const [provider, setProvider] = useState("deepseek");
  const [apis, setApis] = useState<{ name: string; connected: boolean }[]>([]);
  const [emailFrom, setEmailFrom] = useState("");
  const [emailReady, setEmailReady] = useState(false);
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [mfaUri, setMfaUri] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  const [connectors, setConnectors] = useState<Connectors | null>(null);
  const [telegramAppId, setTelegramAppId] = useState("");
  const [accountTypes, setAccountTypes] = useState<AccountType[]>([]);
  const hostedKeyOnly = provider === "deepseek" || provider === "openai";
  const admin = isSystemAdmin(me?.roles);

  function loadApis() {
    apiJson<{ name: string; connected: boolean }[]>("/api/v1/integrations")
      .then(setApis)
      .catch(() => undefined);
  }

  useEffect(() => {
    apiJson<User>("/api/v1/auth/me").then(setMe).catch(() => undefined);
    apiJson<{ mfa_enabled: boolean; mfa_uri: string; mfa_secret: string }>("/api/v1/setup/status")
      .then((status) => {
        setMfaEnabled(status.mfa_enabled);
        setMfaUri(status.mfa_uri || "");
        setMfaSecret(status.mfa_secret || "");
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!admin) return;
    loadApis();
    apiJson<{ id: string; name: string; prefix: string; revoked: boolean }[]>("/api/v1/api-keys")
      .then(setKeys)
      .catch(() => undefined);
    apiJson<{ configured: boolean; from: string }>("/api/v1/email")
      .then((email) => {
        setEmailFrom(email.from || "");
        setEmailReady(email.configured);
      })
      .catch(() => undefined);
    apiJson<Connectors>("/api/v1/system/connectors")
      .then((body) => {
        setConnectors(body);
        setTelegramAppId(body.telegram_app_id || "");
        setEmailFrom(body.email?.from || "");
        setEmailReady(Boolean(body.email?.configured));
      })
      .catch(() => undefined);
    apiJson<{ app_id: string }>("/api/v1/telegram")
      .then((body) => setTelegramAppId(body.app_id || ""))
      .catch(() => undefined);
    apiJson<{ types: AccountType[] }>("/api/v1/system/account-types")
      .then((body) => setAccountTypes(body.types || []))
      .catch(() => undefined);
  }, [admin]);

  async function saveAi(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      provider,
      enabled: form.get("enabled") === "on",
      api_key: String(form.get("api_key") || ""),
    };
    if (!hostedKeyOnly) {
      body.model = form.get("model");
      body.base_url = form.get("base_url");
      body.temperature = form.get("temperature");
      body.max_tokens = Number(form.get("max_tokens"));
    }
    await apiJson("/api/v1/ai/config", { method: "PUT", body: JSON.stringify(body) });
    loadApis();
    event.currentTarget.reset();
    const saved = provider === "openai"
      ? "OpenAI saved. Users never see this key."
      : provider === "deepseek"
        ? "DeepSeek saved. Users never see this key."
        : "AI provider saved. Analysis cannot change risk limits.";
    setMessage(saved);
  }

  async function saveEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const saved = await apiJson<{ configured: boolean; from: string }>("/api/v1/email", {
        method: "PUT",
        body: JSON.stringify({
          api_key: String(form.get("api_key") || ""),
          from_address: String(form.get("from_address") || ""),
        }),
      });
      setEmailFrom(saved.from || "");
      setEmailReady(saved.configured);
      loadApis();
      event.currentTarget.reset();
      setMessage("Resend saved. Users never see this key.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Email settings were not saved");
    }
  }

  async function sendTest() {
    try {
      const sent = await apiJson<{ to: string }>("/api/v1/email/test", { method: "POST" });
      setMessage(`Test sent to ${sent.to}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Test email was not sent");
    }
  }

  async function saveAuthenticator(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiJson("/api/v1/setup/authenticator", {
        method: "POST",
        body: JSON.stringify({ totp_code: String(form.get("totp_code") || "") }),
      });
      setMfaEnabled(true);
      setMessage("Google Authenticator is on. The next sign-in will ask for a code.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Google Authenticator was not enabled");
    }
  }

  async function saveAccountTypes(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const body = await apiJson<{ types: AccountType[] }>("/api/v1/system/account-types", {
        method: "PUT",
        body: JSON.stringify({
          enabled: Object.fromEntries(accountTypes.map((row) => [row.code, row.enabled])),
        }),
      });
      setAccountTypes(body.types || []);
      setMessage("Account types saved. Users can only add the types that are on.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Account types were not saved");
    }
  }

  async function saveConnectors(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const body = await apiJson<Connectors>("/api/v1/system/connectors", {
        method: "PUT",
        body: JSON.stringify({
          metaapi_token: String(form.get("metaapi_token") || ""),
          wallet: {
            api_key: String(form.get("wallet_api_key") || ""),
            ipn_secret: String(form.get("wallet_ipn_secret") || ""),
            payout_email: String(form.get("wallet_payout_email") || ""),
            payout_password: String(form.get("wallet_payout_password") || ""),
          },
        }),
      });
      setConnectors(body);
      event.currentTarget.reset();
      setMessage("Connector keys saved. Users only fill broker login, server, and password when they add an account.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Connector keys were not saved");
    }
  }

  async function saveTelegram(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const body = await apiJson<{ app_id: string; bot_token_set: boolean }>("/api/v1/telegram", {
        method: "PUT",
        body: JSON.stringify({
          app_id: form.get("app_id"),
          api_hash: form.get("api_hash"),
          bot_token: form.get("bot_token"),
        }),
      });
      setTelegramAppId(body.app_id || "");
      loadApis();
      event.currentTarget.reset();
      setMessage("Telegram app saved. Users only sign in with their phone on the Telegram page.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Telegram was not saved");
    }
  }

  async function sendTelegramTest() {
    try {
      const body = await apiJson<{ sent: boolean; bot: string }>("/api/v1/telegram/test", {
        method: "POST",
        body: JSON.stringify({ bot_token: "" }),
      });
      setMessage(body.bot ? `Test sent from @${body.bot}. Check Telegram.` : "Test sent. Check Telegram.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Telegram test was not sent");
    }
  }

  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = await apiJson<{ api_key: string }>("/api/v1/api-keys", {
      method: "POST",
      body: JSON.stringify({ name: form.get("name"), scopes: ["accounts.read"] }),
    });
    setKey(body.api_key);
    const rows = await apiJson<{ id: string; name: string; prefix: string; revoked: boolean }[]>("/api/v1/api-keys");
    setKeys(rows);
  }

  return (
    <div className="grid xl:grid-cols-2 gap-8 max-w-5xl">
      {admin ? (
        <>
          <section className="xl:col-span-2 max-w-xl">
            <PageTitle title="Account types" detail="Turn a type off to hide it when someone adds an account. Existing accounts stay on the list." />
            <form className="flex flex-col gap-3" onSubmit={saveAccountTypes}>
              <ul className="border border-line rounded bg-panel">
                {accountTypes.map((row) => (
                  <li key={row.code} className="flex items-center justify-between gap-3 px-3 py-2 border-b border-line last:border-b-0">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        className="w-auto"
                        type="checkbox"
                        checked={row.enabled}
                        onChange={(event) => setAccountTypes((current) => current.map((item) => item.code === row.code ? { ...item, enabled: event.target.checked } : item))}
                      />
                      <span>{row.label}</span>
                    </label>
                    <span className="text-xs text-muted">{row.enabled ? (row.limit === 1 ? "Available" : `Up to ${row.limit}`) : "Off"}</span>
                  </li>
                ))}
              </ul>
              <button className="primary w-fit" type="submit">Save account types</button>
            </form>
          </section>
          <section className="xl:col-span-2 max-w-xl">
            <PageTitle title="Connected APIs" detail="Each saved key is checked with its provider. Other logins never see these keys." />
            <ul className="border border-line rounded bg-panel">
              {apis.map((api) => (
                <li key={api.name} className="flex items-center justify-between gap-3 px-3 py-2 border-b border-line last:border-b-0">
                  <span>{api.name}</span>
                  <span className={api.connected ? "text-profit" : "text-loss"}>{api.connected ? "Connected" : "Not connected"}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <PageTitle title="AI settings" detail="DeepSeek and OpenAI keys stay on this settings page. Other logins do not paste keys." />
            <form className="flex flex-col gap-3" autoComplete="off" onSubmit={saveAi}>
              <select name="provider" value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option>
                <option value="gemini">Gemini</option>
                <option value="anthropic">Anthropic</option>
                <option value="local">Local OpenAI-compatible</option>
              </select>
              {provider === "deepseek" ? (
                <p className="text-sm">DeepSeek gives you one API key. The desk uses deepseek-chat on the official host.</p>
              ) : provider === "openai" ? (
                <p className="text-sm">OpenAI gives you one API key. The desk uses it on the official host to read images on Telegram and to create images it sends back.</p>
              ) : (
                <>
                  <input name="model" autoComplete="off" placeholder="Model" />
                  <input name="base_url" autoComplete="off" placeholder="Base URL for a local or custom endpoint" />
                  <input name="temperature" type="number" step="0.1" defaultValue="0.2" />
                  <input name="max_tokens" type="number" defaultValue="800" />
                </>
              )}
              <input name="api_key" type="password" autoComplete="off" placeholder={provider === "openai" ? "OpenAI API key" : hostedKeyOnly ? "DeepSeek API key" : "API key"} />
              {provider === "openai" ? null : (
                <label className="text-sm flex gap-2 items-center"><input className="w-auto" type="checkbox" name="enabled" defaultChecked={hostedKeyOnly} /> Enable AI</label>
              )}
              <button className="primary" type="submit">Save provider</button>
            </form>
          </section>
          <section>
            <PageTitle title="Email" detail="Resend sends password resets and alert emails. The from address must use a domain you verified in Resend." />
            <form className="flex flex-col gap-3" autoComplete="off" onSubmit={saveEmail}>
              <input name="from_address" autoComplete="off" placeholder="Maestro <alerts@yourdomain.com>" value={emailFrom} onChange={(event) => setEmailFrom(event.target.value)} />
              <input name="api_key" type="password" autoComplete="off" placeholder={emailReady ? "Key saved. Paste a new one only to replace it." : "Resend API key"} />
              <button className="primary" type="submit">Save email</button>
            </form>
            <button className="ghost mt-3" type="button" onClick={sendTest}>Send test to my email</button>
          </section>
          <section>
            <PageTitle title="MetaAPI and default wallet" detail="Accounts are added with broker, server, login id, and password only. Deposits use USDT TRC20 on the wallet saved here." />
            <form className="flex flex-col gap-3" autoComplete="off" onSubmit={saveConnectors}>
              <input name="metaapi_token" type="password" autoComplete="off" placeholder={connectors?.metaapi_token_set ? "MetaAPI token saved. Paste a new one only to replace it." : "MetaAPI token"} />
              <input name="wallet_api_key" type="password" autoComplete="off" placeholder={connectors?.wallet_key_set ? "Default wallet key saved. Paste a new one only to replace it." : "Default wallet API key"} />
              <input name="wallet_ipn_secret" type="password" autoComplete="off" placeholder="IPN secret, optional for deposits" />
              <input name="wallet_payout_email" autoComplete="off" placeholder="Payout email" />
              <input name="wallet_payout_password" type="password" autoComplete="off" placeholder="Payout password" />
              <button className="primary" type="submit">Save connector keys</button>
            </form>
          </section>
          <section>
            <PageTitle title="Telegram app" detail="App ID and API hash come from my.telegram.org. The bot token comes from BotFather. Users only sign in with their phone." />
            <form className="flex flex-col gap-3" autoComplete="off" onSubmit={saveTelegram}>
              <input name="app_id" value={telegramAppId} onChange={(event) => setTelegramAppId(event.target.value)} autoComplete="off" placeholder="App ID" />
              <input name="api_hash" type="password" autoComplete="off" placeholder={connectors?.telegram_bot_set ? "Leave blank to keep the saved hash" : "App API hash"} />
              <input name="bot_token" type="password" autoComplete="off" placeholder={connectors?.telegram_bot_set ? "Leave blank to keep the saved token" : "Bot token"} />
              <div className="flex gap-2">
                <button className="primary" type="submit">Save Telegram</button>
                <button className="ghost" type="button" onClick={sendTelegramTest}>Send test</button>
              </div>
            </form>
          </section>
          <section>
            <PageTitle title="API keys" detail="The raw key is shown once." />
            <form className="flex flex-col gap-3" onSubmit={createKey}>
              <input name="name" placeholder="Key name" required />
              <button className="primary" type="submit">Create key</button>
            </form>
            {key ? <p className="num break-all mt-3 text-sm">{key}</p> : null}
            <ul className="text-sm mt-3">
              {keys.map((row) => (
                <li key={row.id} className="border-b border-line py-2">{row.name} · {row.prefix} · {row.revoked ? "revoked" : "active"}</li>
              ))}
            </ul>
          </section>
        </>
      ) : (
        <section className="xl:col-span-2">
          <PageTitle title="Settings" detail="Connector keys are set in desk Settings. Here you only turn on Google Authenticator for your own login." />
        </section>
      )}
      <section className="xl:col-span-2 max-w-xl">
        <PageTitle title="Google Authenticator" detail="Optional. Turn it on for your own login." />
        {mfaEnabled ? <p className="text-sm">Google Authenticator is on.</p> : (
          <form className="flex flex-col gap-3" onSubmit={saveAuthenticator}>
            <AuthenticatorQr uri={mfaUri} secret={mfaSecret} />
            <input name="totp_code" inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit code" required />
            <button className="primary" type="submit">Turn on Google Authenticator</button>
          </form>
        )}
      </section>
      {message ? <p className="text-sm xl:col-span-2">{message}</p> : null}
    </div>
  );
}
