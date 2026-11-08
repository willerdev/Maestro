"use client";

import { PageTitle } from "@/components/Shell";
import { AssetPanel } from "@/components/AssetPanel";

export default function AssetsPage() {
  return (
    <div className="max-w-4xl">
      <PageTitle title="Assets" detail="Crypto held in the default wallet for this login." />
      <AssetPanel />
    </div>
  );
}
