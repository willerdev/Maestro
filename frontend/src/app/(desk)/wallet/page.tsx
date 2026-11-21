"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { keepDefaultWallet, publicWalletLabel } from "@/lib/defaultWallet";

type Balance = { currency: string; available: string };
type Transfer = {
  id: string;
  currency: string;
  direction: string;
  amount: string;
  status: string;
  address: string;
  invoice_url: string;
  note: string;
  purpose?: string;
  purpose_label?: string;
  created_at: string;
};
type Home = { configured: boolean; provider: string; balances: Balance[]; transfers: Transfer[] };

function coinLabel(value: string) {
  if (!value || value === "usdttrc20" || value === "usdt") return "USDT TRC20";
  return value.toUpperCase();
}

function when(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function directionLabel(row: Transfer) {
  if (row.purpose_label) return row.purpose_label;
  if (row.note === "Wallet credit") return "Earnings";
  if (row.direction === "expense") return "Expense";
  if (row.direction === "withdraw") return "Withdraw";
  if (row.direction === "contract") return "Contract";
  if (row.direction === "mining_upgrade") return "Mining upgrade";
  return "Deposit";
}

function statusLabel(status: string) {
  if (status === "requested") return "Waiting for approval";
  if (status === "pending") return "Sending";
  if (status === "posted") return "Sent";
  if (status === "rejected") return "Rejected";
  return status;
}

function tone(status: string) {
  const value = status.toLowerCase();
  if (["finished", "confirmed", "paid", "completed", "success"].includes(value)) return "ok";
  if (["failed", "expired", "rejected", "refunded"].includes(value)) return "bad";
  if (["waiting", "pending", "confirming", "sending", "requested"].includes(value)) return "warn";
  return "idle";
}

export default function WalletPage() {
  const [home, setHome] = useState<Home | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [deposit, setDeposit] = useState<Transfer | null>(null);
  const [mode, setMode] = useState<"deposit" | "withdraw">("deposit");
  const [updated, setUpdated] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  function load() {
    setRefreshing(true);
    return keepDefaultWallet()
      .catch(() => undefined)
      .then(() => apiJson<Home>("/api/v1/assets"))
      .then((body) => {
        setHome(body);
        setError("");
        setUpdated(new Date());
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setRefreshing(false));
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 8000);
    return () => window.clearInterval(timer);
  }, []);

  async function sendDeposit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setError("");
    setMessage("");
    try {
      const row = await apiJson<Transfer>("/api/v1/assets/deposits", {
        method: "POST",
        body: JSON.stringify({ currency: form.get("currency"), amount: form.get("amount") }),
      });
      setDeposit(row);
      setMessage("Deposit created. The balance changes after the provider confirms the crypto was paid.");
      formEl.reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deposit was not created");
    }
  }

  async function sendWithdrawal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setError("");
    setMessage("");
    try {
      await apiJson("/api/v1/assets/withdrawals", {
        method: "POST",
        body: JSON.stringify({ currency: form.get("currency"), amount: form.get("amount"), address: form.get("address") }),
      });
      setMessage("Withdrawal requested. It has to be approved before it is sent.");
      formEl.reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Withdrawal was not sent");
    }
  }

  const balances = home?.balances || [];
  const lead = balances[0];
  const transfers = home?.transfers || [];

  return (
    <div className="wallet">
      <section className="wallet-hero">
        <div className="wallet-kicker">
          <span className="wallet-live">
            <i className="live-dot" />
            {refreshing ? "Refreshing" : "Live"}
            {updated ? ` · ${updated.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` : ""}
          </span>
          <span>{home?.configured ? publicWalletLabel(home.provider) : "Wallet not connected"}</span>
        </div>
        <h1>Wallet</h1>
        <div className="wallet-figure">
          <div>
            <span>{lead ? `${coinLabel(lead.currency)} available` : "USDT TRC20 available"}</span>
            <strong className="num">{lead ? lead.available : "0.00"}</strong>
          </div>
          <div className="wallet-coins">
            {balances.length === 0 ? <p className="wallet-empty">No confirmed crypto yet.</p> : null}
            {balances.slice(1).map((row, index) => (
              <article key={row.currency} className="wallet-coin" style={{ animationDelay: `${index * 60}ms` }}>
                <b>{coinLabel(row.currency)}</b>
                <em className="num">{row.available}</em>
              </article>
            ))}
          </div>
        </div>
        {home && !home.configured ? (
          <p className="text-sm mt-4">
            Default self-hosted wallet is selected. <Link className="text-accent" href="/payments">Payment settings</Link>
          </p>
        ) : null}
      </section>

      {error ? <p className="text-loss">{error}</p> : null}
      {message ? <p className="text-sm">{message}</p> : null}

      <div className="wallet-grid">
        <section className="wallet-card">
          <div className="wallet-switch" role="tablist" aria-label="Wallet action">
            <button type="button" className={mode === "deposit" ? "on" : ""} onClick={() => setMode("deposit")}>Deposit</button>
            <button type="button" className={mode === "withdraw" ? "on" : ""} onClick={() => setMode("withdraw")}>Withdraw</button>
          </div>
          {mode === "deposit" ? (
            <form className="wallet-form" onSubmit={sendDeposit}>
              <label>
                <span>Coin</span>
                <select name="currency" defaultValue="usdttrc20" required>
                  <option value="usdttrc20">USDT TRC20</option>
                  <option value="btc">BTC</option>
                  <option value="eth">ETH</option>
                  <option value="usdterc20">USDT ERC20</option>
                  <option value="usdtbsc">USDT BEP20</option>
                </select>
              </label>
              <label>
                <span>Amount</span>
                <input name="amount" type="number" min="0.00000001" step="0.00000001" placeholder="0.00" required />
              </label>
              <button className="primary" type="submit">Create deposit</button>
            </form>
          ) : (
            <form className="wallet-form" onSubmit={sendWithdrawal}>
              <label>
                <span>Coin</span>
                <select name="currency" defaultValue="usdttrc20" required>
                  <option value="usdttrc20">USDT TRC20</option>
                  <option value="btc">BTC</option>
                  <option value="eth">ETH</option>
                </select>
              </label>
              <label>
                <span>Amount</span>
                <input name="amount" type="number" min="0.00000001" step="0.00000001" placeholder="0.00" required />
              </label>
              <label>
                <span>Destination</span>
                <input name="address" placeholder="Payout address" required autoComplete="off" />
              </label>
              <button className="primary" type="submit">Request withdrawal</button>
            </form>
          )}
          {deposit && mode === "deposit" ? (
            <div className="wallet-receipt">
              <p className="text-sm">Pay <span className="num">{deposit.amount} {coinLabel(deposit.currency)}</span></p>
              <p className="text-sm mt-1"><span className={`pill ${tone(deposit.status)}`}>{deposit.status}</span></p>
              {deposit.address ? <p className="num break-all text-sm mt-2">{deposit.address}</p> : <p className="text-sm mt-2">No deposit address was returned.</p>}
              {deposit.invoice_url ? <p className="text-sm mt-2"><a className="text-accent" href={deposit.invoice_url}>Open the invoice</a></p> : null}
            </div>
          ) : null}
        </section>

        <section className="wallet-card">
          <h2>Activity</h2>
          <div className="wallet-feed">
            {transfers.length === 0 ? <p className="wallet-empty">Transfers appear here as soon as you create one.</p> : null}
            {transfers.map((row, index) => {
              const incoming = row.direction !== "withdraw" && row.direction !== "expense" && row.direction !== "contract" && row.direction !== "mining_upgrade";
              return (
                <article key={row.id} className="wallet-row" style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}>
                  <div className={`wallet-mark ${incoming ? "in" : "out"}`} aria-hidden="true">{incoming ? "↓" : "↑"}</div>
                  <div>
                    <p>{directionLabel(row)} <span className="num">{row.amount} {coinLabel(row.currency)}</span></p>
                    <p className="meta num">{row.address || when(row.created_at)}{row.note && row.note !== directionLabel(row) ? ` · ${row.note}` : ""}</p>
                  </div>
                  <div className="text-right">
                    <span className={`pill ${tone(row.status)}`}>{statusLabel(row.status)}</span>
                    <p className="meta">{when(row.created_at)}</p>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
