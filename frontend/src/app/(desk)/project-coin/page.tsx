"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type Wallet = {
  address: string;
  public_key: string;
  available: string;
  pending: string;
  mined: string;
  received: string;
  sent: string;
  symbol: string;
};

type Status = {
  status: string;
  hashrate: number;
  hashes: number;
  duration_seconds: number;
  difficulty: number;
  height: number;
  current_block: number | null;
  success: number;
  failed: number;
  blocks_mined: number;
  rewards: string;
  cpu_percent: number;
  last_block_hash: string;
  last_reward: string;
  network_hashrate: number;
  network_scope: string;
  symbol: string;
  history?: { height: number; hash: string; reward: string; hashes: number; found_at: string }[];
};

export default function ProjectCoinPage() {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [missing, setMissing] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState("");
  const [importKey, setImportKey] = useState("");
  const [exported, setExported] = useState("");

  const load = useCallback(async () => {
    try {
      const [view, live, stats] = await Promise.all([
        apiJson<Wallet>("/api/v1/chain/wallet"),
        apiJson<Status>("/api/v1/chain/mining/status"),
        apiJson<Status>("/api/v1/chain/mining/statistics"),
      ]);
      setWallet(view);
      setStatus({ ...live, history: stats.history || [] });
      setMissing(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "The chain could not be read";
      if (message.includes("Create a Project Coin wallet")) {
        setMissing(true);
        setWallet(null);
        const live = await apiJson<Status>("/api/v1/chain/mining/status").catch(() => null);
        setStatus(live);
      } else {
        setError(message);
      }
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function act(path: string, body?: object) {
    setError("");
    setNotice("");
    try {
      await apiJson(path, { method: "POST", body: JSON.stringify(body || {}) });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed");
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    await act("/api/v1/chain/wallet/send", { recipient, amount });
    setAmount("");
  }

  const symbol = wallet?.symbol || status?.symbol || "PCOIN";
  const running = status?.status === "running";
  const paused = status?.status === "paused";

  return (
    <div className="max-w-5xl">
      <PageTitle title="Project Coin" detail="Maestro's own proof-of-work coin on this server. This is a single node, not the Bitcoin network and not the external mining payout page." />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {notice ? <p className="text-profit mb-3">{notice}</p> : null}
      {missing ? (
        <section className="border border-line bg-panel rounded-lg px-4 py-4 mb-4 grid gap-3">
          <h2 className="text-lg font-semibold">Create a wallet</h2>
          <p className="text-sm text-muted">The private key is encrypted on the server. It is not shown after creation.</p>
          <button className="primary" type="button" onClick={() => act("/api/v1/chain/wallet")}>Create wallet</button>
          <form className="grid gap-2" onSubmit={(event) => { event.preventDefault(); act("/api/v1/chain/wallet/import", { private_key: importKey }); }}>
            <input value={importKey} onChange={(event) => setImportKey(event.target.value)} placeholder="Import a private key" type="password" autoComplete="off" />
            <button className="primary" type="submit">Import wallet</button>
          </form>
        </section>
      ) : null}
      {wallet && status ? (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            <Stat label="Available" value={`${wallet.available} ${symbol}`} />
            <Stat label="Mined" value={`${wallet.mined} ${symbol}`} />
            <Stat label="Hash rate" value={`${status.hashrate} H/s`} />
            <Stat label="Difficulty" value={String(status.difficulty)} />
            <Stat label="Block height" value={String(status.height)} />
            <Stat label="Status" value={status.status} />
            <Stat label="This node" value={`${status.network_hashrate} H/s`} />
            <Stat label="Blocks mined" value={String(status.blocks_mined)} />
          </div>
          <section className="border border-line bg-panel rounded-lg px-4 py-4 mb-4">
            <h2 className="text-lg font-semibold mb-3">Mining</h2>
            <div className="flex flex-wrap gap-2 mb-4">
              <button className="primary" type="button" disabled={running || paused} onClick={() => act("/api/v1/chain/mining/start", {})}>Start mining</button>
              <button className="primary" type="button" disabled={!running && !paused} onClick={() => act("/api/v1/chain/mining/stop")}>Stop mining</button>
              <button className="primary" type="button" disabled={!running} onClick={() => act("/api/v1/chain/mining/pause")}>Pause mining</button>
              <button className="primary" type="button" disabled={!paused} onClick={() => act("/api/v1/chain/mining/resume")}>Resume mining</button>
            </div>
            <div className="grid sm:grid-cols-2 gap-2 text-sm text-muted">
              <p>Current block: {status.current_block ?? "—"}</p>
              <p>Hashes: {status.hashes}</p>
              <p>Latest block: <span className="num break-all">{status.last_block_hash || "—"}</span></p>
              <p>Time mining: {status.duration_seconds}s</p>
              <p>Latest reward: {status.last_reward} {symbol}</p>
              <p>Rewards earned: {status.rewards} {symbol}</p>
              <p>Successful blocks: {status.success}</p>
              <p>Rejected attempts: {status.failed}</p>
              <p>CPU cap: {status.cpu_percent || 20}%</p>
              <p>Network scope: {status.network_scope}</p>
            </div>
            <p className="text-sm mt-3"><Link className="text-accent" href="/project-coin/explorer">Open the block explorer</Link></p>
          </section>
          <section className="border border-line bg-panel rounded-lg px-4 py-4 mb-4 grid gap-2">
            <h2 className="text-lg font-semibold">Wallet</h2>
            <p className="text-sm num break-all">{wallet.address}</p>
            <p className="text-sm text-muted">Pending incoming {wallet.pending} · Received {wallet.received} · Sent {wallet.sent}</p>
            <form className="grid sm:grid-cols-3 gap-2" onSubmit={send}>
              <input value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="Recipient address" required />
              <input value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="Amount" required />
              <button className="primary" type="submit">Send</button>
            </form>
            <button className="primary" type="button" onClick={async () => {
              setExported("");
              try {
                const body = await apiJson<{ private_key: string }>("/api/v1/chain/wallet/export", { method: "POST", body: JSON.stringify({ confirm: true }) });
                setExported(body.private_key);
              } catch (err) {
                setError(err instanceof Error ? err.message : "The key was not exported");
              }
            }}>Export private key</button>
            {exported ? <p className="text-sm text-loss num break-all">Copy this key now. It is not stored in the page after you leave. {exported}</p> : null}
          </section>
          <section className="border border-line bg-panel rounded-lg px-4 py-4">
            <h2 className="text-lg font-semibold mb-2">Mining history</h2>
            <table className="w-full text-sm">
              <thead className="text-left text-muted"><tr><th className="py-2">Height</th><th>Reward</th><th>Hashes</th><th>When</th></tr></thead>
              <tbody>
                {(status.history || []).map((hit) => (
                  <tr key={hit.hash} className="border-t border-line">
                    <td className="py-2">{hit.height}</td>
                    <td className="num">{hit.reward}</td>
                    <td className="num">{hit.hashes}</td>
                    <td>{new Date(hit.found_at).toLocaleString()}</td>
                  </tr>
                ))}
                {(status.history || []).length === 0 ? <tr><td className="py-3 text-muted" colSpan={4}>No blocks from this wallet yet.</td></tr> : null}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-line bg-panel rounded-lg px-3 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-lg font-semibold num break-all">{value}</p>
    </div>
  );
}
