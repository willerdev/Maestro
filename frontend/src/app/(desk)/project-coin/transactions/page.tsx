"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { ActivityItem, typeLabel, when } from "@/lib/coin";

const KINDS = [
  ["all", "All"],
  ["mining_reward", "Mining reward"],
  ["incoming", "Incoming"],
  ["outgoing", "Outgoing"],
  ["network_fee", "Network fee"],
];

export default function TransactionsPage() {
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [rows, setRows] = useState<ActivityItem[]>([]);
  const [open, setOpen] = useState<ActivityItem | null>(null);
  const [error, setError] = useState("");
  const limit = 10;

  useEffect(() => {
    const params = new URLSearchParams({ kind, q: query, limit: String(limit), offset: String(page * limit) });
    apiJson<{ total: number; items: ActivityItem[] }>(`/api/v1/chain/activity?${params}`)
      .then((body) => { setTotal(body.total); setRows(body.items); setError(""); })
      .catch((err: Error) => setError(err.message));
  }, [kind, query, page]);

  function search(event: FormEvent) {
    event.preventDefault();
    setPage(0);
    const form = new FormData(event.currentTarget as HTMLFormElement);
    setQuery(String(form.get("q") || ""));
  }

  const pages = Math.max(1, Math.ceil(total / limit));

  return (
    <>
      <form className="flex gap-2" onSubmit={search}>
        <input name="q" defaultValue={query} placeholder="Search hash or address" />
        <button className="primary" type="submit">Search</button>
      </form>
      {error ? <p className="text-loss">{error}</p> : null}
      <div className="coin-actions">
        {KINDS.map(([value, label]) => (
          <button key={value} className={kind === value ? "primary" : ""} type="button" onClick={() => { setKind(value); setPage(0); }}>{label}</button>
        ))}
      </div>
      <section className="coin-panel overflow-x-auto">
        <table className="coin-table">
          <thead><tr><th>Type</th><th>Amount</th><th>Parties</th><th>Block</th><th>Status</th><th>When</th></tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.tx_hash}-${row.type}-${index}`} onClick={() => setOpen(row)}>
                <td>{typeLabel(row.type)}</td>
                <td className="num">{row.amount}</td>
                <td className="num break-all">{row.sender || "reward"} → {row.recipient}</td>
                <td>{row.block_height ?? "—"}</td>
                <td>{row.status}{row.confirmations ? ` · ${row.confirmations}` : ""}</td>
                <td>{when(row.timestamp)}</td>
              </tr>
            ))}
            {rows.length === 0 ? <tr><td colSpan={6}>No matching transactions.</td></tr> : null}
          </tbody>
        </table>
        <div className="coin-actions mt-3">
          <button type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button>
          <span className="text-sm text-muted">{page + 1} / {pages}</span>
          <button type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>Next</button>
        </div>
      </section>
      {open ? (
        <section className="coin-panel text-sm">
          <h2 className="font-semibold mb-2">{typeLabel(open.type)}</h2>
          <p className="num break-all">Transaction {open.tx_hash}</p>
          <p className="mt-2">Amount {open.amount} · fee {open.fee}</p>
          <p>From {open.sender || "block reward"}</p>
          <p className="break-all">To {open.recipient}</p>
          <p>Block {open.block_height ?? "not mined"} · {open.status} · {open.confirmations} confirmation{open.confirmations === 1 ? "" : "s"}</p>
          <p>{when(open.timestamp)}</p>
        </section>
      ) : null}
    </>
  );
}
