"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type PassProp = { firm_name: string; firm_url: string; rules: string; account_size: string; fee?: string; fee_status?: string; refund_on_breach?: boolean };
type Account = {
  id: string;
  display_name: string;
  account_number: string;
  broker: string;
  server: string;
  currency: string;
  status: string;
  connection_method?: string;
  equity: string;
  balance: string;
  today_pl?: string;
  current_drawdown?: string;
  last_sync_at?: string | null;
  passprop?: PassProp;
};
type Position = { ticket: string; symbol: string; direction: string; lot: string; entry: string; floating_pl: string };
type Trade = { ticket: string; symbol: string; direction: string; lot: string; entry: string; close_price: string | null; profit: string; status: string };
type Day = { date: string; net: string; result: string; trade_count: number; trades: Trade[] };
type Journal = { currency: string; error: string; summary: { profitable_days: number; loss_days: number; even_days: number; net: string; trades: number }; days: Day[] };

export default function PassPropPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [journal, setJournal] = useState<Journal | null>(null);
  const [error, setError] = useState("");
  const [copyNote, setCopyNote] = useState("");
  const [asOf, setAsOf] = useState<Date | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    let stopped = false;
    let timer = 0;
    const load = async () => {
      try {
        const acct = await apiJson<Account>(`/api/v1/accounts/${params.id}`);
        if (stopped) return;
        if (acct.connection_method && acct.connection_method !== "passprop") {
          router.replace("/pass-props");
          return;
        }
        setAccount(acct);
        setAsOf(acct.last_sync_at ? new Date(acct.last_sync_at) : new Date());
        const open = await apiJson<Position[]>(`/api/v1/accounts/${params.id}/positions`);
        if (!stopped) setPositions(open);
        setError("");
      } catch (err) {
        if (!stopped) setError(err instanceof Error ? err.message : "Pass Props account could not be loaded");
      } finally {
        if (!stopped) timer = window.setTimeout(load, 4000);
      }
    };
    load();
    apiJson<Journal>(`/api/v1/journal?account_id=${params.id}`)
      .then((body) => {
        if (!stopped) setJournal(body);
      })
      .catch(() => undefined);
    const journalTimer = window.setInterval(() => {
      apiJson<Journal>(`/api/v1/journal?account_id=${params.id}`)
        .then((body) => {
          if (!stopped) setJournal(body);
        })
        .catch(() => undefined);
    }, 20000);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearInterval(journalTimer);
    };
  }, [params.id, router]);

  async function markBreached() {
    if (!account) return;
    if (!window.confirm("Mark this challenge as breached and return the $100 fee to the wallet?")) return;
    setBusy("refund");
    setError("");
    try {
      const row = await apiJson<Account>(`/api/v1/accounts/${account.id}/passprop/breach`, { method: "POST" });
      setAccount(row);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The fee could not be returned");
    } finally {
      setBusy("");
    }
  }

  const prop = account?.passprop;
  const size = Number(prop?.account_size);
  const equity = Number(account?.equity);
  const vsSize = Number.isFinite(size) && size > 0 && Number.isFinite(equity) ? equity - size : null;
  const vsPct = vsSize !== null && size > 0 ? (vsSize / size) * 100 : null;
  const floating = positions.reduce((total, row) => total + (Number(row.floating_pl) || 0), 0);
  const latest = journal?.days[0];

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageTitle
          title={prop?.firm_name || account?.display_name || "Pass Props"}
          detail={`${prop?.account_size ? `Size ${prop.account_size}` : "Prop account"} · login ${account?.account_number || "—"} · ${account?.server || ""}`}
        />
        <div className="mb-5 flex items-center gap-3 text-sm">
          <Link className="ghost" href="/pass-props">All Pass Props</Link>
          {prop?.firm_url ? <a className="ghost" href={prop.firm_url} target="_blank" rel="noreferrer">Firm site</a> : null}
          <span className="text-muted">{asOf ? asOf.toLocaleTimeString() : ""}</span>
        </div>
      </div>
      <p className="roi-note mb-4">$100 USDT TRC20 for any size. If this challenge is breached, that $100 is returned to the wallet.</p>
      {prop?.fee_status === "charged" ? (
        <p className="text-sm mb-4">
          Challenge fee paid.{" "}
          <button className="ghost" type="button" disabled={busy === "refund"} onClick={markBreached}>
            {busy === "refund" ? "Returning…" : "Challenge breached · return $100"}
          </button>
        </p>
      ) : null}
      {prop?.fee_status === "refunded" ? <p className="text-sm text-profit mb-4">The $100 challenge fee was returned to the wallet after a breach.</p> : null}
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {journal?.error ? <p className="text-sm text-muted mb-3">{journal.error}</p> : null}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Metric label="Balance" value={`${account?.balance || "—"} ${account?.currency || ""}`} />
        <Metric label="Equity" value={`${account?.equity || "—"} ${account?.currency || ""}`} tone="accent" />
        <Metric label="Today P/L" value={signed(account?.today_pl)} tone={toneOf(account?.today_pl)} />
        <Metric label="Drawdown" value={account?.current_drawdown ? `${account.current_drawdown}%` : "—"} tone={Number(account?.current_drawdown) > 0 ? "bad" : ""} />
        <Metric label="Profit vs size" value={vsSize === null ? "—" : `${signed(String(vsSize))} ${account?.currency || ""}`} tone={toneOf(String(vsSize ?? ""))} />
        <Metric label="Vs size %" value={vsPct === null ? "—" : `${vsPct.toFixed(2)}%`} tone={toneOf(String(vsPct ?? ""))} />
        <Metric label="Floating" value={signed(String(floating))} tone={toneOf(String(floating))} />
        <Metric label="Journal net" value={journal ? `${signed(journal.summary.net)} ${journal.currency}` : "—"} tone={toneOf(journal?.summary.net)} />
      </section>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] mb-6">
        <section className="border border-line bg-panel p-4">
          <div className="flex items-center justify-between gap-2 mb-3">
            <h2 className="text-base font-semibold">Firm rules</h2>
            <button
              className="ghost"
              type="button"
              onClick={() => {
                const text = prop?.rules || "";
                if (!text) {
                  setCopyNote("No rules saved on this account.");
                  return;
                }
                navigator.clipboard.writeText(text).then(
                  () => setCopyNote("Rules copied."),
                  () => setCopyNote("Copy was blocked by the browser."),
                );
              }}
            >Copy rules</button>
          </div>
          {copyNote ? <p className="text-sm text-muted mb-2">{copyNote}</p> : null}
          {prop?.rules ? <pre className="text-sm whitespace-pre-wrap break-words max-h-80 overflow-auto">{prop.rules}</pre> : <p className="text-sm text-muted">No rules were saved. Edit is not on this page; add another Pass Props account if the rules change.</p>}
        </section>
        <section className="border border-line bg-panel p-4">
          <h2 className="text-base font-semibold mb-3">Journal</h2>
          {journal ? (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <p>Profitable days <b>{journal.summary.profitable_days}</b></p>
              <p>Loss days <b>{journal.summary.loss_days}</b></p>
              <p>Trades <b>{journal.summary.trades}</b></p>
              <p>Even days <b>{journal.summary.even_days}</b></p>
            </div>
          ) : <p className="text-sm text-muted">Reading closed trades…</p>}
          {latest ? (
            <div className="mt-4">
              <p className="text-sm text-muted mb-2">Latest day {latest.date.slice(0, 10)} · {signed(latest.net)}</p>
              <table className="w-full text-sm">
                <tbody>
                  {latest.trades.slice(0, 8).map((trade) => (
                    <tr key={`${trade.status}-${trade.ticket}`} className="border-t border-line">
                      <td className="py-1">{trade.symbol}</td>
                      <td className="py-1">{trade.direction}</td>
                      <td className={`py-1 num ${toneClass(trade.profit)}`}>{signed(trade.profit)}</td>
                      <td className="py-1 text-muted">{trade.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <p className="text-sm mt-3"><Link className="text-accent" href="/journal">Open full journal</Link></p>
        </section>
      </div>
      <section className="border border-line bg-panel">
        <h2 className="px-3 py-2 text-sm">Open positions</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-muted">
            <tr>{["Ticket", "Symbol", "Side", "Lot", "Entry", "P/L"].map((head) => <th key={head} className="px-3 py-2">{head}</th>)}</tr>
          </thead>
          <tbody>
            {positions.map((row) => (
              <tr key={row.ticket} className="border-t border-line">
                <td className="px-3 py-2 num">{row.ticket}</td>
                <td className="px-3 py-2">{row.symbol}</td>
                <td className="px-3 py-2">{row.direction}</td>
                <td className="px-3 py-2 num">{row.lot}</td>
                <td className="px-3 py-2 num">{row.entry}</td>
                <td className={`px-3 py-2 num ${toneClass(row.floating_pl)}`}>{signed(row.floating_pl)}</td>
              </tr>
            ))}
            {positions.length === 0 ? <tr><td className="px-3 py-6 text-muted" colSpan={6}>No open positions.</td></tr> : null}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Metric({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <article className={`metric ${tone}`}>
      <div className="label">{label}</div>
      <div className={`value num text-lg ${tone === "good" ? "pos" : ""} ${tone === "bad" ? "neg" : ""}`}>{value}</div>
    </article>
  );
}

function signed(value?: string) {
  const number = Number(value);
  if (!Number.isFinite(number)) return value || "—";
  const text = number.toFixed(2);
  return number > 0 ? `+${text}` : text;
}

function toneOf(value?: string) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "good" : "bad";
}

function toneClass(value?: string) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "pos" : "neg";
}
