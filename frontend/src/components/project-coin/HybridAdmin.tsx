"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import type { HybridPlan } from "@/lib/coin";

type Settings = { paused: boolean; base_daily_pcoin: string; default_duration_days: number; max_multiplier: string };
type Overview = {
  settings: Settings;
  free_miners: number;
  premium_miners: number;
  pcoin_issued_premium: string;
  pcoin_issued_pow: string;
  pcoin_issued_total: string;
  today: { premium: string; pow: string; total: string };
  week: { premium: string; pow: string; total: string };
  month: { premium: string; pow: string; total: string };
  purchases: { reference: string; plan: string; amount: string; status: string; method: string; created_at: string }[];
};
type Miners = {
  premium: Miner[];
  free: Miner[];
};
type Miner = { user_id: string; email: string; plan: string; multiplier: string; expires_at: string; premium: string; mining: string };
type Flag = { email: string; credited_today: string; expected_today: string; reason: string };

export function HybridAdmin() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [plans, setPlans] = useState<HybridPlan[]>([]);
  const [miners, setMiners] = useState<Miners | null>(null);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function load() {
    Promise.all([
      apiJson<Overview>("/api/v1/chain/mining/admin/overview"),
      apiJson<HybridPlan[]>("/api/v1/chain/mining/admin/plans"),
      apiJson<Miners>("/api/v1/chain/mining/admin/miners"),
      apiJson<Flag[]>("/api/v1/chain/mining/admin/suspicious"),
    ]).then(([body, rows, people, alerts]) => {
      setOverview(body);
      setSettings(body.settings);
      setPlans(rows);
      setMiners(people);
      setFlags(alerts);
      setError("");
    }).catch((err: Error) => setError(err.message));
  }

  useEffect(() => { load(); }, []);

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) return;
    try {
      const saved = await apiJson<Settings>("/api/v1/chain/mining/admin/settings", { method: "PUT", body: JSON.stringify(settings) });
      setSettings(saved);
      setNotice("Mining economics saved. Free proof-of-work parameters stay on the server environment.");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Settings were not saved");
    }
  }

  async function savePlan(plan: HybridPlan) {
    try {
      await apiJson(`/api/v1/chain/mining/admin/plans/${plan.id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: plan.name,
          price: plan.price,
          multiplier: plan.multiplier,
          duration_days: plan.duration_days,
          daily_limit: plan.daily_limit,
          benefits: plan.benefits,
          enabled: plan.enabled,
        }),
      });
      setNotice(`${plan.name} saved.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The plan was not saved");
    }
  }

  if (!overview && error) return <p className="text-loss">{error}</p>;
  if (!overview || !settings) return <p className="text-muted">Loading hybrid mining…</p>;

  return (
    <div className="flex flex-col gap-4 mt-8">
      <header>
        <h2 className="text-xl font-semibold">Hybrid mining</h2>
        <p className="text-sm text-muted">Free proof-of-work is unchanged. These controls only affect paid multipliers, prices, and the extra PCoin that accrues while a session is running.</p>
      </header>
      {error ? <p className="text-loss">{error}</p> : null}
      {notice ? <p className="text-profit">{notice}</p> : null}
      <div className="coin-grid">
        <div className="coin-stat"><span>Free miners</span><strong>{overview.free_miners}</strong></div>
        <div className="coin-stat"><span>Premium miners</span><strong>{overview.premium_miners}</strong></div>
        <div className="coin-stat"><span>PoW issued</span><strong className="num">{overview.pcoin_issued_pow}</strong></div>
        <div className="coin-stat"><span>Premium issued</span><strong className="num">{overview.pcoin_issued_premium}</strong></div>
        <div className="coin-stat"><span>Today</span><strong className="num">{overview.today.total}</strong></div>
        <div className="coin-stat"><span>Week</span><strong className="num">{overview.week.total}</strong></div>
        <div className="coin-stat"><span>Month</span><strong className="num">{overview.month.total}</strong></div>
        <div className="coin-stat"><span>Total issued</span><strong className="num">{overview.pcoin_issued_total}</strong></div>
      </div>
      <form className="coin-panel grid sm:grid-cols-2 gap-3" onSubmit={saveSettings}>
        <label className="text-sm">Base daily PCoin (display + premium extra)
          <input className="block mt-1 w-full" value={settings.base_daily_pcoin} onChange={(event) => setSettings({ ...settings, base_daily_pcoin: event.target.value })} required />
        </label>
        <label className="text-sm">Default duration (days)
          <input className="block mt-1 w-full" value={settings.default_duration_days} onChange={(event) => setSettings({ ...settings, default_duration_days: Number(event.target.value) })} required />
        </label>
        <label className="text-sm">Maximum multiplier
          <input className="block mt-1 w-full" value={settings.max_multiplier} onChange={(event) => setSettings({ ...settings, max_multiplier: event.target.value })} required />
        </label>
        <label className="text-sm flex items-center gap-2 mt-6">
          <input type="checkbox" checked={settings.paused} onChange={(event) => setSettings({ ...settings, paused: event.target.checked })} />
          Pause mining globally
        </label>
        <div className="coin-actions">
          <button className="primary" type="submit">Save mining economics</button>
        </div>
      </form>
      <section className="coin-panel overflow-x-auto">
        <h3 className="font-semibold mb-2">Plans</h3>
        <table className="coin-table">
          <thead><tr><th>Name</th><th>Price</th><th>Multiplier</th><th>Days</th><th>Daily cap</th><th>On</th><th></th></tr></thead>
          <tbody>
            {plans.map((plan, index) => (
              <tr key={plan.id}>
                <td><input value={plan.name} onChange={(event) => setPlans(plans.map((row, i) => i === index ? { ...row, name: event.target.value } : row))} /></td>
                <td><input className="num w-20" value={plan.price} disabled={plan.free} onChange={(event) => setPlans(plans.map((row, i) => i === index ? { ...row, price: event.target.value } : row))} /></td>
                <td><input className="num w-16" value={plan.multiplier} onChange={(event) => setPlans(plans.map((row, i) => i === index ? { ...row, multiplier: event.target.value } : row))} /></td>
                <td><input className="num w-16" value={plan.duration_days} disabled={plan.free} onChange={(event) => setPlans(plans.map((row, i) => i === index ? { ...row, duration_days: Number(event.target.value) } : row))} /></td>
                <td><input className="num w-16" value={plan.daily_limit} onChange={(event) => setPlans(plans.map((row, i) => i === index ? { ...row, daily_limit: event.target.value } : row))} /></td>
                <td><input type="checkbox" checked={plan.enabled} disabled={plan.free} onChange={(event) => setPlans(plans.map((row, i) => i === index ? { ...row, enabled: event.target.checked } : row))} /></td>
                <td><button type="button" onClick={() => savePlan(plan)}>Save</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="coin-panel overflow-x-auto">
        <h3 className="font-semibold mb-2">Premium miners</h3>
        <MinerTable rows={miners?.premium || []} empty="No paid upgrades are active." />
      </section>
      <section className="coin-panel overflow-x-auto">
        <h3 className="font-semibold mb-2">Free miners</h3>
        <MinerTable rows={miners?.free || []} empty="No free miners with a Project Coin wallet." />
      </section>
      <section className="coin-panel overflow-x-auto">
        <h3 className="font-semibold mb-2">Upgrade purchases</h3>
        <table className="coin-table">
          <thead><tr><th>When</th><th>Plan</th><th>Amount</th><th>Method</th><th>Status</th><th>Reference</th></tr></thead>
          <tbody>
            {overview.purchases.map((row) => (
              <tr key={row.reference}>
                <td>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td>
                <td>{row.plan}</td>
                <td className="num">{row.amount}</td>
                <td>{row.method}</td>
                <td>{row.status}</td>
                <td className="num">{row.reference}</td>
              </tr>
            ))}
            {overview.purchases.length === 0 ? <tr><td colSpan={6}>No upgrade payments yet.</td></tr> : null}
          </tbody>
        </table>
      </section>
      <section className="coin-panel overflow-x-auto">
        <h3 className="font-semibold mb-2">Suspicious premium activity</h3>
        <table className="coin-table">
          <thead><tr><th>Account</th><th>Credited</th><th>Expected</th><th>Why</th></tr></thead>
          <tbody>
            {flags.map((row) => (
              <tr key={row.email}><td>{row.email}</td><td className="num">{row.credited_today}</td><td className="num">{row.expected_today}</td><td>{row.reason}</td></tr>
            ))}
            {flags.length === 0 ? <tr><td colSpan={4}>No premium credits above 1.5x the configured daily extra.</td></tr> : null}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function MinerTable({ rows, empty }: { rows: Miner[]; empty: string }) {
  return (
    <table className="coin-table">
      <thead><tr><th>Account</th><th>Plan</th><th>Rate</th><th>Mining</th><th>Premium</th><th>Expires</th></tr></thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.user_id}>
            <td>{row.email}</td>
            <td>{row.plan}</td>
            <td>{row.multiplier}x</td>
            <td>{row.mining}</td>
            <td className="num">{row.premium}</td>
            <td>{row.expires_at ? new Date(row.expires_at).toLocaleString() : "—"}</td>
          </tr>
        ))}
        {rows.length === 0 ? <tr><td colSpan={6}>{empty}</td></tr> : null}
      </tbody>
    </table>
  );
}
