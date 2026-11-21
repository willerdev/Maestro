"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export type PocketInfo = {
  mode: "demo" | "real" | string;
  platform?: string;
  platform_label?: string;
  has_demo: boolean;
  has_real: boolean;
  demo_balance?: string | null;
  real_balance?: string | null;
  demo_currency?: string;
  real_currency?: string;
};

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  );
}

function Icon({ name }: { name: "demo" | "real" | "plug" | "unplug" | "refresh" | "eye" | "eyeOff" | "shield" | "trash" }) {
  if (name === "demo") return <Svg><path {...stroke} d="M9 3h6l1 7a4 4 0 1 1-8 0zM10 3v3M14 3v3" /></Svg>;
  if (name === "real") return <Svg><path {...stroke} d="M4 10h16v9H4zM7 10V8a5 5 0 0 1 10 0v2M8 15h3" /></Svg>;
  if (name === "plug") return <Svg><path {...stroke} d="M9 7v4M15 7v4M8 11h8v3a4 4 0 0 1-8 0zM12 18v3" /></Svg>;
  if (name === "unplug") return <Svg><path {...stroke} d="M9 3v4M15 3v4M8 7h8v3a4 4 0 0 1-3 3.9M12 18v3M5 19l14-14" /></Svg>;
  if (name === "refresh") return <Svg><path {...stroke} d="M20 6v6h-6M4 18v-6h6M20 12a8 8 0 0 0-14.3-4M4 12a8 8 0 0 0 14.3 4" /></Svg>;
  if (name === "eye") return <Svg><path {...stroke} d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" /><circle {...stroke} cx="12" cy="12" r="3" /></Svg>;
  if (name === "eyeOff") return <Svg><path {...stroke} d="M3 3l18 18M10.6 10.6A3 3 0 0 0 12 15a3 3 0 0 0 2.4-1.2M6.1 6.4C3.7 8 2 12 2 12s4 7 10 7a11 11 0 0 0 5.2-1.3M9.9 5.2A11 11 0 0 1 12 5c6 0 10 7 10 7a18 18 0 0 1-1.8 2.6" /></Svg>;
  if (name === "shield") return <Svg><path {...stroke} d="M12 3l8 3v6c0 5-3.4 8-8 9-4.6-1-8-4-8-9V6z" /></Svg>;
  return <Svg><path {...stroke} d="M5 7h14M9 7V5h6v2M8 7l1 13h6l1-13" /></Svg>;
}

function Tool({
  label,
  onClick,
  href,
  kind = "",
  active = false,
}: {
  label: string;
  onClick?: () => void;
  href?: string;
  kind?: string;
  active?: boolean;
}) {
  const icon = (
    label === "Connect" ? "plug" :
    label === "Disconnect" ? "unplug" :
    label === "Test connection" ? "refresh" :
    label === "Watch" ? "eye" :
    label === "Pause watch" ? "eyeOff" : "trash"
  ) as "plug" | "unplug" | "refresh" | "eye" | "eyeOff" | "shield" | "trash";
  const className = `icon-btn ${kind} ${active ? "on" : ""}`.trim();
  if (href) {
    return (
      <Link className={className} href={href} title={label} aria-label={label}>
        <Icon name={icon} />
      </Link>
    );
  }
  return (
    <button type="button" className={className} title={label} aria-label={label} onClick={onClick}>
      <Icon name={icon} />
    </button>
  );
}

export function PocketModeSwitch({
  mode,
  onMode,
  demoBalance,
  realBalance,
  demoDisabled = false,
  realDisabled = false,
}: {
  mode: "demo" | "real" | "";
  onMode: (mode: "demo" | "real") => void;
  demoBalance?: string | null;
  realBalance?: string | null;
  demoDisabled?: boolean;
  realDisabled?: boolean;
}) {
  return (
    <div className="mode-switch" role="group" aria-label="Demo or Real">
      <button
        type="button"
        className={`demo ${mode === "demo" ? "on" : ""}`}
        disabled={demoDisabled}
        title="Demo book"
        onClick={() => onMode("demo")}
      >
        <Icon name="demo" />
        <span>Demo</span>
        {demoBalance ? <b className="num">{demoBalance}</b> : null}
      </button>
      <button
        type="button"
        className={`real ${mode === "real" ? "on" : ""}`}
        disabled={realDisabled}
        title="Real book"
        onClick={() => onMode("real")}
      >
        <Icon name="real" />
        <span>Real</span>
        {realBalance ? <b className="num">{realBalance}</b> : null}
      </button>
    </div>
  );
}

export function AccountToolbar({
  accountId,
  monitoring,
  pocket,
  onAct,
  onDelete,
  onMode,
}: {
  accountId: string;
  monitoring: boolean;
  pocket?: PocketInfo | null;
  onAct: (path: string, body?: object) => void;
  onDelete: () => void;
  onMode?: (mode: "demo" | "real") => void;
}) {
  const mode = pocket?.mode === "demo" ? "demo" : "real";
  const locked = !pocket?.has_demo && !pocket?.has_real;
  return (
    <div className="desk-toolbar">
      {pocket ? (
        <PocketModeSwitch
          mode={mode}
          onMode={(next) => next !== mode && onMode?.(next)}
          demoBalance={pocket.demo_balance}
          realBalance={pocket.real_balance}
          demoDisabled={locked}
          realDisabled={locked}
        />
      ) : null}
      <div className="icon-tools">
        <Tool label="Connect" onClick={() => onAct(`/api/v1/accounts/${accountId}/connect`)} />
        <Tool label="Disconnect" onClick={() => onAct(`/api/v1/accounts/${accountId}/disconnect`)} />
        <Tool label="Test connection" onClick={() => onAct(`/api/v1/accounts/${accountId}/test-connection`)} />
        <Tool
          label={monitoring ? "Pause watch" : "Watch"}
          active={monitoring}
          onClick={() => onAct(`/api/v1/accounts/${accountId}/monitoring`, { enabled: !monitoring })}
        />
        <Tool label="Delete" kind="danger" onClick={onDelete} />
      </div>
    </div>
  );
}
