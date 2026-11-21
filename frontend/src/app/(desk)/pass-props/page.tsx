"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type Account = {
  id: string;
  display_name: string;
  account_number: string;
  connection_method: string;
  status: string;
  equity: string;
  currency: string;
  today_pl?: string;
  current_drawdown?: string;
  passprop?: { firm_name: string; firm_url: string; account_size: string };
};

export default function PassPropsListPage() {
  const [rows, setRows] = useState<Account[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson<Account[]>("/api/v1/accounts")
      .then((body) => setRows(body.filter((row) => row.connection_method === "passprop")))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <PageTitle title="Pass Props" detail="$100 USDT TRC20 for any size. If a challenge is breached, that $100 is returned to the wallet." />
        <Link href="/accounts/new" className="primary inline-block px-3 py-2 rounded bg-accent text-[var(--on-accent)] font-semibold text-sm">Add Pass Props</Link>
      </div>
      {error ? <p className="text-loss">{error}</p> : null}
      <table className="w-full text-sm border border-line bg-panel">
        <thead className="text-left text-muted">
          <tr>
            {["Firm", "Size", "Login", "Equity", "Today P/L", "Drawdown", "Status"].map((head) => (
              <th key={head} className="px-3 py-2 border-b border-line">{head}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-line">
              <td className="px-3 py-2">
                <Link className="text-accent" href={`/pass-props/${row.id}`}>{row.passprop?.firm_name || row.display_name}</Link>
                {row.passprop?.firm_url ? (
                  <div className="text-xs">
                    <a className="text-muted" href={row.passprop.firm_url} target="_blank" rel="noreferrer">{row.passprop.firm_url}</a>
                  </div>
                ) : null}
              </td>
              <td className="px-3 py-2 num">{row.passprop?.account_size || "—"}</td>
              <td className="px-3 py-2 num">{row.account_number}</td>
              <td className="px-3 py-2 num">{row.equity} {row.currency}</td>
              <td className={`px-3 py-2 num ${tone(row.today_pl)}`}>{signed(row.today_pl)}</td>
              <td className="px-3 py-2 num">{row.current_drawdown ? `${row.current_drawdown}%` : "—"}</td>
              <td className="px-3 py-2">{row.status === "connected" ? "Running" : row.status}</td>
            </tr>
          ))}
          {rows.length === 0 ? <tr><td className="px-3 py-6 text-muted" colSpan={7}>No Pass Props account yet. Add one from Accounts and choose Pass Props.</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}

function signed(value?: string) {
  const number = Number(value);
  if (!Number.isFinite(number)) return value || "—";
  const text = number.toFixed(2);
  return number > 0 ? `+${text}` : text;
}

function tone(value?: string) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "pos" : "neg";
}
