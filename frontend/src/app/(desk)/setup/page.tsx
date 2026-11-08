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
  const [wallet, setWallet] = useState<"hosted" | "external">("hosted");
  const [payProvider, setPayProvider] = useState("nowpayments");
  const [apiUrl, setApiUrl] = useState("https://api.nowpayments.io/v1");
  const [metaAccountId, setMetaAccountId] = useState("");

  useEffect(() => {
    apiJson<Status>("/api/v1/setup/status")
      .then((body) => {
        setStatus(body);
        setDial(body.phone_country_code || body.countries[0]?.dial || "");
      })
      .catch((err: Error) => setError(err.message));
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
          payment: wallet === "hosted"
            ? { provider: "nowpayments", wallet: "hosted", sandbox: false, credentials: {} }
            : {
                provider: payProvider,
                wallet: "external",
                sandbox: form.get("sandbox") === "on",
                credentials: {
                  api_key: String(form.get("pay_api_key") || ""),
                  api_url: String(form.get("api_url") || ""),
                  ipn_secret: String(form.get("ipn_secret") || ""),
                  payout_email: String(form.get("payout_email") || ""),
                  payout_password: String(form.get("payout_password") || ""),
                  merchant_id: String(form.get("merchant_id") || ""),
                },
              },
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
        <button className="primary" onClick={() => router.push("/dashboard")}>Open the desk</button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl">
      <PageTitle
        title="Set up Maestro"
        detail="Complete the firm profile and choose a wallet. The MetaAPI account id and Google Authenticator can wait until Settings."
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
              Admin email
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
          <p className="text-sm text-muted mb-3">
            Choose the default self-hosted wallet, or connect an external wallet. A payment is marked paid only after the provider confirms it.
          </p>
          <div className="grid gap-2 mb-3">
            <label className={`choice ${wallet === "hosted" ? "on" : ""}`}>
              <input type="radio" name="wallet" checked={wallet === "hosted"} onChange={() => setWallet("hosted")} />
              <span>
                <strong>Default self-hosted wallet</strong>
                <span className="block text-sm text-muted">Maestro uses its own wallet. The payment keys stay on the server and are not shown here.</span>
              </span>
            </label>
            <label className={`choice ${wallet === "external" ? "on" : ""}`}>
              <input type="radio" name="wallet" checked={wallet === "external"} onChange={() => setWallet("external")} />
              <span>
                <strong>External wallet</strong>
                <span className="block text-sm text-muted">Connect your own NOWPayments or Cryptomus account.</span>
              </span>
            </label>
          </div>
          {wallet === "external" ? (
            <>
              <p className="text-sm mb-3 border border-line rounded-lg px-3 py-3">
                External wallets are risky. The provider holds the payment, and fees may be applied.
              </p>
              <div className="grid gap-2 mb-3">
                <label className={`choice ${payProvider === "nowpayments" ? "on" : ""}`}>
                  <input type="radio" name="pay_provider" checked={payProvider === "nowpayments"} onChange={() => setPayProvider("nowpayments")} />
                  <span>
                    <strong>NOWPayments</strong>
                    <span className="block text-sm text-muted">API key, API URL, payout email, payout password, and IPN secret. The email must match the NOWPayments dashboard, including capitals.</span>
                  </span>
                </label>
                <label className={`choice ${payProvider === "cryptomus" ? "on" : ""}`}>
                  <input type="radio" name="pay_provider" checked={payProvider === "cryptomus"} onChange={() => setPayProvider("cryptomus")} />
                  <span>
                    <strong>Cryptomus</strong>
                    <span className="block text-sm text-muted">Merchant id and payment API key.</span>
                  </span>
                </label>
              </div>
              <div className="grid sm:grid-cols-2 gap-3">
                {payProvider === "cryptomus" ? (
                  <label className="text-sm text-muted">
                    Merchant id
                    <input name="merchant_id" required autoComplete="off" />
                  </label>
                ) : null}
                <label className="text-sm text-muted">
                  API key
                  <input name="pay_api_key" type="password" required autoComplete="off" />
                </label>
                {payProvider === "nowpayments" ? (
                  <>
                    <label className="text-sm text-muted sm:col-span-2">
                      API URL
                      <input name="api_url" type="url" required value={apiUrl} onChange={(event) => setApiUrl(event.target.value)} autoComplete="off" />
                    </label>
                    <label className="text-sm text-muted">
                      Payout email
                      <input name="payout_email" type="text" required autoComplete="username" placeholder="Same email as the NOWPayments dashboard" />
                    </label>
                    <label className="text-sm text-muted">
                      Payout password
                      <input name="payout_password" type="password" required autoComplete="new-password" />
                    </label>
                    <label className="text-sm text-muted">
                      IPN secret
                      <input name="ipn_secret" type="password" required autoComplete="off" />
                    </label>
                  </>
                ) : null}
              </div>
              {payProvider === "nowpayments" ? (
                <label className="text-sm flex gap-2 items-center mt-3">
                  <input
                    className="w-auto"
                    type="checkbox"
                    name="sandbox"
                    onChange={(event) => setApiUrl(event.target.checked ? "https://api-sandbox.nowpayments.io/v1" : "https://api.nowpayments.io/v1")}
                  /> Use the NOWPayments sandbox host in the API URL
                </label>
              ) : null}
            </>
          ) : null}
        </fieldset>
        <AccountSections
          method={method}
          onMethod={setMethod}
          allowWebhook={false}
          onProbe={setProbe}
          metaApiOptional
          onMetaAccountId={setMetaAccountId}
        />
        <button className="primary" type="submit" disabled={!(method === "metaapi" && metaAccountId.trim() === "") && method !== "blockchain" && method !== "mining" && !probe?.ok}>Save setup</button>
      </form>
    </div>
  );
}
