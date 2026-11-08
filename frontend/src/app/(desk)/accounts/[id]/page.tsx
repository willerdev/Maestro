"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { AccountToolbar, type PocketInfo } from "@/components/AccountToolbar";
import { CandleChart } from "@/components/CandleChart";
import { PageTitle } from "@/components/Shell";
import { accountHome } from "@/lib/accounts";
import { api, apiJson } from "@/lib/api";

type Account = Record<string, string | number | boolean | null | object>;
type Position = Record<string, string | number | null>;
type Candle = { time: number; open: string; high: string; low: string; close: string };
type OrderResult = { sent: boolean; decision: string; message: string; risk_blocks_paused?: boolean };
type TradeStep = { tool: string; result: { sent?: boolean; decision?: string; message?: string; symbol?: string; bid?: string; ask?: string } };

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

function stepText(step: TradeStep) {
  const result = step.result;
  if (result.bid || result.ask) return `${step.tool}: ${result.symbol || ""} bid ${result.bid || "—"} ask ${result.ask || "—"}`;
  if (result.sent) return `${step.tool}: sent ${result.decision || ""} ${result.message || ""}`.trim();
  return `${step.tool}: ${result.decision || "not sent"} ${result.message || ""}`.trim();
}

const ACTIONS = [
  ["PAUSE_ACCOUNT", "PAUSE ACCOUNT"],
  ["RESUME_ACCOUNT", "RESUME ACCOUNT"],
  ["CLOSE_ALL_TRADES", "CLOSE ALL TRADES"],
  ["DISABLE_NEW_TRADES", "DISABLE NEW TRADES"],
  ["EMERGENCY_STOP", "EMERGENCY STOP"],
];

