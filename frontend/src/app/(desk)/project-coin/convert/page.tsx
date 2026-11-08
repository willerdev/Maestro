"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Quote = { pcoin: string; fee: string; total_pcoin: string; usdt: string; rate: string; available_pcoin: string };
type Result = Quote & { reference: string; available_usdt: string; duplicate: boolean };
type Rules = { enabled: boolean; rate: string; min_pcoin: string; max_pcoin: string; fee_bps: number; label: string; detail: string };

export default function ConvertPage() {
  const [rules, setRules] = useState<Rules | null>(null);
  const [amount, setAmount] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiJson<Rules>("/api/v1/chain/conversion/settings").then(setRules).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!amount) {
      setQuote(null);
      return;
    }
    const handle = window.setTimeout(() => {
      apiJson<Quote>(`/api/v1/chain/conversion/quote?amount=${encodeURIComponent(amount)}`)
        .then((body) => { setQuote(body); setError(""); })
        .catch((err: Error) => { setQuote(null); setError(err.message); });
    }, 300);
    return () => window.clearTimeout(handle);
  }, [amount]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!confirm) {
      setConfirm(true);
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const body = await apiJson<Result>("/api/v1/chain/conversion", { method: "POST", body: JSON.stringify({ amount }) });
      setNotice(`Converted ${body.pcoin} PCoin to ${body.usdt} USDT TRC20 on the default wallet. Reference ${body.reference}. Available PCoin ${body.available_pcoin}.`);
      setConfirm(false);
      setAmount("");
      setQuote(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The conversion was rejected");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="coin-hero">
        <p className="coin-kicker">PCoin to USDT TRC20</p>
        <p className="text-2xl font-semibold mt-1">{rules?.label || "1000 PCoin = 1 USDT TRC20"}</p>
        <p className="text-sm text-muted mt-2">{rules?.detail}</p>
      </section>
      {error ? <p className="text-loss">{error}</p> : null}
      {notice ? <p className="text-profit">{notice}</p> : null}
      <form className="coin-panel grid gap-3 max-w-xl" onSubmit={submit}>
        <p className="text-sm text-muted">Available {quote?.available_pcoin || "—"} PCoin. Minimum {rules?.min_pcoin || "1000"}. Maximum {rules?.max_pcoin === "0" ? "none" : rules?.max_pcoin}. Fee {rules?.fee_bps || 0} bps.</p>
        <input value={amount} onChange={(event) => { setAmount(event.target.value); setConfirm(false); }} placeholder="PCoin to convert" required />
        <div className="coin-grid">
          <div className="coin-stat"><span>USDT you receive</span><strong className="num">{quote ? quote.usdt : "—"}</strong></div>
          <div className="coin-stat"><span>PCoin plus fee</span><strong className="num">{quote ? quote.total_pcoin : "—"}</strong></div>
        </div>
        {confirm && quote ? <p className="text-sm">Convert {quote.pcoin} PCoin into {quote.usdt} USDT TRC20 on the default wallet at {quote.rate} PCoin per USDT?</p> : null}
        <button className="primary" type="submit" disabled={busy || !rules?.enabled}>{busy ? "Converting…" : confirm ? "Confirm conversion" : "Review conversion"}</button>
        {rules && !rules.enabled ? <p className="text-sm text-loss">Conversion is turned off.</p> : null}
      </form>
    </>
  );
}
