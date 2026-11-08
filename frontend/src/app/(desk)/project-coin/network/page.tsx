"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Network = {
  mode: string;
  decentralized: boolean;
  detail: string;
  node_id: string;
  peers: unknown[];
  height: number;
  difficulty: number;
  work: number;
  coin: { name: string; symbol: string; max_supply: string; initial_reward: string; fee: string; consensus: string; hash: string };
};

export default function NetworkPage() {
  const [data, setData] = useState<Network | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    apiJson<Network>("/api/v1/chain/network/status").then(setData).catch((err: Error) => setError(err.message));
  }, []);
  if (error) return <p className="text-loss">{error}</p>;
  if (!data) return <p className="text-muted">Loading network…</p>;
  return (
    <>
      <section className="coin-hero">
        <p className="coin-kicker">This server</p>
        <p className="text-2xl font-semibold mt-1">Single node</p>
        <p className="text-sm text-muted mt-2">{data.detail}</p>
      </section>
      <div className="coin-grid">
        <Stat label="Mode" value={data.mode} />
        <Stat label="Public network" value={data.decentralized ? "Yes" : "No"} />
        <Stat label="Peers" value={String(data.peers.length)} />
        <Stat label="Height" value={String(data.height)} />
        <Stat label="Difficulty" value={String(data.difficulty)} />
        <Stat label="Work" value={String(data.work)} />
        <Stat label="Coin" value={`${data.coin.name} (${data.coin.symbol})`} />
        <Stat label="Supply cap" value={data.coin.max_supply} />
      </div>
      <section className="coin-panel text-sm">
        <p>Node {data.node_id}</p>
        <p className="text-muted mt-2">Consensus {data.coin.consensus}. Hash {data.coin.hash}. Block reward starts at {data.coin.initial_reward}. Transfer fee {data.coin.fee}.</p>
      </section>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="coin-stat"><span>{label}</span><strong className="num">{value}</strong></div>;
}
