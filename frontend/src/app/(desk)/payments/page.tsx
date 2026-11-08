"use client";

import { FormEvent, useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";
import { ExtraWallets } from "@/components/ExtraWallets";
import { keepDefaultWallet, publicWalletLabel } from "@/lib/defaultWallet";

type Provider = { configured: boolean; provider: string; wallet: string; sandbox: boolean; enabled: boolean; callback_url: string; detail?: string };
type Payment = {
  id: string;
  provider: string;
  purpose: string;
  price_amount: string;
  price_currency: string;
  pay_currency: string;
  pay_amount: string | null;
  pay_address: string;
  invoice_url: string;
  provider_status: string;
  status: string;
  created_at: string;
};

export default function PaymentsPage() {
  const [provider, setProvider] = useState<Provider | null>(null);
  const [rows, setRows] = useState<Payment[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Payment | null>(null);

  function load() {
    return keepDefaultWallet()
      .then((config) => setProvider(config as Provider))
      .then(() => apiJson<Payment[]>("/api/v1/payments").then(setRows).catch(() => setRows([])));
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  async function requestPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    setCreated(null);
    try {
      const body = await apiJson<Payment>("/api/v1/payments", {
        method: "POST",
        body: JSON.stringify({
          price_amount: form.get("price_amount"),
          price_currency: form.get("price_currency"),
          pay_currency: form.get("pay_currency"),
          purpose: form.get("purpose"),
          description: form.get("description"),
        }),
      });
      setCreated(body);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment request failed");
    }
  }

  return (
    <div className="max-w-5xl">
      <PageTitle
        title="Crypto payments"
        detail="The default self-hosted wallet stays the payment wallet. Ledger, Binance, Bybit, and OKX are extra public-address connections."
      />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {message ? <p className="text-sm mb-3">{message}</p> : null}
      <p className="text-sm text-muted mb-4">
        The default wallet is set in Settings. You can still attach extra public wallets below and request a payment once the default wallet is ready.
      </p>
      <ExtraWallets />
      <form className="grid md:grid-cols-3 gap-3 max-w-4xl mb-8" onSubmit={requestPayment}>
        <input name="price_amount" type="number" min="0.01" step="0.01" placeholder="Amount" required />
        <input name="price_currency" defaultValue="USD" placeholder="Price currency" required />
        <input name="pay_currency" defaultValue="usdttrc20" placeholder="USDT TRC20" />
        <select name="purpose" defaultValue="deposit">
          <option value="deposit">Deposit</option>
          <option value="subscription">Subscription</option>
          <option value="other">Other</option>
        </select>
        <input name="description" placeholder="Description" />
        <button className="primary" type="submit" disabled={!provider?.configured}>Request payment</button>
      </form>
      {created ? (
        <p className="text-sm mb-4">
          Status {created.status}{created.provider_status ? ` · ${created.provider_status}` : ""}.
          {created.invoice_url ? <> <a className="text-accent" href={created.invoice_url}>Open the invoice</a></> : null}
          {created.pay_address ? <> Address: <span className="num">{created.pay_address}</span></> : null}
        </p>
      ) : null}
      <table className="w-full text-sm bg-panel border border-line">
        <thead className="text-left text-muted">
          <tr>
            <th className="px-3 py-2">When</th>
            <th>Purpose</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Provider</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-line">
              <td className="px-3 py-2">{row.created_at.slice(0, 16).replace("T", " ")}</td>
              <td>{row.purpose}</td>
              <td className="num">{row.price_amount} {row.price_currency}</td>
              <td>{row.status}</td>
              <td>{row.provider_status || publicWalletLabel(row.provider)}</td>
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr><td className="px-3 py-3 text-muted" colSpan={5}>No payment requests yet.</td></tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
