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

export default function ContractsPage() {
  const [rows, setRows] = useState<Account[]>([]);
  const [chain, setChain] = useState("ethereum");
  const [wallet, setWallet] = useState("");
  const [contract, setContract] = useState("");
  const [detail, setDetail] = useState("");
  const [error, setError] = useState("");

  function load() {
    return apiJson<Account[]>("/api/v1/accounts")
      .then((body) => setRows(body.filter((row) => row.connection_method === "blockchain")))
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setDetail("");
    const credentials = { chain, wallet_address: wallet.trim(), contract_address: contract.trim() };
    try {
      const probe = await apiJson<Probe>("/api/v1/connections/probe", {
        method: "POST",
        body: JSON.stringify({ connection_method: "blockchain", credentials }),
      });
      if (!probe.ok || !probe.account) {
        setError(probe.detail || "The contract balance was not read");
        return;
      }
      await apiJson("/api/v1/accounts", {
        method: "POST",
        body: JSON.stringify({
          display_name: probe.account.display_name,
          account_number: probe.account.account_number,
          broker: probe.account.broker,
          server: probe.account.server,
          connection_method: "blockchain",
          currency: probe.account.currency,
          leverage: "1",
          trading_day_timezone: "UTC",
          credentials,
        }),
      });
      setDetail(probe.detail);
      setWallet("");
      setContract("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The contract was not saved");
    }
  }

  return (
    <div className="max-w-5xl">
      <PageTitle title="Contracts" detail="Read a public wallet and one contract on Ethereum, BNB Chain, or Polygon." />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {detail ? <p className="text-sm text-profit mb-3">{detail}</p> : null}
      <div className="grid lg:grid-cols-2 gap-4 mb-8">
        <section className="border border-line bg-panel rounded-lg px-4 py-4">
          <h2 className="text-lg font-semibold mb-2">Requirements</h2>
          <ul className="text-sm text-muted list-disc pl-5">
            <li>Ethereum, BNB Chain, or Polygon.</li>
            <li>The public wallet that holds the contract balance.</li>
            <li>The contract address.</li>
            <li>Minimum deposit $2,000.</li>
          </ul>
          <p className="text-sm text-muted mt-3">A private key or seed phrase is rejected and is not stored.</p>
        </section>
        <section className="border border-line bg-panel rounded-lg px-4 py-4">
          <h2 className="text-lg font-semibold mb-2">Functions</h2>
          <ul className="text-sm text-muted list-disc pl-5">
            <li>Read the wallet balance on the selected chain.</li>
            <li>Read that wallet’s balance of the contract.</li>
          </ul>
        </section>
      </div>
      <form className="grid md:grid-cols-4 gap-3 mb-8" onSubmit={connect}>
        <select value={chain} onChange={(event) => setChain(event.target.value)}>
          <option value="ethereum">Ethereum</option>
          <option value="bnb">BNB Chain</option>
          <option value="polygon">Polygon</option>
        </select>
        <input value={wallet} onChange={(event) => setWallet(event.target.value)} placeholder="Public wallet address" required autoComplete="off" />
        <input value={contract} onChange={(event) => setContract(event.target.value)} placeholder="Contract address" required autoComplete="off" />
        <button className="primary" type="submit">Read contract</button>
      </form>
      <table className="w-full text-sm bg-panel border border-line">
        <thead className="text-left text-muted">
          <tr>
            <th className="px-3 py-2">Chain</th>
            <th>Wallet</th>
            <th>Balance</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-line">
              <td className="px-3 py-2"><Link href={`/accounts/${row.id}`}>{row.broker}</Link></td>
              <td className="num break-all">{row.account_number}</td>
              <td className="num">{row.balance} {row.currency}</td>
              <td>{row.status}</td>
            </tr>
          ))}
          {rows.length === 0 ? <tr><td className="px-3 py-3 text-muted" colSpan={4}>No contracts yet.</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}
