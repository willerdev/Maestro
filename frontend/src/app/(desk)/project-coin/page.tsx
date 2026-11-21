"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BalanceChart, BlockChart, HashChart, RewardChart } from "@/components/project-coin/CoinCharts";
import { ComputersPanel } from "@/components/project-coin/ComputersPanel";
import { apiJson } from "@/lib/api";
import { Dashboard, MiningMinerGroup, when } from "@/lib/coin";

const RANGES = ["24h", "7d", "30d", "all"] as const;

export default function ProjectCoinDashboard() {
  const [span, setSpan] = useState<(typeof RANGES)[number]>("all");
  const [data, setData] = useState<Dashboard | null>(null);
  const [miners, setMiners] = useState<MiningMinerGroup[]>([]);
  const [error, setError] = useState("");
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    let stop = false;
    function load() {
      Promise.all([
        apiJson<Dashboard>(`/api/v1/chain/dashboard?span=${span}`),
        apiJson<{ miners: MiningMinerGroup[] }>("/api/v1/chain/mining/computers?everyone=1").catch(() => ({ miners: [] as MiningMinerGroup[] })),
      ])
        .then(([body, roster]) => {
          if (stop) return;
          setData(body);
          setMiners(roster.miners || []);
          setError("");
        })
        .catch((err: Error) => { if (!stop) setError(err.message); });
    }
    load();
    const timer = window.setInterval(load, 3000);
    return () => { stop = true; window.clearInterval(timer); };
  }, [span]);

  useEffect(() => {
    setAccepted(sessionStorage.getItem("maestro-account-terms") === "mining");
  }, []);

  const wallet = data?.wallet;
  const mining = data?.mining;
  const hybrid = data?.hybrid;
  const symbol = wallet?.symbol || mining?.symbol || "PCOIN";

  return (
    <>
      <header className="coin-hero">
        <p className="coin-kicker">Available balance</p>
        <p className="coin-balance num">{wallet ? `${wallet.available} ${symbol}` : "No wallet"}</p>
        <p className="text-sm text-muted">{data?.network_detail}</p>
        <div className="flex gap-2 mt-3">
          {RANGES.map((item) => (
            <button key={item} className={item === span ? "primary" : ""} type="button" onClick={() => setSpan(item)}>{item === "all" ? "All time" : item}</button>
          ))}
        </div>
      </header>
      {accepted ? <p className="text-sm text-profit">Terms accepted. Project Coin is on the running account list.</p> : null}
      {error ? <p className="text-loss">{error}</p> : null}
      {!wallet ? <p className="text-sm">Create a wallet in <Link className="text-accent" href="/project-coin/settings">Settings</Link> before mining.</p> : null}
      {hybrid ? (
        <section className="coin-panel mb-3">
          <p className="coin-kicker">Active plan</p>
          <p className="font-semibold">{hybrid.plan?.name || "Free Miner"} · {hybrid.multiplier}x · ~{hybrid.speed_daily} PCoin/day</p>
          <p className="text-sm text-muted mt-1">{hybrid.mining === "running" ? "Mining is running." : "Mining is stopped."} {hybrid.expires_at ? `Plan ends ${new Date(hybrid.expires_at).toLocaleString()}.` : "Free mining has no expiry."} <Link className="text-accent" href="/project-coin/plans">Compare plans</Link></p>
        </section>
      ) : null}
      <div className="coin-grid">
        <Stat label="Available PCoin" value={wallet ? `${wallet.available} ${symbol}` : "—"} />
        <Stat label="Proof-of-work mined" value={wallet ? `${wallet.pow_mined || wallet.mined} ${symbol}` : "—"} />
        <Stat label="Premium extra" value={hybrid ? `${hybrid.premium_available} ${symbol}` : "—"} />
        <Stat label="Pending transfers" value={wallet ? `${wallet.pending} ${symbol}` : "—"} />
        <Stat label="Today mined" value={hybrid ? `${hybrid.today_total} ${symbol}` : "—"} />
        <Stat label="Lifetime mined" value={wallet ? `${wallet.mined} ${symbol}` : "—"} />
        <Stat label="USDT wallet" value={wallet?.usdt_available ? `${wallet.usdt_available} USDT` : "—"} />
        <Stat label="Withdrawn / sent" value={wallet ? `${wallet.withdrawn} ${symbol}` : "—"} />
        <Stat label="Week mined" value={hybrid ? `${hybrid.week_total} ${symbol}` : "—"} />
        <Stat label="Month mined" value={hybrid ? `${hybrid.month_total} ${symbol}` : "—"} />
        <Stat label="Hash rate" value={mining ? `${mining.hashrate} H/s` : "—"} />
        <Stat label="Mining" value={mining?.status || "—"} />
        <Stat label="Height" value={mining ? String(mining.height) : "—"} />
        <Stat label="Blocks mined" value={mining ? String(mining.blocks_mined) : "—"} />
        <Stat label="Difficulty" value={mining ? String(mining.difficulty) : "—"} />
        <Stat label="CPU cap" value={mining ? `${mining.cpu_percent || 0}%` : "—"} />
        <Stat label="Mining time" value={mining ? `${mining.duration_seconds}s` : "—"} />
        <Stat label="Accepted blocks" value={mining ? String(mining.success) : "—"} />
        <Stat label="Rejected attempts" value={mining ? String(mining.failed) : "—"} />
      </div>
      {wallet ? <p className="text-sm text-muted">{wallet.confirmation_rule}</p> : null}
      <ComputersPanel computers={miners.length ? undefined : data?.mining?.computers} groups={miners.length ? miners : undefined} symbol={symbol} />
      <div className="grid lg:grid-cols-2 gap-3">
        <section className="coin-panel"><h2 className="font-semibold mb-2">Rewards</h2><RewardChart rows={data?.series.rewards || []} /></section>
        <section className="coin-panel"><h2 className="font-semibold mb-2">Hash rate</h2><HashChart rows={data?.series.hashrate || []} /></section>
        <section className="coin-panel"><h2 className="font-semibold mb-2">Blocks mined</h2><BlockChart rows={data?.series.blocks_per_day || []} /></section>
        <section className="coin-panel"><h2 className="font-semibold mb-2">Balance</h2><BalanceChart rows={data?.series.balance || []} /></section>
      </div>
      {hybrid?.rewards?.length ? (
        <section className="coin-panel">
          <h2 className="font-semibold mb-2">Premium extras</h2>
          <table className="coin-table">
            <thead><tr><th>When</th><th>Amount</th><th>Multiplier</th><th>Note</th></tr></thead>
            <tbody>
              {hybrid.rewards.map((row) => (
                <tr key={row.created_at + row.amount}><td>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td><td className="num">{row.amount}</td><td>{row.multiplier}x</td><td>{row.note}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
      <section className="coin-panel">
        <h2 className="font-semibold mb-2">Recent rewards</h2>
        <table className="coin-table">
          <thead><tr><th>Height</th><th>Reward</th><th>Status</th><th>When</th></tr></thead>
          <tbody>
            {(data?.rewards || []).slice(0, 8).map((row) => (
              <tr key={row.tx_hash}><td>{row.height}</td><td className="num">{row.reward}</td><td>{row.status} · {row.confirmations}</td><td>{when(row.timestamp)}</td></tr>
            ))}
            {(data?.rewards || []).length === 0 ? <tr><td colSpan={4}>No confirmed rewards in this range.</td></tr> : null}
          </tbody>
        </table>
      </section>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="coin-stat"><span>{label}</span><strong className="num">{value}</strong></div>;
}
