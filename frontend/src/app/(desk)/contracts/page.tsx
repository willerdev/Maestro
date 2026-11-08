"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ExtraWallets } from "@/components/ExtraWallets";
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

type Position = {
  id: string;
  account_id: string;
  account: string;
  principal: string;
  yield_earned: string;
  held: string;
  status: string;
  locked: boolean;
  can_cancel: boolean;
  can_withdraw: boolean;
  unlock_at: string;
  last_yield_on: string;
};

type Desk = {
  daily_rate: string;
  rate_range: string;
  min_deposit: string;
  wallet_usdt: string;
  accounts: { id: string; display_name: string; account_number: string }[];
  positions: Position[];
};

export default function ContractsPage() {
  const [rows, setRows] = useState<Account[]>([]);
  const [chain, setChain] = useState("ethereum");
  const [wallet, setWallet] = useState("");
  const [contract, setContract] = useState("");
  const [detail, setDetail] = useState("");
  const [error, setError] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [desk, setDesk] = useState<Desk | null>(null);
  const [amount, setAmount] = useState("");
  const [target, setTarget] = useState("");

  useEffect(() => {
    setAccepted(sessionStorage.getItem("maestro-account-terms") === "blockchain");
  }, []);

  function load() {
    return Promise.all([
      apiJson<Account[]>("/api/v1/accounts").then((body) => setRows(body.filter((row) => row.connection_method === "blockchain"))),
      apiJson<Desk>("/api/v1/contracts/desk").then((body) => {
        setDesk(body);
        if (!target && body.accounts[0]) setTarget(body.accounts[0].id);
      }),
    ]).catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function act(id: string, action: "cancel" | "withdraw") {
    setError("");
    setDetail("");
    try {
      const body = await apiJson<{ returned?: string; position: Position }>(`/api/v1/contracts/${id}/${action}`, { method: "POST" });
      setDetail(action === "cancel"
        ? `Cancelled. Yield is forfeited. Initial ${body.position.principal} USDT ${body.position.can_withdraw ? "can be withdrawn now" : "can be withdrawn after 7 days"}.`
        : `Returned ${body.returned} USDT to the default wallet.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The contract change was rejected");
    }
  }

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
      <PageTitle title="Contracts" detail={`Transfer USDT before a contract runs. Daily yield ${desk?.rate_range || "2.00% to 2.98%"}. Funds stay on the contract for 7 days. Cancel forfeits yield; after 7 days you can withdraw the initial balance.`} />
      {accepted ? <p className="text-sm text-profit mb-3">Terms accepted. Blockchain contracts is on the running account list.</p> : null}
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {detail ? <p className="text-sm text-profit mb-3">{detail}</p> : null}
      <div className="grid lg:grid-cols-2 gap-4 mb-8">
        <section className="border border-line bg-panel rounded-lg px-4 py-4">
          <h2 className="text-lg font-semibold mb-2">Requirements</h2>
          <ul className="text-sm text-muted list-disc pl-5">
            <li>Ethereum, BNB Chain, or Polygon.</li>
            <li>The public wallet that holds the contract balance.</li>
            <li>The contract address.</li>
            <li>Minimum transfer {desk?.min_deposit || "2000"} USDT from the default wallet.</li>
            <li>Daily yield {desk?.rate_range || "2.00% to 2.98%"} only after the transfer is on the contract.</li>
            <li>Funds stay on the contract for 7 days. Cancel drops the yield. After 7 days you can withdraw the initial balance.</li>
          </ul>
          <p className="text-sm text-muted mt-3">A private key or seed phrase is not required to fund a contract. Convert mined PCoin to USDT TRC20 on the default wallet first if the wallet is empty.</p>
        </section>
        <section className="border border-line bg-panel rounded-lg px-4 py-4">
          <h2 className="text-lg font-semibold mb-2">Functions</h2>
          <ul className="text-sm text-muted list-disc pl-5">
            <li>Read a public wallet and one contract.</li>
            <li>Transfer default-wallet USDT onto the contract. The funds go on hold.</li>
            <li>Credit {desk?.daily_rate || "2.00%"} each UTC day only after money is transferred.</li>
            <li>After 7 days, withdraw. A cancel keeps only the original amount.</li>
          </ul>
          <p className="text-sm mt-3">Default wallet USDT TRC20 available: <span className="num">{desk?.wallet_usdt || "0"}</span></p>
        </section>
      </div>
      <form className="grid md:grid-cols-3 gap-3 mb-8" onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        setDetail("");
        try {
          const body = await apiJson<{ position: Position; wallet_usdt: string }>("/api/v1/contracts/fund", {
            method: "POST",
            body: JSON.stringify({ account_id: target, amount }),
          });
          setDetail(`Transferred ${body.position.principal} USDT to ${body.position.account}. Status: ${body.position.status}.`);
          setAmount("");
          await load();
        } catch (err) {
          setError(err instanceof Error ? err.message : "The transfer was rejected");
        }
      }}>
        <select value={target} onChange={(event) => setTarget(event.target.value)} required>
          <option value="">Choose a contract account</option>
          {(desk?.accounts || []).map((row) => (
            <option key={row.id} value={row.id}>{row.display_name}</option>
          ))}
        </select>
        <input value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="USDT to transfer" required />
        <button className="primary" type="submit" disabled={!target}>Transfer to contract</button>
      </form>
      {!desk?.accounts.length ? <p className="text-sm text-muted mb-4">Add a blockchain contract account before transferring.</p> : null}
      {desk && Number(desk.wallet_usdt) <= 0 ? <p className="text-sm text-muted mb-4">USDT must be on the default wallet before a contract can run. Convert mined PCoin or deposit first.</p> : null}
      <table className="w-full text-sm bg-panel border border-line mb-8">
        <thead className="text-left text-muted">
          <tr>
            <th className="px-3 py-2">Contract</th>
            <th>Principal</th>
            <th>Yield</th>
            <th>Held</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {(desk?.positions || []).map((row) => (
            <tr key={row.id} className="border-t border-line">
              <td className="px-3 py-2">{row.account}</td>
              <td className="num">{row.principal} USDT</td>
              <td className="num">{row.yield_earned} USDT</td>
              <td className="num">{row.held} USDT</td>
              <td>{row.status}{row.locked ? ` · locked until ${row.unlock_at.slice(0, 10)}` : ""}</td>
              <td className="px-3 py-2 text-right">
                {row.can_cancel ? <button className="ghost" type="button" onClick={() => act(row.id, "cancel")}>Cancel</button> : null}
                {row.can_withdraw ? <button className="primary" type="button" onClick={() => act(row.id, "withdraw")}>Withdraw</button> : null}
                {row.locked && !row.can_withdraw ? <span className="text-muted">Capital after {row.unlock_at.slice(0, 10)}</span> : null}
              </td>
            </tr>
          ))}
          {!desk?.positions.length ? <tr><td className="px-3 py-3 text-muted" colSpan={6}>No contract transfers yet. Transfer USDT before the contract runs.</td></tr> : null}
        </tbody>
      </table>
      <ExtraWallets onConnected={(row) => setWallet(row.address)} />
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
              <td className="px-3 py-2">{row.broker || row.display_name}</td>
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