export default function AccountPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Position[]>([]);
  const [phrase, setPhrase] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [syncError, setSyncError] = useState("");
  const [asOf, setAsOf] = useState<Date | null>(null);
  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState("15m");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [aiReply, setAiReply] = useState("");
  const [aiSteps, setAiSteps] = useState<TradeStep[]>([]);
  const pocketHold = useRef<"demo" | "real" | "">("");

  async function loadClosed() {
    const closed = await apiJson<Position[]>(`/api/v1/accounts/${params.id}/trades`);
    setTrades(closed);
  }

  useEffect(() => {
    let stopped = false;
    let timer = 0;
    const load = async () => {
      try {
        const acct = await apiJson<Account>(`/api/v1/accounts/${params.id}?sync=1`);
        if (stopped) return;
        const method = String(acct.connection_method || "");
        if (method === "blockchain" || method === "mining" || method === "passprop") {
          router.replace(accountHome(method, params.id));
          return;
        }
        const incoming = acct.pocket && typeof acct.pocket === "object" ? (acct.pocket as PocketInfo) : null;
        if (pocketHold.current && incoming?.mode && incoming.mode !== pocketHold.current) {
          return;
        }
        pocketHold.current = "";
        setAccount(acct);
        setPositions(Array.isArray(acct.positions) ? (acct.positions as Position[]) : []);
        setSyncError(typeof acct.sync_error === "string" ? acct.sync_error : "");
        const stamp = typeof acct.last_sync_at === "string" ? new Date(acct.last_sync_at) : new Date();
        setAsOf(stamp);
      } catch (err) {
        if (!stopped) setSyncError(err instanceof Error ? err.message : "Live book could not be loaded");
      } finally {
        if (!stopped) timer = window.setTimeout(load, 1000);
      }
    };
    load();
    loadClosed().catch((err: Error) => setMessage(err.message));
    const closed = window.setInterval(() => {
      loadClosed().catch(() => undefined);
    }, 15000);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearInterval(closed);
    };
  }, [params.id]);

  useEffect(() => {
    if (symbol) return;
    const first = positions.find((row) => row.symbol) || trades.find((row) => row.symbol);
    if (first) setSymbol(String(first.symbol));
  }, [positions, trades, symbol]);

  useEffect(() => {
    if (!symbol || account?.connection_method !== "metaapi") return;
    let stopped = false;
    let timer = 0;
    const load = async () => {
      try {
        const body = await apiJson<{ candles: Candle[] }>(
          `/api/v1/accounts/${params.id}/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`,
        );
        if (!stopped) setCandles(body.candles || []);
      } catch {
        if (!stopped) setCandles([]);
      } finally {
        if (!stopped) timer = window.setTimeout(load, 15000);
      }
    };
    load();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [symbol, timeframe, params.id, account?.connection_method]);

  async function act(path: string, body?: object) {
    try {
      const response = await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) setMessage(typeof payload.detail === "string" ? payload.detail : "Action failed");
      else setMessage(typeof payload.status === "string" ? payload.status : String(payload.control_state || payload.detail || "Updated"));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Action failed");
    }
  }

  async function sendOrder(body: object) {
    try {
      const result = await apiJson<OrderResult>(`/api/v1/accounts/${params.id}/orders`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const pausedBlock = result.sent && result.risk_blocks_paused && result.decision !== "ALLOW" && result.decision !== "WARNING";
      setMessage(pausedBlock ? `Sent with risk blocks paused. ${result.decision}: ${result.message}` : result.sent ? `Order sent. ${result.decision}` : `${result.decision}: ${result.message}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Order failed");
    }
  }

  async function submitTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const limit = String(form.get("price") || "");
    await sendOrder({
      action: limit ? "limit" : "open",
      symbol,
      side: String(form.get("side") || "buy"),
      volume: form.get("volume"),
      stop_loss: form.get("stop_loss") || null,
      take_profit: form.get("take_profit") || null,
      price: limit || null,
    });
  }

  async function setRiskBlocks(paused: boolean) {
    await apiJson(`/api/v1/accounts/${params.id}`, { method: "PATCH", body: JSON.stringify({ risk_blocks_paused: paused }) });
    setAccount((current) => (current ? { ...current, risk_blocks_paused: paused } : current));
  }

  async function setAiTrading(enabled: boolean) {
    await apiJson(`/api/v1/accounts/${params.id}`, { method: "PATCH", body: JSON.stringify({ ai_trading_enabled: enabled }) });
    setAccount((current) => (current ? { ...current, ai_trading_enabled: enabled } : current));
  }

  async function askTrader(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const body = await apiJson<{ reply: string; steps: TradeStep[] }>(`/api/v1/accounts/${params.id}/ai/trade`, {
        method: "POST",
        body: JSON.stringify({ message: form.get("message") }),
      });
      setAiReply(body.reply);
      setAiSteps(body.steps || []);
    } catch (err) {
      setAiReply(err instanceof Error ? err.message : "DeepSeek did not answer");
      setAiSteps([]);
    }
  }

  async function confirmEmergency() {
    if (!pending) return;
    const expected = ACTIONS.find(([code]) => code === pending)?.[1] || "";
    if (phrase !== expected) {
      setMessage(`Type ${expected} to confirm`);
      return;
    }
    await act(`/api/v1/accounts/${params.id}/emergency`, { action: pending, confirm: phrase });
    setPending(null);
    setPhrase("");
  }

  if (!account) return <p className="text-muted">{syncError || message || "Loading account"}</p>;
  const floating = positions.reduce((sum, row) => sum + Number(row.floating_pl || 0), 0);
  const health = String(account.account_health ?? "—");
  const status = String(account.status ?? "");
  const control = String(account.control_state ?? "");
  const pocket = (account.pocket && typeof account.pocket === "object" ? account.pocket : null) as PocketInfo | null;
  const pocketMode = pocket?.mode === "demo" ? "demo" : pocket ? "real" : "";

  async function switchPocket(mode: "demo" | "real") {
    pocketHold.current = mode;
    setAccount((current) => {
      if (!current) return current;
      const currentPocket = current.pocket && typeof current.pocket === "object" ? (current.pocket as PocketInfo) : {};
      return { ...current, server: mode, pocket: { ...currentPocket, mode } };
    });
    setPositions([]);
    setMessage(mode === "demo" ? "Reading the demo book…" : "Reading the real book…");
    try {
      const body = await apiJson<Account>(`/api/v1/accounts/${params.id}/pocketoption/mode`, {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
      if (pocketHold.current !== mode) return;
      setAccount(body);
      if (Array.isArray(body.positions)) setPositions(body.positions as Position[]);
      setMessage(mode === "demo" ? "Demo book" : "Real book");
    } catch (err) {
      pocketHold.current = "";
      setMessage(err instanceof Error ? err.message : "The book did not switch");
    }
  }

  async function removeAccount() {
    if (!window.confirm(`Delete ${String(account.display_name)}? It will leave the running list.`)) return;
    setMessage("Removing…");
    try {
      await apiJson(`/api/v1/accounts/${params.id}`, { method: "DELETE" });
      router.push("/accounts");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "The account was not deleted");
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageTitle
          title={String(account.display_name)}
          detail={
            <span className="inline-flex flex-wrap items-center gap-2">
              {pocketMode ? <span className={`mode-chip ${pocketMode}`}>{pocketMode}</span> : null}
              <span>{`${account.broker} · ${account.account_number}`}</span>
            </span>
          }
        />
        <div className="mb-5 flex items-center gap-2 text-sm text-muted">
          <span className="live-dot" />
          <span>Live · {asOf ? asOf.toLocaleTimeString() : "waiting"}</span>
        </div>
      </div>
      {message ? <p className="mb-3 text-sm">{message}</p> : null}
      {syncError ? <p className="mb-3 text-sm text-loss">{syncError}</p> : null}
      {account.connection_method === "pocketoption" ? (
        <>
        <AccountToolbar
          accountId={params.id}
          monitoring={Boolean(account.monitoring_enabled)}
          pocket={pocket}
          onAct={act}
          onDelete={removeAccount}
          onMode={switchPocket}
        />
        <p className="roi-note">Guaranteed 10% ROI per day.</p>
        </>
      ) : (
      <div className="flex flex-wrap gap-2 mb-4">
        <button className="primary" onClick={() => act(`/api/v1/accounts/${params.id}/connect`)}>Connect</button>
        <button className="ghost" onClick={() => act(`/api/v1/accounts/${params.id}/disconnect`)}>Disconnect</button>
        <button className="ghost" onClick={() => act(`/api/v1/accounts/${params.id}/test-connection`)}>Test connection</button>
        <button className="ghost" onClick={() => act(`/api/v1/accounts/${params.id}/monitoring`, { enabled: !account.monitoring_enabled })}>
          {account.monitoring_enabled ? "Disable monitoring" : "Enable monitoring"}
        </button>
        <Link className="ghost inline-block" href={`/accounts/${params.id}/rules`}>Risk rules</Link>
        <button className="ghost" type="button" onClick={removeAccount}>Delete</button>
      </div>
      )}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Metric label="Balance" value={String(account.balance)} />
        <Metric label="Equity" value={String(account.equity)} tone="accent" tick />
        <Metric label="Margin" value={String(account.margin)} />
        <Metric label="Free margin" value={String(account.free_margin)} />
      </section>
      {account.connection_method === "pocketoption" ? (
        <>
          <form
            className="ticket pocket-ticket"
            onSubmit={(event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              void sendOrder({
                action: "open",
                symbol: String(form.get("symbol") || ""),
                side: String(form.get("side") || "sell"),
                volume: form.get("volume"),
                duration: Number(form.get("duration") || 60),
              });
            }}
          >
            <label className="sized-field">
              <span>Asset</span>
              <input name="symbol" defaultValue="AUCAD OTC" />
            </label>
            <label className="sized-field side">
              <span>Side</span>
              <select name="side" defaultValue="sell">
                <option value="buy">Call</option>
                <option value="sell">Put</option>
              </select>
            </label>
            <label className="sized-field side">
              <span>Expiry</span>
              <select name="duration" defaultValue="60">
                <option value="60">1 min</option>
                <option value="120">2 min</option>
                <option value="180">3 min</option>
                <option value="300">5 min</option>
              </select>
            </label>
            <label className="sized-field">
              <span>Stake</span>
              <input name="volume" defaultValue="100" />
            </label>
            <button className="primary" type="submit">Place test trade</button>
          </form>
          <section className="trade-board">
            <h2>Open trades</h2>
            <TradeTable rows={positions} />
          </section>
          <section className="trade-board">
            <h2>Closed trades</h2>
            <TradeTable rows={trades} closed />
          </section>
        </>
      ) : (
      <>
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Metric label="Floating P/L" value={signed(floating)} tone={toneOf(floating)} tick />
        <Metric label="Today P/L" value={signed(metricText(account.today_pl))} tone={toneOf(metricText(account.today_pl))} />
        <Metric label="Open trades" value={String(positions.length)} tone="accent" />
        <Metric label="Drawdown %" value={String(account.current_drawdown ?? "—")} tone={Number(account.current_drawdown) > 0 ? "bad" : ""} />
        <article className="metric">
          <div className="label">Account health</div>
          <div className="value"><StatusPill kind={healthKind(health)}>{health.replaceAll("_", " ")}</StatusPill></div>
        </article>
        <article className="metric">
          <div className="label">Status</div>
          <div className="value"><StatusPill kind={status === "connected" ? "ok" : "bad"}>{status || "—"}</StatusPill></div>
        </article>
        <article className="metric">
          <div className="label">Control</div>
          <div className="value"><StatusPill kind={control === "ACTIVE" ? "ok" : "warn"}>{control || "—"}</StatusPill></div>
        </article>
        <article className="metric">
          <div className="label">Monitoring</div>
          <div className="value"><StatusPill kind={account.monitoring_enabled ? "live" : "idle"}>{account.monitoring_enabled ? "On" : "Off"}</StatusPill></div>
        </article>
      </section>
      <div className="tv-top">
      <section className="chart-panel">
        <div className="chart-toolbar">
          <h2 className="mr-auto">Chart</h2>
          <input className="symbol-box" value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="Symbol" />
          {TIMEFRAMES.map((frame) => (
            <button key={frame} type="button" className={frame === timeframe ? "primary" : "ghost"} onClick={() => setTimeframe(frame)}>{frame}</button>
          ))}
        </div>
        <div className="chart-frame">
          {account.connection_method === "metaapi" && symbol ? <CandleChart candles={candles} /> : <p className="text-sm text-muted h-full grid place-items-center">No points for this diagram yet.</p>}
        </div>
        <form className="ticket" onSubmit={submitTicket}>
          <label className="sized-field side">
            <span>Side</span>
            <select name="side" defaultValue="buy">
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </label>
          <label className="sized-field">
            <span>Volume</span>
            <input name="volume" placeholder="0.01" required />
          </label>
          <label className="sized-field">
            <span>Stop</span>
            <input name="stop_loss" />
          </label>
          <label className="sized-field">
            <span>Take profit</span>
            <input name="take_profit" />
          </label>
          <label className="sized-field">
            <span>Limit price</span>
            <input name="price" />
          </label>
          <button className="primary" type="submit" disabled={account.connection_method !== "metaapi"}>Place trade</button>
          <label className="text-sm flex gap-2 items-center mb-1">
            <input className="w-auto" type="checkbox" checked={Boolean(account.risk_blocks_paused)} onChange={(event) => setRiskBlocks(event.target.checked)} />
            Pause risk blocks
          </label>
        </form>
        {account.risk_blocks_paused ? <p className="text-xs text-muted mt-2">Risk blocks are paused. The engine still records each decision, and orders are sent until you turn this off.</p> : null}
      </section>
      <section className="tv-open">
        <h2>Open trades</h2>
        <TradeTable rows={positions} onOrder={account.connection_method === "metaapi" ? sendOrder : undefined} />
      </section>
      </div>
      <div className="tv-bottom">
      <section className="assistant-panel">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h2>DeepSeek trade assistant</h2>
          <label className="text-sm flex gap-2 items-center">
            <input className="w-auto" type="checkbox" checked={Boolean(account.ai_trading_enabled)} onChange={(event) => setAiTrading(event.target.checked)} />
            Allow DeepSeek to trade this account
          </label>
        </div>
        <form className="assistant-form" onSubmit={askTrader}>
          <textarea name="message" rows={2} placeholder="Close the open buy and set the other trade to breakeven" />
          <button className="primary" type="submit">Send</button>
        </form>
        {aiReply ? <p className="text-sm mt-3">{aiReply}</p> : null}
        {aiSteps.length > 0 ? (
          <ul className="text-sm mt-2 space-y-1">
            {aiSteps.map((step, index) => (
              <li key={`${step.tool}-${index}`} className="num">{stepText(step)}</li>
            ))}
          </ul>
        ) : null}
      </section>
      <section className="tv-closed">
        <h2>Closed trades</h2>
        <TradeTable rows={trades} closed />
      </section>
      </div>
      <h2 className="mt-6 mb-2">Emergency controls</h2>
      <div className="flex flex-wrap gap-2">
        {ACTIONS.map(([code, label]) => (
          <button key={code} className={code === "EMERGENCY_STOP" ? "danger" : "ghost"} onClick={() => setPending(code)}>{label}</button>
        ))}
      </div>
      {pending ? (
        <div className="mt-3 max-w-md bg-panel border border-line rounded p-3">
          <p className="text-sm mb-2">Type {ACTIONS.find(([code]) => code === pending)?.[1]} to confirm. This writes an audit record.</p>
          <input value={phrase} onChange={(event) => setPhrase(event.target.value)} />
          <div className="flex gap-2 mt-2">
            <button className="primary" onClick={confirmEmergency}>Confirm</button>
            <button className="ghost" onClick={() => { setPending(null); setPhrase(""); }}>Cancel</button>
          </div>
        </div>
      ) : null}
      </>
      )}
    </div>
  );
}

function Metric({ label, value, tone = "", tick = false }: { label: string; value: string; tone?: string; tick?: boolean }) {
  return (
    <article className={`metric ${tone}`}>
      <div className="label">{label}</div>
      <div className={`value num ${tone === "good" ? "pos" : ""} ${tone === "bad" ? "neg" : ""}`}>
        {tick ? <Tick value={value} /> : value}
      </div>
    </article>
  );
}

function StatusPill({ kind, children }: { kind: string; children: React.ReactNode }) {
  return <span className={`pill ${kind}`}>{children}</span>;
}

function TradeTable({ rows, closed = false, onOrder }: { rows: Position[]; closed?: boolean; onOrder?: (body: object) => Promise<void> }) {
  const [drafts, setDrafts] = useState<Record<string, { stop: string; limit: string }>>({});
  const columns = ["Ticket", "Symbol", "Side", "Lot", "Entry", closed ? "Close" : "Price", "P/L", "Source", ...(onOrder ? ["Actions"] : [])];
  return (
    <div className="book overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-muted">
          <tr>{columns.map((head) => <th key={head} className="px-3 py-2">{head}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const side = String(row.direction || "").toLowerCase();
            const plValue = closed ? Number(row.profit) : runningPl(row);
            const pl = Number.isFinite(plValue) ? String(plValue) : String(closed ? row.profit : row.floating_pl);
            const outcome = tradeOutcome(row, closed);
            const ticket = String(row.ticket);
            const draft = drafts[ticket] || { stop: "", limit: "" };
            return (
              <tr key={ticket} className={`border-t border-line ${outcome === "win" ? "trade-win" : outcome === "loss" ? "trade-loss" : ""}`}>
                <td className="px-3 py-2 num">{row.ticket}</td>
                <td className="px-3 py-2">{row.symbol}</td>
                <td className="px-3 py-2"><span className={`pill ${side === "sell" || side === "put" ? "sell" : "buy"}`}>{side || "—"}</span></td>
                <td className="px-3 py-2 num">{row.lot}</td>
                <td className="px-3 py-2 num">{row.entry}</td>
                <td className="px-3 py-2 num">{closed ? row.close_price : <Tick value={String(row.current_price ?? "—")} />}</td>
                <td className={`px-3 py-2 num ${moneyClass(pl)}`}>{closed ? signed(pl) : <Tick value={signed(pl)} />}</td>
                <td className="px-3 py-2">{String(row.source || row.strategy || "—")}</td>
                {onOrder ? (
                  <td className="px-3 py-2">
                    <div className="row-actions">
                      <button type="button" className="ghost" onClick={() => onOrder({ action: "close", ticket })}>Close</button>
                      <button type="button" className="ghost" onClick={() => onOrder({ action: "breakeven", ticket })}>Breakeven</button>
                      <input placeholder="Stop" value={draft.stop} onChange={(event) => setDrafts((current) => ({ ...current, [ticket]: { ...draft, stop: event.target.value } }))} />
                      <input placeholder="Limit" value={draft.limit} onChange={(event) => setDrafts((current) => ({ ...current, [ticket]: { ...draft, limit: event.target.value } }))} />
                      <button type="button" className="ghost" onClick={() => onOrder({ action: "modify", ticket, stop_loss: draft.stop || null, take_profit: draft.limit || null })}>Set</button>
                    </div>
                  </td>
                ) : null}
              </tr>
            );
          })}
          {rows.length === 0 ? <tr><td className="px-3 py-6 text-muted" colSpan={columns.length}>{closed ? "No closed trades." : "No open trades."}</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}

function Tick({ value }: { value: string }) {
  const previous = useRef(value);
  const [flash, setFlash] = useState("");
  useEffect(() => {
    if (previous.current === value) return;
    const before = Number(previous.current.replace("+", ""));
    const after = Number(value.replace("+", ""));
    previous.current = value;
    if (!Number.isFinite(before) || !Number.isFinite(after) || before === after) return;
    setFlash(after > before ? "tick-up" : "tick-down");
    const timer = window.setTimeout(() => setFlash(""), 700);
    return () => window.clearTimeout(timer);
  }, [value]);
  return <span className={flash}>{value}</span>;
}

function metricText(value: string | number | boolean | object | null | undefined) {
  if (typeof value === "string" || typeof value === "number") return value;
  return null;
}

function signed(value: string | number | null | undefined) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const text = number.toFixed(2);
  return number > 0 ? `+${text}` : text;
}

function toneOf(value: string | number | null | undefined) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "good" : "bad";
}

function moneyClass(value: string) {
  const number = Number(String(value).replace("+", ""));
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "pos" : "neg";
}

function runningPl(row: Position) {
  const stored = Number(row.floating_pl);
  const entry = Number(row.entry);
  const current = Number(row.current_price);
  if (!Number.isFinite(entry) || !Number.isFinite(current)) return stored;
  const sell = String(row.direction || "").toLowerCase() === "sell" || String(row.direction || "").toLowerCase() === "put";
  const move = sell ? entry - current : current - entry;
  if (move === 0) return Number.isFinite(stored) ? stored : 0;
  return move;
}

function tradeOutcome(row: Position, closed: boolean): "win" | "loss" | "" {
  if (closed) {
    const profit = Number(row.profit);
    if (!Number.isFinite(profit) || profit === 0) return "";
    return profit > 0 ? "win" : "loss";
  }
  const entry = Number(row.entry);
  const current = Number(row.current_price);
  const side = String(row.direction || "").toLowerCase();
  if (Number.isFinite(entry) && Number.isFinite(current) && current !== entry) {
    const buy = side !== "sell" && side !== "put";
    const losing = buy ? current < entry : current > entry;
    return losing ? "loss" : "win";
  }
  const pl = runningPl(row);
  if (!Number.isFinite(pl) || pl === 0) return "";
  return pl > 0 ? "win" : "loss";
}

function healthKind(health: string) {
  const text = health.toUpperCase();
  if (text.includes("HIGH") || text.includes("CRITICAL")) return "bad";
  if (text.includes("RISK") || text.includes("WARN")) return "warn";
  if (text === "—" || text === "") return "idle";
  return "ok";
}
