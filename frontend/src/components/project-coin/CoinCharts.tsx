"use client";

import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function stamp(value: number) {
  return new Date(value * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function RewardChart({ rows }: { rows: { t: number; amount: string }[] }) {
  const data = rows.map((row) => ({ label: stamp(row.t), amount: Number(row.amount) }));
  if (!data.length) return <p className="text-sm text-muted">No mining rewards in this range.</p>;
  return (
    <div style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer>
        <LineChart data={data}>
          <XAxis dataKey="label" stroke="currentColor" fontSize={11} />
          <YAxis stroke="currentColor" fontSize={11} width={48} />
          <Tooltip />
          <Line type="monotone" dataKey="amount" name="PCOIN" stroke="var(--accent)" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function HashChart({ rows }: { rows: { t: number; hashrate: number }[] }) {
  const data = rows.map((row) => ({ label: new Date(row.t * 1000).toLocaleTimeString(), hashrate: row.hashrate }));
  if (!data.length) return <p className="text-sm text-muted">Hash rate appears here while this server is mining. Nothing is estimated.</p>;
  return (
    <div style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer>
        <LineChart data={data}>
          <XAxis dataKey="label" stroke="currentColor" fontSize={11} />
          <YAxis stroke="currentColor" fontSize={11} width={48} />
          <Tooltip />
          <Line type="monotone" dataKey="hashrate" name="H/s" stroke="var(--accent)" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BlockChart({ rows }: { rows: { day: string; count: number }[] }) {
  if (!rows.length) return <p className="text-sm text-muted">No blocks mined in this range.</p>;
  return (
    <div style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer>
        <BarChart data={rows}>
          <XAxis dataKey="day" stroke="currentColor" fontSize={11} />
          <YAxis stroke="currentColor" fontSize={11} allowDecimals={false} width={32} />
          <Tooltip />
          <Bar dataKey="count" name="Blocks" fill="var(--accent)" radius={4} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BalanceChart({ rows }: { rows: { t: number; balance: string }[] }) {
  const data = rows.map((row) => ({ label: stamp(row.t), balance: Number(row.balance) }));
  if (!data.length) return <p className="text-sm text-muted">No balance movement in this range.</p>;
  return (
    <div style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer>
        <LineChart data={data}>
          <XAxis dataKey="label" stroke="currentColor" fontSize={11} />
          <YAxis stroke="currentColor" fontSize={11} width={48} />
          <Tooltip />
          <Line type="monotone" dataKey="balance" name="PCOIN" stroke="var(--accent)" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
