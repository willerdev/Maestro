"use client";

import { useEffect, useState } from "react";
import { BalanceChart, BlockChart, HashChart, RewardChart } from "@/components/project-coin/CoinCharts";
import { apiJson } from "@/lib/api";
import { Dashboard } from "@/lib/coin";

const RANGES = ["24h", "7d", "30d", "all"] as const;

export default function AnalyticsPage() {
  const [span, setSpan] = useState<(typeof RANGES)[number]>("7d");
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    apiJson<Dashboard>(`/api/v1/chain/dashboard?span=${span}`).then(setData).catch((err: Error) => setError(err.message));
  }, [span]);
  return (
    <>
      <div className="coin-actions">
        {RANGES.map((item) => (
          <button key={item} className={span === item ? "primary" : ""} type="button" onClick={() => setSpan(item)}>{item === "all" ? "All time" : item}</button>
        ))}
      </div>
      {error ? <p className="text-loss">{error}</p> : null}
      <section className="coin-panel"><h2 className="font-semibold mb-2">Mining rewards</h2><RewardChart rows={data?.series.rewards || []} /></section>
      <section className="coin-panel"><h2 className="font-semibold mb-2">Hash rate</h2><HashChart rows={data?.series.hashrate || []} /></section>
      <section className="coin-panel"><h2 className="font-semibold mb-2">Blocks mined per day</h2><BlockChart rows={data?.series.blocks_per_day || []} /></section>
      <section className="coin-panel"><h2 className="font-semibold mb-2">Balance growth</h2><BalanceChart rows={data?.series.balance || []} /></section>
    </>
  );
}
