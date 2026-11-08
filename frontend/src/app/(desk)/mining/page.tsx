"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type Account = {
  id: string;
  display_name: string;
  account_number: string;
  broker: string;
  server: string;
  currency: string;
  balance: string;
  status: string;
  connection_method: string;
};

type Probe = {
  ok: boolean;
  detail: string;
  account: { display_name: string; account_number: string; broker: string; server: string; currency: string; leverage: string } | null;
};

export default function MiningPage() {
  const [rows, setRows] = useState<Account[]>([]);
  const [chain, setChain] = useState("bitcoin");
  const [payout, setPayout] = useState("");
  const [worker, setWorker] = useState("");
  const [detail, setDetail] = useState("");
  const [error, setError] = useState("");

  function load() {
    return apiJson<Account[]>("/api/v1/accounts")
      .then((body) => setRows(body.filter((row) => row.connection_method === "mining")))
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setDetail("");
    const credentials = { chain, mining_address: payout.trim(), worker: worker.trim() };
    try {
      const probe = await apiJson<Probe>("/api/v1/connections/probe", {
        method: "POST",
        body: JSON.stringify({ connection_method: "mining", credentials }),
      });
      if (!probe.ok || !probe.account) {
        setError(probe.detail || "The mining balance was not read");
        return;
      }
      await apiJson("/api/v1/accounts", {
        method: "POST",
        body: JSON.stringify({
          display_name: probe.account.display_name,
          account_number: probe.account.account_number,
          broker: probe.account.broker,
          server: probe.account.server,
          connection_method: "mining",
          currency: probe.account.currency,
          leverage: "1",
          trading_day_timezone: "UTC",
          credentials,
        }),
      });
      setDetail(probe.detail);
      setPayout("");
      setWorker("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The mining payout was not saved");
    }
  }

  return (
    <div className="max-w-5xl">
      <PageTitle title="Mining" detail="Read a mining payout address on Bitcoin, Ethereum, BNB Chain, or Polygon." />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {detail ? <p className="text-sm text-profit mb-3">{detail}</p> : null}
      <div className="grid lg:grid-cols-2 gap-4 mb-8">
        <section className="border border-line bg-panel rounded-lg px-4 py-4">
          <h2 className="text-lg font-semibold mb-2">Requirements</h2>
          <ul className="text-sm text-muted list-disc pl-5">
            <li>The chain the miner is paid on.</li>
            <li>The public payout address.</li>
            <li>A worker name, if you want it stored with the payout.</li>
          </ul>
          <p className="text-sm text-muted mt-3">A private key or seed phrase is rejected and is not stored.</p>
        </section>
        <section className="border border-line bg-panel rounded-lg px-4 py-4">
          <h2 className="text-lg font-semibold mb-2">Functions</h2>
          <ul className="text-sm text-muted list-disc pl-5">
            <li>Read the mining payout balance.</li>
            <li>Keep the worker name with that payout.</li>
          </ul>
        </section>
      </div>
      <form className="grid md:grid-cols-4 gap-3 mb-8" onSubmit={connect}>
        <select value={chain} onChange={(event) => setChain(event.target.value)}>
          <option value="bitcoin">Bitcoin</option>
          <option value="ethereum">Ethereum</option>
          <option value="bnb">BNB Chain</option>
          <option value="polygon">Polygon</option>
        </select>
        <input value={payout} onChange={(event) => setPayout(event.target.value)} placeholder="Mining payout address" required autoComplete="off" />
        <input value={worker} onChange={(event) => setWorker(event.target.value)} placeholder="Worker name, optional" autoComplete="off" />
        <button className="primary" type="submit">Read mining balance</button>
      </form>
      <table className="w-full text-sm bg-panel border border-line">
        <thead className="text-left text-muted">
          <tr>
            <th className="px-3 py-2">Chain</th>
            <th>Payout</th>
            <th>Worker</th>
            <th>Balance</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-line">
              <td className="px-3 py-2"><Link href={`/accounts/${row.id}`}>{row.broker}</Link></td>
              <td className="num break-all">{row.account_number}</td>
              <td>{row.server === "mining" ? "—" : row.server}</td>
              <td className="num">{row.balance} {row.currency}</td>
              <td>{row.status}</td>
            </tr>
          ))}
          {rows.length === 0 ? <tr><td className="px-3 py-3 text-muted" colSpan={5}>No mining payouts yet.</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}
