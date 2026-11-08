"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { CoinWallet, Dashboard } from "@/lib/coin";

export default function CoinSettingsPage() {
  const [wallet, setWallet] = useState<CoinWallet | null>(null);
  const [coin, setCoin] = useState<Dashboard["mining"]["coin"] | null>(null);
  const [importKey, setImportKey] = useState("");
  const [cpu, setCpu] = useState(20);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function load() {
    apiJson<Dashboard>("/api/v1/chain/dashboard")
      .then((body) => {
        setWallet(body.wallet);
        setCoin(body.mining.coin);
        if (body.mining.cpu_percent) setCpu(body.mining.cpu_percent);
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => { load(); }, []);

  async function create() {
    setError("");
    try {
      const body = await apiJson<CoinWallet>("/api/v1/chain/wallet", { method: "POST", body: "{}" });
      setWallet(body);
      setNotice("Wallet created. The private key stays encrypted on the server and is not shown.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The wallet was not created");
    }
  }

  async function importWallet(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const body = await apiJson<CoinWallet>("/api/v1/chain/wallet/import", { method: "POST", body: JSON.stringify({ private_key: importKey.trim() }) });
      setWallet(body);
      setImportKey("");
      setNotice("Wallet imported. The key is encrypted and is not shown again.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The key was not imported");
    }
  }

  async function saveCpu() {
    setError("");
    try {
      await apiJson("/api/v1/chain/mining/cpu", { method: "POST", body: JSON.stringify({ cpu_percent: cpu }) });
      setNotice("CPU limit saved. It applies on the next mining round.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The limit was not saved");
    }
  }

  return (
    <>
      {error ? <p className="text-loss">{error}</p> : null}
      {notice ? <p className="text-profit">{notice}</p> : null}
      <section className="coin-panel grid gap-2">
        <h2 className="font-semibold">Wallet</h2>
        {wallet ? <p className="num break-all text-sm">{wallet.address}</p> : <button className="primary" type="button" onClick={create}>Create wallet</button>}
        {!wallet ? (
          <form className="grid gap-2" onSubmit={importWallet}>
            <input value={importKey} onChange={(event) => setImportKey(event.target.value)} type="password" placeholder="Import private key" autoComplete="off" />
            <button className="primary" type="submit">Import wallet</button>
          </form>
        ) : <p className="text-sm text-muted">The private key is not shown on this page.</p>}
      </section>
      <section className="coin-panel grid gap-2">
        <h2 className="font-semibold">Mining limit</h2>
        <label className="text-sm">CPU cap {cpu}%
          <input className="block mt-2 w-full" type="range" min={5} max={50} value={cpu} onChange={(event) => setCpu(Number(event.target.value))} />
        </label>
        <button className="primary" type="button" onClick={saveCpu}>Save CPU limit</button>
      </section>
      {coin ? (
        <section className="coin-panel text-sm text-muted">
          <h2 className="font-semibold text-ink mb-2">Chain rules</h2>
          <p>{coin.name} ({coin.symbol}). These values come from the server and are not edited here.</p>
          <p className="mt-2">Maximum supply {coin.max_supply}. Initial reward {coin.initial_reward}. Fee {coin.fee}. Difficulty {coin.difficulty}.</p>
        </section>
      ) : null}
    </>
  );
}
