"use client";

import { FormEvent, useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson, type User } from "@/lib/api";

type Member = {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
  is_active: boolean;
  organization: string;
  accounts: number;
  wallet_usdt: string;
  pcoin: string;
  contract_yield: string;
  contract_held: string;
  created_at: string;
};

function money(value: string) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  return amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 8 });
}

function when(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function UsersPage() {
  const [me, setMe] = useState<User | null>(null);
  const [rows, setRows] = useState<Member[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  const current = rows.find((row) => row.id === selected) || null;

  function load(keep = selected) {
    return apiJson<Member[]>("/api/v1/users")
      .then((body) => {
        setRows(body);
        setSelected((now) => {
          if (keep && body.some((row) => row.id === keep)) return keep;
          return body[0]?.id || "";
        });
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    apiJson<User>("/api/v1/auth/me").then(setMe).catch(() => undefined);
    load("");
  }, []);

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!current) return;
    const form = event.currentTarget;
    const password = String(new FormData(form).get("password") || "");
    const confirm = String(new FormData(form).get("confirm") || "");
    setError("");
    setMessage("");
    if (password !== confirm) {
      setError("The two passwords do not match");
      return;
    }
    setBusy("password");
    try {
      const row = await apiJson<Member>(`/api/v1/users/${current.id}/password`, {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setRows((list) => list.map((item) => (item.id === row.id ? { ...item, ...row } : item)));
      form.reset();
      setMessage(`Password updated for ${row.email}. Their other sessions are signed out.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password could not be changed");
    } finally {
      setBusy("");
    }
  }

  async function setBanned(banned: boolean) {
    if (!current) return;
    if (banned && !window.confirm(`Ban ${current.email}? They will not be able to sign in.`)) return;
    setError("");
    setMessage("");
    setBusy(banned ? "ban" : "unban");
    try {
      const row = await apiJson<Member>(`/api/v1/users/${current.id}/${banned ? "ban" : "unban"}`, { method: "POST" });
      setRows((list) => list.map((item) => (item.id === row.id ? { ...item, ...row } : item)));
      setMessage(banned ? `${row.email} is banned.` : `${row.email} can sign in again.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status could not be updated");
    } finally {
      setBusy("");
    }
  }

  async function allocate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!current) return;
    const form = event.currentTarget;
    const amount = String(new FormData(form).get("amount") || "").trim();
    setError("");
    setMessage("");
    if (!amount) {
      setError("Enter an amount to add");
      return;
    }
    if (!window.confirm(`Add ${amount} USDT TRC20 to ${current.email}?`)) return;
    setBusy("wallet");
    try {
      const body = await apiJson<{ user: Member }>(`/api/v1/users/${current.id}/wallet`, {
        method: "POST",
        body: JSON.stringify({ amount, currency: "usdttrc20" }),
      });
      setRows((list) => list.map((item) => (item.id === body.user.id ? { ...item, ...body.user } : item)));
      form.reset();
      setMessage(`${amount} USDT TRC20 added to ${body.user.email}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Wallet could not be credited");
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      <PageTitle title="Users" detail="Everyone who has a login, what they are earning, and controls for password, ban, and wallet credit." />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {message ? <p className="text-sm mb-3">{message}</p> : null}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <table className="w-full text-sm border border-line bg-panel">
          <thead className="text-left text-muted">
            <tr>
              {["Person", "Wallet", "Contract yield", "PCoin", "Accounts", "Status", "Joined"].map((head) => (
                <th key={head} className="px-3 py-2 border-b border-line">{head}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const on = row.id === selected;
              return (
                <tr
                  key={row.id}
                  className={`border-b border-line cursor-pointer ${on ? "bg-[var(--accent-soft,transparent)]" : ""}`}
                  onClick={() => setSelected(row.id)}
                >
                  <td className="px-3 py-2">
                    <div className="font-medium">{row.full_name || row.email}</div>
                    <div className="text-muted text-xs">{row.email}</div>
                    <div className="text-muted text-xs">{row.roles.join(", ") || "—"}</div>
                  </td>
                  <td className="px-3 py-2 num">{money(row.wallet_usdt)} USDT</td>
                  <td className="px-3 py-2 num">{money(row.contract_yield)}</td>
                  <td className="px-3 py-2 num">{row.pcoin}</td>
                  <td className="px-3 py-2 num">{row.accounts}</td>
                  <td className="px-3 py-2">{row.is_active ? "Active" : "Banned"}</td>
                  <td className="px-3 py-2 num">{when(row.created_at)}</td>
                </tr>
              );
            })}
            {rows.length === 0 ? <tr><td className="px-3 py-6 text-muted" colSpan={7}>No users yet.</td></tr> : null}
          </tbody>
        </table>
        <aside className="border border-line bg-panel p-4 h-fit">
          {current ? (
            <>
              <h2 className="text-base font-semibold mb-1">{current.full_name || current.email}</h2>
              <p className="text-sm text-muted mb-4">{current.email} · {current.organization || "Desk"}</p>
              <dl className="text-sm grid grid-cols-2 gap-2 mb-5">
                <div>
                  <dt className="text-muted">Wallet</dt>
                  <dd className="num">{money(current.wallet_usdt)} USDT TRC20</dd>
                </div>
                <div>
                  <dt className="text-muted">Yield</dt>
                  <dd className="num">{money(current.contract_yield)}</dd>
                </div>
                <div>
                  <dt className="text-muted">Held in contracts</dt>
                  <dd className="num">{money(current.contract_held)}</dd>
                </div>
                <div>
                  <dt className="text-muted">PCoin</dt>
                  <dd className="num">{current.pcoin}</dd>
                </div>
              </dl>
              <form className="flex flex-col gap-2 mb-5" onSubmit={allocate}>
                <div className="label">Allocate to wallet</div>
                <input name="amount" type="number" min="0.01" step="0.01" placeholder="Amount in USDT TRC20" required />
                <button className="primary" type="submit" disabled={busy === "wallet"}>{busy === "wallet" ? "Adding…" : "Add USDT TRC20"}</button>
              </form>
              <form className="flex flex-col gap-2 mb-5" onSubmit={changePassword}>
                <div className="label">Change password</div>
                <input name="password" type="password" autoComplete="new-password" placeholder="New password" minLength={12} required />
                <input name="confirm" type="password" autoComplete="new-password" placeholder="Confirm password" minLength={12} required />
                <p className="text-xs text-muted">At least 12 characters, with a letter and a digit. Their sessions are signed out.</p>
                <button className="ghost" type="submit" disabled={busy === "password"}>{busy === "password" ? "Saving…" : "Save password"}</button>
              </form>
              {me?.id === current.id ? (
                <p className="text-sm text-muted">You cannot ban your own login.</p>
              ) : current.is_active ? (
                <button className="ghost" type="button" disabled={busy === "ban"} onClick={() => setBanned(true)}>
                  {busy === "ban" ? "Banning…" : "Ban user"}
                </button>
              ) : (
                <button className="primary" type="button" disabled={busy === "unban"} onClick={() => setBanned(false)}>
                  {busy === "unban" ? "Restoring…" : "Unban user"}
                </button>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">Select a person to manage their login and wallet.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
