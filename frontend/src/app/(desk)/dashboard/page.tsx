"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { DailyPnlChart, DrawdownChart, EquityChart, ExposureChart, FrequencyChart, UtilizationChart, WinLossChart } from "@/components/Charts";
import { PageTitle } from "@/components/Shell";
import { apiJson, deviceId, isSystemAdmin, type User } from "@/lib/api";
import { keepDefaultWallet } from "@/lib/defaultWallet";

type Operating = {
  required: boolean;
  allowed: boolean;
  licensed?: boolean;
  funded?: boolean;
  mining_allowed?: boolean;
  reason?: string;
};
type Summary = Record<string, string | number>;
type Charts = {
  equity: { t: string; equity: string }[];
  drawdown: { t: string; drawdown: string }[];
  daily_pnl: { date: string; pnl: string }[];
  trade_frequency: { bucket: string; count: number }[];
  risk_utilization: { account: string; percent: string }[];
  exposure: { symbol: string; notional: string }[];
  win_loss: { wins: number; losses: number };
};

const TILES: [string, string][] = [
  ["total_accounts", "Total accounts"],
  ["connected_accounts", "Connected"],
  ["total_balance", "Total balance"],
  ["total_equity", "Total equity"],
  ["total_open_risk", "Open risk"],
  ["today_pl", "Today P/L"],
  ["today_loss", "Today loss"],
  ["current_drawdown", "Current drawdown %"],
  ["max_drawdown", "Max drawdown %"],
  ["open_positions", "Open positions"],
  ["trades_today", "Trades today"],
  ["risk_violations", "Risk violations"],
  ["account_health", "Account health"],
];

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [charts, setCharts] = useState<Charts | null>(null);
  const [error, setError] = useState("");
  const [paymentNeeded, setPaymentNeeded] = useState(false);
  const [operating, setOperating] = useState<Operating | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [licenseBusy, setLicenseBusy] = useState(false);
  const [licenseError, setLicenseError] = useState("");
  const own = me ? !isSystemAdmin(me.roles) : true;

  useEffect(() => {
    apiJson<User>("/api/v1/auth/me").then(setMe).catch(() => undefined);
    keepDefaultWallet()
      .then((body) => setPaymentNeeded(!body.configured && body.wallet !== "hosted"))
      .catch(() => setPaymentNeeded(false));
    apiJson<Operating>("/api/v1/operating-status")
      .then(setOperating)
      .catch(() => undefined);
    Promise.all([apiJson<Summary>("/api/v1/dashboard/summary"), apiJson<Charts>("/api/v1/dashboard/charts")])
      .then(([sum, chart]) => {
        setSummary(sum);
        setCharts(chart);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function activateLicense(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const code = String(new FormData(form).get("code") || "").trim();
    setLicenseError("");
    setLicenseBusy(true);
    try {
      await apiJson("/api/v1/licenses/activate", {
        method: "POST",
        body: JSON.stringify({ code, device_id: deviceId() }),
      });
      form.reset();
      window.location.reload();
    } catch (err) {
      setLicenseError(err instanceof Error ? err.message : "License could not be activated");
    } finally {
      setLicenseBusy(false);
    }
  }

  return (
    <div>
      <PageTitle title="Dashboard" detail={own ? "Your accounts, balances, and risk on this login." : "Risk picture across the accounts on this desk."} />
      {error ? <p className="text-loss">{error}</p> : null}
      {operating?.required ? (
        <section className="mb-4 border border-line bg-panel rounded-lg px-4 py-4">
          <h2 className="font-semibold mb-1">Operating balance</h2>
          {operating.licensed ? (
            <p className="text-sm text-muted mb-2">This computer is licensed.</p>
          ) : (
            <form className="flex flex-col gap-2 mb-3 max-w-md" onSubmit={activateLicense}>
              <label className="label" htmlFor="license-code">License key</label>
              <input id="license-code" name="code" autoComplete="off" placeholder="MAE-XXXX-XXXX-XXXX" required />
              <button className="primary" type="submit" disabled={licenseBusy}>{licenseBusy ? "Activating…" : "Activate license"}</button>
              {licenseError ? <p className="text-sm text-loss">{licenseError}</p> : <p className="text-xs text-muted">One key works on this computer only. It cannot be used on another computer after activation.</p>}
            </form>
          )}
          {operating.funded ? (
            <p className="text-sm text-muted">Deposit a minimum of $500.</p>
          ) : (
            <p className="text-sm text-loss">
              Deposit a minimum of $500 to operate. <Link className="text-accent" href="/wallet">Open wallet</Link>
            </p>
          )}
          {!operating.funded ? (
            <p className="text-sm mt-2">Project Coin can be added without that deposit. Other account types stay closed until the wallet has $500. <Link className="text-accent" href="/accounts/new">Add Project Coin</Link></p>
          ) : null}
        </section>
      ) : null}
      {paymentNeeded ? (
        <p className="mb-4 text-sm border border-line bg-panel rounded-lg px-3 py-3">
          Default self-hosted wallet is the payment wallet. <Link className="text-accent" href="/payments">Open payment settings</Link>.
        </p>
      ) : null}
      <>
          <section className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 mb-6">
            {TILES.map(([key, label]) => (
              <article key={key} className="bg-panel border border-line rounded-lg px-3 py-3">
                <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
                <div className={`num text-lg mt-1 ${tone(key, summary?.[key])}`}>{summary ? String(summary[key]) : "—"}</div>
              </article>
            ))}
          </section>
          {charts ? (
            <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <EquityChart data={charts.equity} />
              <DrawdownChart data={charts.drawdown} />
              <DailyPnlChart data={charts.daily_pnl} />
              <FrequencyChart data={charts.trade_frequency} />
              <UtilizationChart data={charts.risk_utilization} />
              <ExposureChart data={charts.exposure} />
              <WinLossChart wins={charts.win_loss.wins} losses={charts.win_loss.losses} />
            </section>
          ) : null}
        </>
    </div>
  );
}

function tone(key: string, value: string | number | undefined) {
  if (value === undefined) return "";
  if (key === "today_pl") return Number(value) < 0 ? "text-loss" : "text-profit";
  if (key === "account_health") {
    if (value === "CRITICAL" || value === "HIGH_RISK") return "text-loss";
    if (value === "WARNING") return "text-warn";
    if (value === "HEALTHY") return "text-profit";
  }
  return "";
}
