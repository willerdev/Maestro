"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import { EXTRA_WALLETS, ExtraWallet, ExtraWalletId, connectExtraWallet } from "@/lib/extraWallets";

type Saved = {
  id: ExtraWalletId;
  label: string;
  address: string;
  source: string;
  configured: boolean;
  has_key: boolean;
};

export function ExtraWallets({ onConnected }: { onConnected?: (row: ExtraWallet) => void }) {
  const [rows, setRows] = useState<Saved[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState<ExtraWalletId | "">("");
  const [keyText, setKeyText] = useState("");
  const [addressText, setAddressText] = useState("");

  function load() {
    return apiJson<Saved[]>("/api/v1/wallets/extra").then(setRows).catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function connect(id: ExtraWalletId) {
    setError("");
    setBusy(id);
    try {
      const row = await connectExtraWallet(id);
      onConnected?.(row);
      await apiJson(`/api/v1/wallets/extra/${id}`, { method: "PUT", body: JSON.stringify({ address: row.address }) });
      await load();
    } catch (err) {
      const saved = rows.find((row) => row.id === id && row.configured);
      if (saved?.address) {
        onConnected?.({ id, label: saved.label, address: saved.address, connectedAt: new Date().toISOString() });
        setError("");
      } else {
        setError(err instanceof Error ? err.message : "The wallet did not connect");
        setOpen(id);
      }
    } finally {
      setBusy("");
    }
  }

  async function save(event: FormEvent<HTMLFormElement>, id: ExtraWalletId) {
    event.preventDefault();
    setError("");
    setBusy(id);
    try {
      const body = await apiJson<Saved>(`/api/v1/wallets/extra/${id}`, {
        method: "PUT",
        body: JSON.stringify({ private_key: keyText, address: addressText }),
      });
      setKeyText("");
      setAddressText("");
      setOpen("");
      await load();
      if (body.address) onConnected?.({ id, label: body.label, address: body.address, connectedAt: new Date().toISOString() });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The wallet was not saved");
    } finally {
      setBusy("");
    }
  }

  async function forget(id: ExtraWalletId) {
    setError("");
    try {
      await apiJson(`/api/v1/wallets/extra/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The wallet was not removed");
    }
  }

  return (
    <section className="border border-line bg-panel rounded-lg px-4 py-4 mb-8">
      <h2 className="font-semibold mb-1">Extra wallets</h2>
      <p className="text-sm text-muted mb-3">Ledger, Binance, Bybit, and OKX sit beside the default self-hosted wallet. Connecting one does not replace it. Use the browser wallet, or save a private key or public address for Binance, Bybit, and OKX. The key is stored encrypted and is never shown again. Ledger stays on the device.</p>
      {error ? <p className="text-sm text-loss mb-3">{error}</p> : null}
      <div className="grid sm:grid-cols-2 gap-2">
        {EXTRA_WALLETS.map((item) => {
          const saved = rows.find((row) => row.id === item.id);
          const configurable = item.id !== "ledger";
          return (
            <div key={item.id} className="border border-line rounded-lg px-3 py-3">
              <strong>{item.label}</strong>
              {saved?.configured ? (
                <>
                  <p className="num break-all text-sm mt-1">{saved.address}</p>
                  <p className="text-xs text-muted mt-1">{saved.has_key ? "Configured with an encrypted key" : saved.source === "address" ? "Configured with a public address" : "Connected"}</p>
                </>
              ) : <p className="text-sm text-muted mt-1">Not connected</p>}
              <div className="flex flex-wrap gap-2 mt-2">
                <button className="primary" type="button" disabled={busy === item.id} onClick={() => connect(item.id)}>{saved?.configured ? "Reconnect" : "Connect"}</button>
                {configurable ? <button className="ghost" type="button" onClick={() => { setOpen(open === item.id ? "" : item.id); setError(""); }}>{open === item.id ? "Close" : "Configure"}</button> : null}
                {saved?.configured ? <button className="ghost" type="button" onClick={() => forget(item.id)}>Remove</button> : null}
              </div>
              {open === item.id && configurable ? (
                <form className="grid gap-2 mt-3" onSubmit={(event) => save(event, item.id)}>
                  <input type="password" value={keyText} onChange={(event) => setKeyText(event.target.value)} placeholder="Private key, 64 hex characters" autoComplete="off" />
                  <input value={addressText} onChange={(event) => setAddressText(event.target.value)} placeholder="Public address, optional if the key is set" autoComplete="off" />
                  <button className="primary" type="submit" disabled={busy === item.id}>Save configuration</button>
                </form>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
