"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type Block = {
  height: number;
  timestamp: number;
  previous_hash: string;
  hash: string;
  nonce: number;
  difficulty: number;
  miner: string;
  reward: string;
  earned: string;
  transactions: number;
  confirmations?: number;
};

type Tx = {
  tx_hash: string;
  kind: string;
  sender: string;
  recipient: string;
  amount: string;
  fee: string;
  status: string;
  confirmations: number;
  block_height: number | null;
};

type SearchResult = {
  kind: string;
  block?: Block & { transactions: Tx[] | number };
  transaction?: Tx;
  wallet?: { address: string; available: string; pending: string; mined: string; received: string; sent: string; transactions: Tx[] };
};

export default function ExplorerPage() {
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson<Block[]>("/api/v1/chain/blocks?limit=50").then(setBlocks).catch((err: Error) => setError(err.message));
  }, []);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      setResult(await apiJson<SearchResult>(`/api/v1/chain/search?q=${encodeURIComponent(query.trim())}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  return (
    <div className="max-w-5xl">
      <PageTitle title="Block explorer" detail="This server's Project Coin chain, newest first. Search a height, block hash, transaction hash, or wallet address." />
      <p className="text-sm mb-3"><Link className="text-accent" href="/project-coin">Back to mining</Link></p>
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      <form className="flex gap-2 mb-4" onSubmit={onSearch}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Height, hash, or address" required />
        <button className="primary" type="submit">Search</button>
      </form>
      {result?.kind === "none" ? <p className="text-sm text-muted mb-4">Nothing matched that search.</p> : null}
      {result?.kind === "block" && result.block ? <BlockCard block={result.block} /> : null}
      {result?.kind === "transaction" && result.transaction ? <TxTable rows={[result.transaction]} /> : null}
      {result?.kind === "wallet" && result.wallet ? (
        <section className="border border-line bg-panel rounded-lg px-4 py-4 mb-4 text-sm">
          <p className="num break-all mb-2">{result.wallet.address}</p>
          <p className="text-muted">Available {result.wallet.available} · Pending {result.wallet.pending} · Mined {result.wallet.mined} · Received {result.wallet.received} · Sent {result.wallet.sent}</p>
          <TxTable rows={result.wallet.transactions} />
        </section>
      ) : null}
      <table className="w-full text-sm bg-panel border border-line">
        <thead className="text-left text-muted">
          <tr>
            <th className="px-3 py-2">Height</th>
            <th>Hash</th>
            <th>Miner</th>
            <th>Reward</th>
            <th>Difficulty</th>
            <th>Nonce</th>
            <th>When</th>
            <th>Txs</th>
          </tr>
        </thead>
        <tbody>
          {blocks.map((block) => (
            <tr key={block.hash} className="border-t border-line">
              <td className="px-3 py-2">{block.height}</td>
              <td className="num break-all">{block.hash.slice(0, 18)}…</td>
              <td className="num break-all">{block.miner}</td>
              <td className="num">{block.reward}</td>
              <td>{block.difficulty}</td>
              <td className="num">{block.nonce}</td>
              <td>{block.timestamp ? new Date(block.timestamp * 1000).toLocaleString() : "—"}</td>
              <td>{block.transactions}</td>
            </tr>
          ))}
          {blocks.length === 0 ? <tr><td className="px-3 py-3 text-muted" colSpan={8}>No blocks yet.</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}

function BlockCard({ block }: { block: Block & { transactions?: Tx[] | number } }) {
  const rows = Array.isArray(block.transactions) ? block.transactions : [];
  return (
    <section className="border border-line bg-panel rounded-lg px-4 py-4 mb-4 text-sm">
      <p>Height {block.height} · confirmations {block.confirmations ?? "—"} · nonce {block.nonce}</p>
      <p className="num break-all mt-1">{block.hash}</p>
      <p className="text-muted mt-1">Previous {block.previous_hash}</p>
      <p className="mt-1">Miner {block.miner}</p>
      <p>Subsidy {block.reward} · earned {block.earned}</p>
      {rows.length ? <TxTable rows={rows} /> : null}
    </section>
  );
}

function TxTable({ rows }: { rows: Tx[] }) {
  return (
    <table className="w-full text-sm mt-3">
      <thead className="text-left text-muted"><tr><th className="py-2">Kind</th><th>Amount</th><th>Status</th><th>Parties</th></tr></thead>
      <tbody>
        {rows.map((tx) => (
          <tr key={tx.tx_hash} className="border-t border-line">
            <td className="py-2">{tx.kind}</td>
            <td className="num">{tx.amount}</td>
            <td>{tx.status}{tx.confirmations ? ` · ${tx.confirmations}` : ""}</td>
            <td className="num break-all">{tx.sender || "reward"} → {tx.recipient}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
