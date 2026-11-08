"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Balance = { currency: string; available: string };
type Transfer = { id: string; currency: string; direction: string; amount: string; status: string; address: string; invoice_url: string; note: string; created_at: string };
type Home = { configured: boolean; provider: string; balances: Balance[]; transfers: Transfer[] };

export function AssetPanel() {
  const [home, setHome] = useState<Home | null>(null);
  const [message, setMessage] = useState("");
  const [deposit, setDeposit] = useState<Transfer | null>(null);

  function load() {
    apiJson<Home>("/api/v1/assets")
      .then((body) => {
        setHome(body);
        setMessage("");
      })
      .catch((error: Error) => setMessage(error.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function sendDeposit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const row = await apiJson<Transfer>("/api/v1/assets/deposits", {
        method: "POST",
        body: JSON.stringify({ currency: form.get("currency"), amount: form.get("amount") }),
      });
      setDeposit(row);
      setMessage("Deposit created. The balance changes after the crypto is confirmed as paid.");
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Deposit was not created");
    }
  }

  async function sendWithdrawal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiJson("/api/v1/assets/withdrawals", {
        method: "POST",
        body: JSON.stringify({ currency: form.get("currency"), amount: form.get("amount"), address: form.get("address") }),
      });
      setMessage("Withdrawal requested. It has to be approved before it is sent.");
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Withdrawal was not sent");
    }
  }

  return (
    <section>
      <h2 className="text-lg font-semibold mb-1">Assets</h2>
      <p className="text-sm text-muted mb-4">Deposit and withdraw crypto through the default wallet. Confirmed crypto is available to withdraw. Broker equity and fund units stay unchanged.</p>
      {message ? <p className="text-sm mb-3">{message}</p> : null}
      {home && !home.configured ? <p className="text-sm mb-4">The default wallet is not ready yet. Open Payments to connect it.</p> : null}
      <div className="flex flex-col gap-2 mb-4">
        {(home?.balances || []).length === 0 ? <p className="text-sm text-muted">No confirmed crypto yet.</p> : null}
        {(home?.balances || []).map((row) => (
          <article key={row.currency} className="border border-line bg-panel rounded p-3">
            <div className="text-sm text-muted">{row.currency}</div>
            <div className="num text-lg">{row.available}</div>
          </article>
        ))}
      </div>
      <form className="grid md:grid-cols-3 gap-2 mb-3" onSubmit={sendDeposit}>
        <select name="currency" defaultValue="usdttrc20" required>
          <option value="usdttrc20">USDT TRC20</option>
          <option value="btc">BTC</option>
          <option value="eth">ETH</option>
        </select>
        <input name="amount" type="number" min="0.00000001" step="0.00000001" placeholder="Amount" required />
        <button className="primary" type="submit">Deposit</button>
      </form>
      {deposit ? (
        <p className="text-sm mb-4">
          Pay {deposit.amount} {deposit.currency}. Status {deposit.status}.
          {deposit.address ? <> Address <span className="num break-all">{deposit.address}</span>.</> : null}
          {deposit.invoice_url ? <> <a href={deposit.invoice_url}>Open the invoice</a>.</> : null}
        </p>
      ) : null}
      <form className="grid md:grid-cols-4 gap-2 mb-6" onSubmit={sendWithdrawal}>
        <input name="currency" placeholder="Ticker" required />
        <input name="amount" type="number" min="0.00000001" step="0.00000001" placeholder="Amount" required />
        <input name="address" placeholder="Destination wallet address" required />
        <button className="primary" type="submit">Request withdrawal</button>
      </form>
      <ul className="text-sm">
        {(home?.transfers || []).map((row) => (
          <li key={row.id} className="border-b border-line py-2">
            {row.direction} {row.amount} {row.currency} · {row.status}
            {row.address ? <span className="num"> · {row.address}</span> : null}
            {row.note ? ` · ${row.note}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
