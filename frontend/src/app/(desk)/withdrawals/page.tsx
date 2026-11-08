"use client";

import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type RequestRow = {
  id: string;
  email: string;
  full_name: string;
  organization: string;
  currency: string;
  amount: string;
  address: string;
  status: string;
  note: string;
  created_at: string;
};

function coinLabel(value: string) {
  if (!value || value === "usdttrc20" || value === "usdt") return "USDT TRC20";
  return value.toUpperCase();
}

function when(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusLabel(status: string) {
  if (status === "requested") return "Waiting";
  if (status === "pending") return "Sending";
  if (status === "posted") return "Sent";
  if (status === "rejected") return "Rejected";
  if (status === "failed") return "Failed";
  return status;
}

export default function WithdrawalsPage() {
  const [rows, setRows] = useState<RequestRow[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  function load() {
    return apiJson<RequestRow[]>("/api/v1/admin/withdrawals")
      .then((body) => {
        setRows(body);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 8000);
    return () => window.clearInterval(timer);
  }, []);

  async function decide(row: RequestRow, action: "approve" | "reject") {
    const verb = action === "approve" ? "Approve" : "Reject";
    if (!window.confirm(`${verb} ${row.amount} ${coinLabel(row.currency)} for ${row.email}?`)) return;
    setBusy(`${action}-${row.id}`);
    setError("");
    setMessage("");
    try {
      const body = await apiJson<RequestRow>(`/api/v1/admin/withdrawals/${row.id}/${action}`, {
        method: "POST",
        body: JSON.stringify(action === "reject" ? { note: "" } : {}),
      });
      setRows((list) => list.map((item) => (item.id === body.id ? { ...item, ...body } : item)));
      setMessage(action === "approve" ? `Approved ${body.email}. The payout is being sent.` : `Rejected ${body.email}. The amount is back in their wallet.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request could not be updated");
    } finally {
      setBusy("");
    }
  }

  const waiting = rows.filter((row) => row.status === "requested");
  const rest = rows.filter((row) => row.status !== "requested");

  return (
    <div>
      <PageTitle title="Withdrawals" detail="Users request a payout from their wallet. Approve to send it, or reject to put the amount back." />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {message ? <p className="text-sm mb-3">{message}</p> : null}
      <h2 className="text-base font-semibold mb-2">Waiting for approval</h2>
      <table className="w-full text-sm border border-line bg-panel mb-8">
        <thead className="text-left text-muted">
          <tr>
            {["Person", "Amount", "Address", "Requested", ""].map((head) => (
              <th key={head} className="px-3 py-2 border-b border-line">{head}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {waiting.map((row) => (
            <tr key={row.id} className="border-b border-line">
              <td className="px-3 py-2">
                <div className="font-medium">{row.full_name || row.email}</div>
                <div className="text-muted text-xs">{row.email}</div>
                {row.organization ? <div className="text-muted text-xs">{row.organization}</div> : null}
              </td>
              <td className="px-3 py-2 num">{row.amount} {coinLabel(row.currency)}</td>
              <td className="px-3 py-2 num break-all">{row.address}</td>
              <td className="px-3 py-2 num">{when(row.created_at)}</td>
              <td className="px-3 py-2 text-right whitespace-nowrap">
                <button className="primary mr-2" type="button" disabled={Boolean(busy)} onClick={() => decide(row, "approve")}>
                  {busy === `approve-${row.id}` ? "Sending…" : "Approve"}
                </button>
                <button className="ghost" type="button" disabled={Boolean(busy)} onClick={() => decide(row, "reject")}>
                  {busy === `reject-${row.id}` ? "Rejecting…" : "Reject"}
                </button>
              </td>
            </tr>
          ))}
          {waiting.length === 0 ? <tr><td className="px-3 py-6 text-muted" colSpan={5}>No withdrawal requests waiting.</td></tr> : null}
        </tbody>
      </table>
      <h2 className="text-base font-semibold mb-2">History</h2>
      <table className="w-full text-sm border border-line bg-panel">
        <thead className="text-left text-muted">
          <tr>
            {["Person", "Amount", "Address", "Status", "When"].map((head) => (
              <th key={head} className="px-3 py-2 border-b border-line">{head}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rest.map((row) => (
            <tr key={row.id} className="border-b border-line">
              <td className="px-3 py-2">
                <div className="font-medium">{row.full_name || row.email}</div>
                <div className="text-muted text-xs">{row.email}</div>
              </td>
              <td className="px-3 py-2 num">{row.amount} {coinLabel(row.currency)}</td>
              <td className="px-3 py-2 num break-all">{row.address}</td>
              <td className="px-3 py-2">{statusLabel(row.status)}{row.note ? ` · ${row.note}` : ""}</td>
              <td className="px-3 py-2 num">{when(row.created_at)}</td>
            </tr>
          ))}
          {rest.length === 0 ? <tr><td className="px-3 py-6 text-muted" colSpan={5}>Approved and rejected payouts show here.</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}
