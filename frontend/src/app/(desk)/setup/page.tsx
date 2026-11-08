"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AccountSections, accountBody, type ConnectionMethod, type Probe } from "@/components/AccountSections";
import { AuthenticatorQr } from "@/components/AuthenticatorQr";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type Country = { name: string; dial: string };
type Language = { code: string; name: string };
type Status = {
  complete: boolean;
  country: string;
  language: string;
  phone_country_code: string;
  phone_number: string;
  admin_email: string;
  mfa_enabled: boolean;
  mfa_secret: string;
  mfa_uri: string;
  countries: Country[];
  languages: Language[];
};

type Done = {
  complete: boolean;
  connection_test: { ok: boolean; status: string; error_code?: string; detail?: string };
};

export default function SetupPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [method, setMethod] = useState<ConnectionMethod>("metaapi");
  const [probe, setProbe] = useState<Probe | null>(null);
  const [dial, setDial] = useState("");
  const [done, setDone] = useState<Done | null>(null);
  const [enabled, setEnabled] = useState<Partial<Record<ConnectionMethod, boolean>> | undefined>();

  useEffect(() => {
    apiJson<Status>("/api/v1/setup/status")
      .then((body) => {
        setStatus(body);
        setDial(body.phone_country_code || body.countries[0]?.dial || "");
      })
      .catch((err: Error) => setError(err.message));
    apiJson<{ enabled: Partial<Record<ConnectionMethod, boolean>> }>("/api/v1/system")
      .then((info) => setEnabled(info.enabled || {}))
      .catch(() => undefined);
  }, []);

  function onCountry(name: string) {
    const match = status?.countries.find((row) => row.name === name);
    if (match) setDial(match.dial);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      const account = accountBody(form, method, probe, { allowSkipMetaApi: true });
      const body = await apiJson<Done>("/api/v1/setup/complete", {
        method: "POST",
        body: JSON.stringify({
          country: form.get("country"),
          language: form.get("language"),
          phone_country_code: form.get("phone_country_code"),
          phone_number: form.get("phone_number"),
          admin_email: form.get("admin_email"),
          totp_code: String(form.get("totp_code") || ""),
          account,
          payment: { provider: "nowpayments", wallet: "hosted", sandbox: false, credentials: {} },
        }),
      });
      setDone(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup could not be saved");
    }
  }

  if (!status) {
    return <p className="text-muted">{error || "Loading setup…"}</p>;
  }

  if (status.complete || done) {
    const test = done?.connection_test;
    return (
      <div className="max-w-3xl">
        <PageTitle title="Setup complete" detail="Risk limits stay with the deterministic engine. AI remains optional." />
        {test ? (
          <p className="text-sm mb-4">
            Connection check: {test.ok ? "connected. The account details were read from the terminal." : test.detail || test.error_code || test.status}
          </p>
        ) : null}
        <button className="primary" onClick={() => router.push(method === "blockchain" ? "/contracts" : method === "mining" ? "/project-coin" : "/dashboard")}>
          {method === "blockchain" ? "Open contracts" : method === "mining" ? "Open Project Coin" : "Open the desk"}
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl">
      <PageTitle
        title="Set up Maestro"
        detail="Complete the firm profile. Connector keys wait in Settings. Add a terminal with broker login if you want one now."
      />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <fieldset className="section">
          <legend>Firm profile</legend>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="text-sm text-muted">
              Country
              <select name="country" required defaultValue="" onChange={(event) => onCountry(event.target.value)}>
                <option value="" disabled>Choose a country</option>
                {status.countries.map((row) => (
                  <option key={row.name} value={row.name}>{row.name}</option>
                ))}
              </select>
            </label>
            <label className="text-sm text-muted">
              Language
              <select name="language" required defaultValue="en">
                {status.languages.map((row) => (
                  <option key={row.code} value={row.code}>{row.name}</option>
                ))}
              </select>
            </label>
            <label className="text-sm text-muted">
              Phone country code
              <input name="phone_country_code" value={dial} onChange={(event) => setDial(event.target.value)} required />
            </label>
            <label className="text-sm text-muted">
              Phone number
              <input name="phone_number" placeholder="712345678" required />
            </label>
            <label className="text-sm text-muted sm:col-span-2">
              Your email
              <input name="admin_email" type="email" defaultValue={status.admin_email} required />
            </label>
          </div>
        </fieldset>
        <fieldset className="section">
          <legend>Google Authenticator</legend>
          <p className="text-sm text-muted mb-3">Optional. You can turn this on later in Settings.</p>
          <AuthenticatorQr uri={status.mfa_uri} secret={status.mfa_secret} />
          <input name="totp_code" inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit code, optional" />
        </fieldset>
        <fieldset className="section">
          <legend>Crypto payments</legend>
          <p className="text-sm text-muted">
            The default wallet is used. Payment keys, MetaAPI, email, Telegram, OpenAI, and DeepSeek are saved later in Settings. People who add accounts only fill broker login details.
          </p>
        </fieldset>
        <AccountSections
          method={method}
          onMethod={setMethod}
          allowWebhook={false}
          onProbe={setProbe}
          metaApiOptional
          gateTerms
          enabled={enabled}
        />
        <button className="primary" type="submit" disabled={method !== "blockchain" && method !== "mining" && method !== "metaapi" && !probe?.ok}>Save setup</button>
      </form>
    </div>
  );
}
