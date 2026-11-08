"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, apiJson } from "@/lib/api";
import { HybridAdmin } from "@/components/project-coin/HybridAdmin";

type Rules = { enabled: boolean; rate: string; min_pcoin: string; max_pcoin: string; fee_bps: number; label: string; detail: string };
type Report = { conversions: number; pcoin_converted: string; usdt_credited: string };
type Row = { reference: string; email: string; pcoin: string; fee: string; usdt: string; rate: string; created_at: string };

export default function ConversionRatesPage() {
  const [rules, setRules] = useState<Rules | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function load() {
    Promise.all([
      apiJson<Rules>("/api/v1/chain/conversion/settings"),
      apiJson<Report>("/api/v1/chain/conversion/report"),
      apiJson<Row[]>("/api/v1/chain/conversion/history"),
    ]).then(([settings, totals, history]) => {
      setRules(settings);
      setReport(totals);
      setRows(history);
      setError("");
    }).catch((err: Error) => setError(err.message));
  }

  useEffect(() => { load(); }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!rules) return;
    setNotice("");
    try {
      const saved = await apiJson<Rules>("/api/v1/chain/conversion/settings", { method: "PUT", body: JSON.stringify(rules) });
      setRules(saved);
      setNotice("Exchange rate saved.");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The rate was not saved");
    }
  }

  async function download() {
    const response = await api("/api/v1/chain/conversion/export");
    const text = await response.text();
    const blob = new Blob([text], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "pcoin-conversions.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!rules && error) return <p className="text-loss">{error}</p>;
  if (!rules) return <p className="text-muted">Loading conversion settings…</p>;

  return (
    <>
      {error ? <p className="text-loss">{error}</p> : null}
      {notice ? <p className="text-profit">{notice}</p> : null}
      <div className="coin-grid">
        <div className="coin-stat"><span>Conversions</span><strong>{report?.conversions ?? 0}</strong></div>
        <div className="coin-stat"><span>PCoin converted</span><strong className="num">{report?.pcoin_converted ?? "0"}</strong></div>
        <div className="coin-stat"><span>USDT credited</span><strong className="num">{report?.usdt_credited ?? "0"}</strong></div>
      </div>
      <form className="coin-panel grid sm:grid-cols-2 gap-3" onSubmit={save}>
        <label className="text-sm">PCoin per 1 USDT
          <input className="block mt-1 w-full" value={rules.rate} onChange={(event) => setRules({ ...rules, rate: event.target.value })} required />
        </label>
        <label className="text-sm">Fee in basis points
          <input className="block mt-1 w-full" value={rules.fee_bps} onChange={(event) => setRules({ ...rules, fee_bps: Number(event.target.value) })} required />
        </label>
        <label className="text-sm">Minimum PCoin
          <input className="block mt-1 w-full" value={rules.min_pcoin} onChange={(event) => setRules({ ...rules, min_pcoin: event.target.value })} required />
        </label>
        <label className="text-sm">Maximum PCoin, 0 for none
          <input className="block mt-1 w-full" value={rules.max_pcoin} onChange={(event) => setRules({ ...rules, max_pcoin: event.target.value })} required />
        </label>
        <label className="text-sm flex items-center gap-2">
          <input type="checkbox" checked={rules.enabled} onChange={(event) => setRules({ ...rules, enabled: event.target.checked })} />
          Conversion enabled
        </label>
        <div className="coin-actions">
          <button className="primary" type="submit">Save rate</button>
          <button type="button" onClick={download}>Export CSV</button>
        </div>
      </form>
      <p className="text-sm text-muted">{rules.detail}</p>
      <section className="coin-panel overflow-x-auto">
        <table className="coin-table">
          <thead><tr><th>When</th><th>Account</th><th>PCoin</th><th>USDT</th><th>Reference</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.reference}>
                <td>{new Date(row.created_at).toLocaleString()}</td>
                <td>{row.email}</td>
                <td className="num">{row.pcoin}</td>
                <td className="num">{row.usdt}</td>
                <td className="num">{row.reference}</td>
              </tr>
            ))}
            {rows.length === 0 ? <tr><td colSpan={5}>No conversions yet.</td></tr> : null}
          </tbody>
        </table>
      </section>
      <HybridAdmin />
    </>
  );
}
