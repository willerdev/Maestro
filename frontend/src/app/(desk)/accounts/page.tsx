"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { accountHome } from "@/lib/accounts";
import { apiJson } from "@/lib/api";

type Account = {
  id: string;
  display_name: string;
  broker: string;
  server: string;
  account_number: string;
  connection_method: string;
  status: string;
  currency: string;
  equity: string;
  balance: string;
  control_state: string;
  monitoring_enabled: boolean;
};

const METHOD_LABEL: Record<string, string> = {
  metaapi: "MetaAPI",
  local_mt5: "MetaTrader",
  passprop: "Pass Props",
  pocketoption: "Options Trading",
  blockchain: "Contracts",
  mining: "Project Coin",
  webhook: "Webhook",
};

type SystemInfo = { can_add: boolean; counts: Record<string, number>; limits: Record<string, number>; enabled?: Record<string, boolean> };

export default function AccountsPage() {
  const [rows, setRows] = useState<Account[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [error, setError] = useState("");

  function load() {
    setError("");
    return Promise.all([
      apiJson<Account[]>("/api/v1/accounts").then(setRows).catch((err: Error) => { setError(err.message); }),
      apiJson<SystemInfo>("/api/v1/system").then(setSystem).catch(() => setSystem({ can_add: true, counts: {}, limits: {} })),
    ]);
  }

  useEffect(() => {
    load();
  }, []);

  async function remove(row: Account) {
    if (!window.confirm(`Delete ${row.display_name}? It will leave the running list.`)) return;
    setError("");
    try {
      await apiJson(`/api/v1/accounts/${row.id}`, { method: "DELETE" });
      setRows((current) => current.filter((item) => item.id !== row.id));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The account was not deleted");
      await load();
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <PageTitle title="Accounts" detail="Project Coin allows up to 20. MetaTrader and Pass Props allow up to 10. Options Trading allows up to 5 platforms. Other types allow one." />
        {system?.can_add === false ? <p className="text-sm text-muted">{Object.values(system.enabled || {}).some(Boolean) ? "Every account type is full." : "No account type is enabled yet."}</p> : <Link href="/accounts/new" className="primary inline-block px-3 py-2 rounded bg-accent text-[var(--on-accent)] font-semibold text-sm">Add account</Link>}
      </div>
      {error ? <p className="text-loss">{error}</p> : null}
      <table className="w-full text-sm border border-line bg-panel">
        <thead className="text-left text-muted">
          <tr>
            {["Name", "Number", "Method", "Status", "Control", "Equity", "Monitoring", ""].map((head) => (
              <th key={head} className="px-3 py-2 border-b border-line">{head}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-line">
              <td className="px-3 py-2"><Link href={accountHome(row.connection_method, row.id)} className="text-accent">{row.display_name}</Link></td>
              <td className="px-3 py-2 num">{row.account_number}</td>
              <td className="px-3 py-2">{METHOD_LABEL[row.connection_method] || row.connection_method}</td>
              <td className="px-3 py-2">{row.status === "connected" ? "Running" : row.status}</td>
              <td className="px-3 py-2">{row.control_state}</td>
              <td className="px-3 py-2 num">{row.equity} {row.currency}</td>
              <td className="px-3 py-2">{row.monitoring_enabled ? "On" : "Off"}</td>
              <td className="px-3 py-2 text-right"><button className="ghost" type="button" onClick={() => remove(row)}>Delete</button></td>
            </tr>
          ))}
          {rows.length === 0 ? <tr><td className="px-3 py-6 text-muted" colSpan={8}>No accounts yet.</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}
