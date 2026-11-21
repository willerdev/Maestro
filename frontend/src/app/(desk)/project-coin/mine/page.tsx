"use client";

import { useEffect, useState } from "react";
import { HashChart } from "@/components/project-coin/CoinCharts";
import { ComputersPanel } from "@/components/project-coin/ComputersPanel";
import { apiJson } from "@/lib/api";
import { Dashboard, MiningMinerGroup } from "@/lib/coin";

export default function MiningPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [miners, setMiners] = useState<MiningMinerGroup[]>([]);
  const [error, setError] = useState("");
  const [cpu, setCpu] = useState(20);
  const mining = data?.mining;
  const running = mining?.status === "running";
  const paused = mining?.status === "paused";

  useEffect(() => {
    let stop = false;
    function load() {
      Promise.all([
        apiJson<Dashboard>("/api/v1/chain/dashboard?span=24h"),
        apiJson<{ miners: MiningMinerGroup[] }>("/api/v1/chain/mining/computers?everyone=1").catch(() => ({ miners: [] as MiningMinerGroup[] })),
      ])
        .then(([body, roster]) => {
          if (stop) return;
          setData(body);
          setMiners(roster.miners || []);
          if (body.mining.cpu_percent) setCpu(body.mining.cpu_percent);
          setError("");
        })
        .catch((err: Error) => { if (!stop) setError(err.message); });
    }
    load();
    const timer = window.setInterval(load, 2000);
    return () => { stop = true; window.clearInterval(timer); };
  }, []);

  async function act(path: string, body?: object) {
    setError("");
    try {
      await apiJson(path, { method: "POST", body: JSON.stringify(body || {}) });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mining did not change");
    }
  }

  return (
    <>
      <section className="coin-hero">
        <p className="coin-kicker">Live hash rate</p>
        <p className="coin-live num">{mining ? mining.hashrate : 0} H/s</p>
        <p className={`coin-status ${running ? "run" : ""} ${paused ? "pause" : ""}`}><i />{mining?.status || "stopped"}</p>
        <p className="text-sm text-muted mt-2">Hash rate is this server’s CPU while mining is on. Outside miners cannot connect.</p>
        {mining?.hybrid?.plan ? <p className="text-sm mt-2">{mining.hybrid.plan.name} · {mining.hybrid.multiplier}x · ~{mining.hybrid.speed_daily} PCoin/day{mining.hybrid.expires_at ? ` · ends ${new Date(mining.hybrid.expires_at).toLocaleString()}` : ""}</p> : null}
      </section>
      {error ? <p className="text-loss">{error}</p> : null}
      <div className="coin-actions">
        <button className="primary" type="button" disabled={running || paused} onClick={() => act("/api/v1/chain/mining/start", { cpu_percent: cpu })}>Start mining</button>
        <button className="primary" type="button" disabled={!running && !paused} onClick={() => act("/api/v1/chain/mining/stop")}>Stop mining</button>
        <button className="primary" type="button" disabled={!running} onClick={() => act("/api/v1/chain/mining/pause")}>Pause mining</button>
        <button className="primary" type="button" disabled={!paused} onClick={() => act("/api/v1/chain/mining/resume")}>Resume mining</button>
      </div>
      <section className="coin-panel grid sm:grid-cols-[1fr_auto] gap-3 items-end">
        <label className="text-sm">CPU limit {cpu}%
          <input className="block mt-2 w-full" type="range" min={5} max={50} value={cpu} onChange={(event) => setCpu(Number(event.target.value))} />
        </label>
        <button className="primary" type="button" onClick={() => act("/api/v1/chain/mining/cpu", { cpu_percent: cpu })}>Save limit</button>
      </section>
      <div className="coin-grid">
        <Stat label="Current block" value={mining?.current_block == null ? "—" : String(mining.current_block)} />
        <Stat label="Duration" value={mining ? `${mining.duration_seconds}s` : "—"} />
        <Stat label="Latest block" value={mining?.last_block_hash ? mining.last_block_hash.slice(0, 18) : "—"} />
        <Stat label="Latest reward" value={mining ? `${mining.last_reward} ${mining.symbol}` : "—"} />
        <Stat label="Total hashes" value={mining ? String(mining.hashes) : "—"} />
        <Stat label="Accepted" value={mining ? String(mining.success) : "—"} />
        <Stat label="Rejected" value={mining ? String(mining.failed) : "—"} />
        <Stat label="Difficulty" value={mining ? String(mining.difficulty) : "—"} />
      </div>
      <ComputersPanel computers={miners.length ? undefined : mining?.computers} groups={miners.length ? miners : undefined} symbol={mining?.symbol} />
      <section className="coin-panel">
        <h2 className="font-semibold mb-2">Hash rate</h2>
        <HashChart rows={mining?.hashrate_samples || data?.series.hashrate || []} />
      </section>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="coin-stat"><span>{label}</span><strong className="num">{value}</strong></div>;
}
