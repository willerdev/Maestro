"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import type { HybridPlan, HybridView } from "@/lib/coin";

type Purchase = {
  activated: boolean;
  status: string;
  invoice_url: string;
  invoice?: { invoice_url?: string; status?: string };
  upgrade?: { plan: string; multiplier: string; ends_at: string };
};

export default function MiningPlansPage() {
  const [plans, setPlans] = useState<HybridPlan[]>([]);
  const [hybrid, setHybrid] = useState<HybridView | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<HybridPlan | null>(null);
  const [busy, setBusy] = useState("");

  function load() {
    Promise.all([apiJson<HybridPlan[]>("/api/v1/chain/mining/plans"), apiJson<HybridView>("/api/v1/chain/mining/hybrid")])
      .then(([rows, overview]) => {
        setPlans(rows);
        setHybrid(overview);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, []);

  async function buy(plan: HybridPlan, method: "wallet" | "invoice") {
    setBusy(`${plan.id}-${method}`);
    setError("");
    setNotice("");
    try {
      const result = await apiJson<Purchase>("/api/v1/chain/mining/upgrades", {
        method: "POST",
        body: JSON.stringify({ plan_id: plan.id, method }),
      });
      setPending(null);
      if (result.activated) {
        setNotice(`${result.upgrade?.plan || plan.name} is active at ${result.upgrade?.multiplier || plan.multiplier}x. Extra PCoin starts while mining is running.`);
      } else if (result.invoice_url || result.invoice?.invoice_url) {
        const url = result.invoice_url || result.invoice?.invoice_url || "";
        setNotice("Invoice opened. The upgrade activates only after the payment is confirmed on the server.");
        if (url) window.open(url, "_blank", "noopener");
      } else {
        setNotice("Payment is waiting. The upgrade is not active yet.");
      }
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The upgrade was not purchased");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <header className="coin-hero">
        <p className="coin-kicker">Mining plans</p>
        <p className="coin-balance">{hybrid?.plan?.name || "Free Miner"}</p>
        <p className="text-sm text-muted">{hybrid?.detail}</p>
        <p className="text-sm mt-2">Current speed {hybrid?.speed_daily || "10"} PCoin/day at {hybrid?.multiplier || "1"}x. Extra PCoin is not USDT until you convert it.</p>
      </header>
      {error ? <p className="text-loss">{error}</p> : null}
      {notice ? <p className="text-profit">{notice}</p> : null}
      {hybrid?.paused ? <p className="text-warn">Mining is paused. Free proof-of-work and premium extras are both stopped for new sessions.</p> : null}
      <div className="plan-grid">
        {plans.map((plan) => (
          <article key={plan.id} className={`plan-card ${plan.active ? "on" : ""} ${plan.free ? "free" : ""}`}>
            <p className="coin-kicker">{plan.active ? "Active plan" : plan.free ? "Included" : "Upgrade"}</p>
            <h2>{plan.name}</h2>
            <p className="plan-price num">{plan.free ? "$0" : `$${trim(plan.price)}`}</p>
            <p className="text-sm">{plan.multiplier}x · ~{plan.speed_daily} PCoin/day</p>
            <p className="text-sm text-muted mt-2">{plan.benefits}</p>
            <ul className="text-sm mt-3">
              <li>Multiplier {plan.multiplier}x</li>
              <li>Speed ~{plan.speed_daily} PCoin/day</li>
              <li>{plan.duration_days ? `${plan.duration_days} day duration` : "No expiry"}</li>
              {plan.daily_limit !== "0" ? <li>Daily premium cap {plan.daily_limit} PCoin</li> : <li>No extra daily cap</li>}
            </ul>
            {plan.free || plan.active ? (
              <p className="text-sm text-muted mt-3">{plan.active ? "This is your current plan." : "No purchase required."}</p>
            ) : (
              <div className="coin-actions mt-3">
                <button className="primary" type="button" onClick={() => setPending(plan)}>Upgrade</button>
              </div>
            )}
          </article>
        ))}
        {plans.length === 0 ? <p className="text-muted">Loading plans…</p> : null}
      </div>
      <section className="coin-panel">
        <h2 className="font-semibold mb-2">Upgrade history</h2>
        <table className="coin-table">
          <thead><tr><th>When</th><th>Plan</th><th>Amount</th><th>Method</th><th>Status</th></tr></thead>
          <tbody>
            {(hybrid?.purchases || []).map((row) => (
              <tr key={row.reference}>
                <td>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td>
                <td>{row.plan}</td>
                <td className="num">{row.amount}</td>
                <td>{row.method}</td>
                <td>{row.status}{row.invoice_url ? <> · <a className="text-accent" href={row.invoice_url} target="_blank" rel="noreferrer">Invoice</a></> : null}</td>
              </tr>
            ))}
            {(hybrid?.purchases || []).length === 0 ? <tr><td colSpan={5}>No upgrade purchases yet. Free mining continues without one.</td></tr> : null}
          </tbody>
        </table>
      </section>
      {pending ? (
        <div className="plan-modal" role="dialog" aria-modal="true" aria-labelledby="upgrade-title">
          <div className="coin-panel plan-dialog">
            <h2 id="upgrade-title">Upgrade to {pending.name}</h2>
            <p className="text-sm mt-2">Pay ${trim(pending.price)} USDT for {pending.multiplier}x mining. The plan {pending.duration_days ? `lasts ${pending.duration_days} days` : "does not expire"}. Extra PCoin accrues only while mining is running. A browser success message cannot activate the plan.</p>
            <div className="coin-actions mt-4">
              <button className="primary" type="button" disabled={Boolean(busy)} onClick={() => buy(pending, "wallet")}>{busy.endsWith("wallet") ? "Debiting…" : "Pay from wallet"}</button>
              <button type="button" disabled={Boolean(busy)} onClick={() => buy(pending, "invoice")}>{busy.endsWith("invoice") ? "Opening…" : "Open invoice"}</button>
              <button type="button" onClick={() => setPending(null)}>Cancel</button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function trim(value: string) {
  return value.replace(/\.?0+$/, "");
}
