"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type Wallet = { id: string; label: string; address: string; owner: string; currency: string; available: string };
type Move = { id: string; label: string; address: string; owner: string; direction: string; amount: string; currency: string; status: string };
type Fund = {
  id: string;
  name: string;
  base_currency: string;
  aum: string;
  unit_price: string;
  units_outstanding: string;
  publishable: boolean;
  wallets?: Wallet[];
  movements?: Move[];
};

type LedgerAccount = { code: string; name: string; kind: string; balance: string; debit: string; credit: string };
type Ledger = { balanced: boolean; accounts: LedgerAccount[]; journals: { id: string; memo: string; status: string; created_at: string }[] };

export default function FundsPage() {
  const [rows, setRows] = useState<Fund[]>([]);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [message, setMessage] = useState("");

  function load() {
    apiJson<Fund[]>("/api/v1/funds").then(setRows).catch((error: Error) => setMessage(error.message));
    apiJson<Ledger>("/api/v1/ledger").then(setLedger).catch(() => setLedger(null));
  }

  useEffect(() => {
    load();
  }, []);

  async function saveWallet(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const fundId = String(form.get("fund_id") || "");
    try {
      await apiJson(`/api/v1/funds/${fundId}/wallets`, {
        method: "POST",
        body: JSON.stringify({ label: form.get("label"), address: form.get("address") }),
      });
      setMessage("Wallet address saved.");
      event.currentTarget.reset();
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Wallet was not saved");
    }
  }

  async function moveWallet(event: FormEvent<HTMLFormElement>, fundId: string, walletId: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiJson(`/api/v1/funds/${fundId}/wallets/${walletId}/moves`, {
        method: "POST",
        body: JSON.stringify({ direction: form.get("direction"), amount: form.get("amount"), note: "" }),
      });
      setMessage("");
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Wallet movement was not recorded");
    }
  }

  async function settle(fundId: string, movementId: string, decision: string) {
    try {
      await apiJson(`/api/v1/funds/${fundId}/wallet-moves/${movementId}`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      setMessage("");
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Movement was not updated");
    }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiJson("/api/v1/funds", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          base_currency: form.get("base_currency"),
          management_fee_pct: form.get("management_fee_pct"),
          performance_fee_pct: form.get("performance_fee_pct"),
        }),
      });
      event.currentTarget.reset();
      setMessage("Fund created. Attach live accounts, then publish NAV from their equity.");
      load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Fund was not created");
    }
  }

  return (
    <div className="max-w-5xl">
      <PageTitle title="Funds" detail="A fund owns a share of live account equity. Subscriptions do not move broker cash. The ledger below posts the same wallet and fund records in double entry." />
      {ledger ? (
        <section className="kpi-band">
          <h2>{ledger.balanced ? "Ledger balanced" : "Ledger out of balance"}</h2>
          <div className="book overflow-x-auto mb-4">
            <table>
              <thead>
                <tr><th>Account</th><th>Kind</th><th>Debit</th><th>Credit</th><th>Balance</th></tr>
              </thead>
              <tbody>
                {ledger.accounts.length ? ledger.accounts.map((row) => (
                  <tr key={row.code}>
                    <td>{row.code} {row.name}</td>
                    <td>{row.kind}</td>
                    <td className="num">{row.debit}</td>
                    <td className="num">{row.credit}</td>
                    <td className="num">{row.balance}</td>
                  </tr>
                )) : <tr><td colSpan={5}>No posted movements yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      <section className="mb-8 border border-line bg-panel rounded-lg p-4">
        <h2 className="mb-1">Wallets</h2>
        <p className="text-sm text-muted mb-3">Save a wallet address on a fund, then deposit or withdraw the cash recorded at that address. This does not change broker equity.</p>
        {rows.length === 0 ? <p className="text-sm text-muted">Create a fund below, then save a wallet address here.</p> : (
          <form className="grid md:grid-cols-4 gap-2 mb-4" onSubmit={saveWallet}>
            <select name="fund_id" required defaultValue={rows[0]?.id}>
              {rows.map((fund) => <option key={fund.id} value={fund.id}>{fund.name}</option>)}
            </select>
            <input name="label" placeholder="Wallet name" required />
            <input name="address" placeholder="Wallet address" required />
            <button className="primary" type="submit">Save address</button>
          </form>
        )}
        {rows.flatMap((fund) => (fund.wallets || []).filter((wallet) => wallet.owner === "fund").map((wallet) => (
          <form key={wallet.id} className="border border-line rounded p-3 mb-2" onSubmit={(event) => void moveWallet(event, fund.id, wallet.id)}>
            <div className="text-sm"><span className="font-medium">{wallet.label}</span> · {fund.name}</div>
            <div className="text-sm num text-muted break-all">{wallet.address}</div>
            <div className="text-sm num my-2">Available {wallet.available} {wallet.currency}</div>
            <div className="grid md:grid-cols-3 gap-2">
              <select name="direction" defaultValue="deposit"><option value="deposit">Deposit</option><option value="withdraw">Withdraw</option></select>
              <input name="amount" type="number" min="0.01" step="0.01" placeholder="Amount" required />
              <button className="primary" type="submit">Record</button>
            </div>
          </form>
        )))}
        {rows.some((fund) => (fund.wallets || []).some((wallet) => wallet.owner === "fund")) ? null : rows.length ? <p className="text-sm text-muted">No wallet saved yet.</p> : null}
        {rows.flatMap((fund) => (fund.movements || []).filter((row) => row.owner === "investor" && row.status === "pending").map((row) => (
          <div key={row.id} className="flex flex-wrap items-center gap-2 border border-line rounded px-3 py-2 mt-2 text-sm">
            <span className="flex-1">{row.direction} {row.amount} {row.currency} · {row.label} · <span className="num">{row.address}</span></span>
            <button className="primary" type="button" onClick={() => void settle(fund.id, row.id, "post")}>Post</button>
            <button className="ghost" type="button" onClick={() => void settle(fund.id, row.id, "reject")}>Reject</button>
          </div>
        )))}
      </section>
      <form className="grid md:grid-cols-5 gap-2 mb-6" onSubmit={create}>
        <input name="name" placeholder="Fund name" required />
        <input name="base_currency" placeholder="USD" defaultValue="USD" required />
        <input name="management_fee_pct" type="number" step="0.01" min="0" placeholder="Management % / year" defaultValue="0" />
        <input name="performance_fee_pct" type="number" step="0.01" min="0" placeholder="Performance %" defaultValue="0" />
        <button className="primary" type="submit">Create fund</button>
      </form>
      {message ? <p className="text-sm mb-4">{message}</p> : null}
      <div className="book overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-muted">
            <tr>
              <th className="px-3 py-2">Fund</th>
              <th className="px-3 py-2">Equity</th>
              <th className="px-3 py-2">Unit price</th>
              <th className="px-3 py-2">Units</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((fund) => (
              <tr key={fund.id} className="border-t border-line">
                <td className="px-3 py-2"><Link href={`/funds/${fund.id}`}>{fund.name}</Link></td>
                <td className="px-3 py-2 num">{fund.aum} {fund.base_currency}</td>
                <td className="px-3 py-2 num">{fund.unit_price}</td>
                <td className="px-3 py-2 num">{fund.units_outstanding}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
