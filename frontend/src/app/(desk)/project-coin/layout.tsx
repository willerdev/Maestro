"use client";

import { CoinNav } from "@/components/project-coin/CoinNav";

export default function ProjectCoinLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="coin-app max-w-6xl">
      <CoinNav />
      {children}
    </div>
  );
}
