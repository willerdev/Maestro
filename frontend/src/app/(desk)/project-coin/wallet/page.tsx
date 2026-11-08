"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { apiJson } from "@/lib/api";
import { ActivityItem, CoinWallet, typeLabel, when } from "@/lib/coin";

export default function CoinWalletPage() {
  const [wallet, setWallet] = useState<CoinWallet | null>(null);
  const [missing, setMissing] = useState(false);
  const [rows, setRows] = useState<ActivityItem[]>([]);
  const [mode, setMode] = useState<"receive" | "send" | "">("");
  const [qr, setQr] = useState("");
  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const panel = useRef<HTMLElement | null>(null);

  function load() {
    apiJson<CoinWallet>("/api/v1/chain/wallet")
      .then((body) => {
        setWallet(body);
        setMissing(false);
        return apiJson<{ items: ActivityItem[] }>("/api/v1/chain/activity?limit=8");
      })
      .then((body) => { if (body) setRows(body.items); })
      .catch((err: Error) => {
        if (err.message.includes("Create a Project Coin wallet")) setMissing(true);
        else setError(err.message);
      });
  }

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (mode === "receive" && wallet) {
      QRCode.toDataURL(wallet.address, { margin: 1, width: 180 }).then(setQr).catch(() => setQr(""));
    }
    if (mode) panel.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [mode, wallet]);

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!confirm) {
      setConfirm(true);
      return;
    }
    setError("");
    try {
      await apiJson("/api/v1/chain/wallet/send", {
        method: "POST",
        body: JSON.stringify({ recipient: recipient.trim(), amount: amount.trim() }),
      });
      setNotice("Transfer submitted. It stays pending until a block includes it.");
      setConfirm(false);
      setAmount("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The transfer was rejected");
    }
  }

  if (missing) return <p>Create a wallet in <Link className="text-accent" href="/project-coin/settings">Settings</Link>.</p>;
  if (!wallet) return error ? <p className="text-loss">{error}</p> : <p className="text-muted">Loading wallet…</p>;
  const fee = wallet.coin.fee;
  const total = amount ? `${amount} plus a ${fee} ${wallet.symbol} fee` : `Amount plus a ${fee} ${wallet.symbol} fee`;

  return (
    <>
      <section className="coin-hero">
        <p className="coin-kicker">Available</p>
        <p className="coin-balance num">{wallet.available} {wallet.symbol}</p>
        <p className="text-sm num break-all">{wallet.address}</p>
        <div className="coin-actions mt-3">
          <button className="primary" type="button" onClick={() => navigator.clipboard.writeText(wallet.address).then(() => setNotice("Address copied."), () => setError("The address could not be copied."))}>Copy address</button>
          <button className="primary" type="button" onClick={() => { setMode("receive"); setError(""); }}>Receive</button>
          <button className="primary" type="button" onClick={() => { setMode("send"); setConfirm(false); setError(""); }}>Send</button>
        </div>
      </section>
      {error ? <p className="text-loss">{error}</p> : null}
      {notice ? <p className="text-profit">{notice}</p> : null}
      {mode === "receive" ? (
        <section className="coin-panel" ref={(node) => { panel.current = node; }}>
          <h2 className="font-semibold mb-2">Receive {wallet.symbol}</h2>
          <p className="text-sm text-muted mb-3">Share this address. Coins arrive after the sender’s transfer is included in a block.</p>
          {qr ? <img className="coin-qr" src={qr} alt="Wallet address QR code" /> : null}
          <p className="num break-all mt-3 text-sm">{wallet.address}</p>
        </section>
      ) : null}
      {mode === "send" ? (
        <form className="coin-panel grid gap-3" ref={(node) => { panel.current = node; }} onSubmit={send}>
          <h2 className="font-semibold">Send {wallet.symbol}</h2>
          {Number(wallet.available) <= 0 ? <p className="text-sm text-muted">There is no spendable {wallet.symbol} yet. Mine a block first, then send to another Project Coin address.</p> : null}
          <input value={recipient} onChange={(event) => { setRecipient(event.target.value); setConfirm(false); }} placeholder="Recipient address, pcoin1…" required />
          <input value={amount} onChange={(event) => { setAmount(event.target.value); setConfirm(false); }} placeholder="Amount" required />
          <p className="text-sm text-muted">Network fee {fee} {wallet.symbol}. Total {total}. You cannot send to your own address.</p>
          {confirm ? <p className="text-sm">Send {amount} {wallet.symbol} to {recipient.trim()}? The fee is added on top.</p> : null}
          <button className="primary" type="submit" disabled={Number(wallet.available) <= 0}>{confirm ? "Confirm send" : "Review transfer"}</button>
        </form>
      ) : null}
      <div className="coin-grid">
        <Stat label="Pending" value={`${wallet.pending} ${wallet.symbol}`} />
        <Stat label="Lifetime earnings" value={`${wallet.lifetime_earnings} ${wallet.symbol}`} />
        <Stat label="Received" value={`${wallet.received} ${wallet.symbol}`} />
        <Stat label="Sent" value={`${wallet.sent} ${wallet.symbol}`} />
        <Stat label="Converted" value={`${wallet.converted || "0"} ${wallet.symbol}`} />
        <Stat label="USDT available" value={`${wallet.usdt_available || "0"} USDT`} />
        <Stat label="USDT from conversion" value={`${wallet.usdt_total || "0"} USDT`} />
        <Stat label="Exchange rate" value={wallet.exchange_label || "1000 PCoin = 1 USDT"} />
      </div>
      <p className="text-sm"><Link className="text-accent" href="/project-coin/convert">Convert PCoin to USDT</Link></p>
      <p className="text-sm text-muted">USDT shown here is an internal balance. It is not a blockchain token and cannot be withdrawn.</p>
      <p className="text-sm text-muted">{wallet.confirmation_rule}</p>
      <section className="coin-panel">
        <h2 className="font-semibold mb-2">Recent activity</h2>
        <Activity rows={rows} />
        <p className="text-sm mt-2"><Link className="text-accent" href="/project-coin/transactions">Full history</Link></p>
      </section>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="coin-stat"><span>{label}</span><strong className="num">{value}</strong></div>;
}

export function Activity({ rows }: { rows: ActivityItem[] }) {
  return (
    <table className="coin-table">
      <thead><tr><th>Type</th><th>Amount</th><th>Status</th><th>When</th></tr></thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${row.tx_hash}-${row.type}-${index}`}>
            <td>{typeLabel(row.type)}</td>
            <td className="num">{row.amount}</td>
            <td>{row.status}</td>
            <td>{when(row.timestamp)}</td>
          </tr>
        ))}
        {rows.length === 0 ? <tr><td colSpan={4}>No transactions yet.</td></tr> : null}
      </tbody>
    </table>
  );
}
