"use client";

import type { MiningComputer, MiningMinerGroup } from "@/lib/coin";

export function ComputersPanel({
  computers,
  groups,
  symbol = "PCOIN",
}: {
  computers?: MiningComputer[];
  groups?: MiningMinerGroup[];
  symbol?: string;
}) {
  const own = computers || [];
  const miners = groups || [];
  if (own.length === 0 && miners.length === 0) {
    return (
      <section className="coin-panel">
        <h2 className="font-semibold mb-2">Mining computers</h2>
        <p className="text-sm text-muted">Open Project Coin on another computer with this login to see it here, including identity and how much it is making.</p>
      </section>
    );
  }
  return (
    <section className="coin-panel overflow-x-auto">
      <h2 className="font-semibold mb-2">Mining computers</h2>
      <p className="text-sm text-muted mb-3">Each computer that signs in with this account is listed separately, with its identity and earnings.</p>
      {miners.length > 0
        ? miners.map((group) => (
            <div key={group.user_id} className="mb-4">
              <h3 className="text-sm font-semibold mb-1">{group.full_name ? `${group.full_name} · ${group.email}` : group.email}</h3>
              <ComputerTable rows={group.computers} symbol={symbol} />
            </div>
          ))
        : <ComputerTable rows={own} symbol={symbol} />}
    </section>
  );
}

function ComputerTable({ rows, symbol }: { rows: MiningComputer[]; symbol: string }) {
  return (
    <table className="coin-table">
      <thead>
        <tr>
          <th>Computer</th>
          <th>Status</th>
          <th>Hash rate</th>
          <th>Proof-of-work</th>
          <th>Premium</th>
          <th>Making</th>
          <th>Last seen</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              {row.label}
              {row.this_computer ? <span className="text-muted"> · this computer</span> : null}
            </td>
            <td className={`coin-status ${row.status === "running" ? "run" : ""} ${row.status === "paused" ? "pause" : ""}`}>{row.status}</td>
            <td className="num">{row.hashrate} H/s</td>
            <td className="num">{row.pow_mined} {symbol}</td>
            <td className="num">{row.premium} {symbol}</td>
            <td className="num">{row.earned} {symbol}</td>
            <td>{row.last_seen ? new Date(row.last_seen).toLocaleString() : "—"}</td>
          </tr>
        ))}
        {rows.length === 0 ? <tr><td colSpan={7}>No computers on this login yet.</td></tr> : null}
      </tbody>
    </table>
  );
}
