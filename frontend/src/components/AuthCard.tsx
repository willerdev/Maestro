"use client";

import { ThemeToggle } from "@/components/ThemeToggle";

export function AuthCard({ title, error, children }: { title: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen grid place-items-center px-4">
      <div className="w-full max-w-md bg-panel border border-line rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="text-xs tracking-[0.18em] text-muted">MAESTRO</div>
          <ThemeToggle />
        </div>
        <h1 className="text-2xl font-semibold mb-4">{title}</h1>
        {error ? <p className="text-loss text-sm mb-3">{error}</p> : null}
        {children}
      </div>
    </div>
  );
}
