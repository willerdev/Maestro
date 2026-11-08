"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiJson, isSystemAdmin, type User } from "@/lib/api";

const LINKS: [string, string][] = [
  ["/project-coin", "Dashboard"],
  ["/project-coin/mine", "Mining"],
  ["/project-coin/plans", "Plans"],
  ["/project-coin/wallet", "Wallet"],
  ["/project-coin/convert", "Convert"],
  ["/project-coin/rates", "Rates"],
  ["/project-coin/transactions", "Transactions"],
  ["/project-coin/explorer", "Explorer"],
  ["/project-coin/network", "Network"],
  ["/project-coin/analytics", "Analytics"],
  ["/project-coin/settings", "Settings"],
];

export function CoinNav() {
  const path = usePathname();
  const [showRates, setShowRates] = useState(false);

  useEffect(() => {
    apiJson<User>("/api/v1/auth/me")
      .then((me) => setShowRates(isSystemAdmin(me.roles)))
      .catch(() => undefined);
  }, []);

  return (
    <nav className="coin-nav" aria-label="Project Coin">
      {LINKS.filter(([href]) => href !== "/project-coin/rates" || showRates).map(([href, label]) => {
        const on = href === "/project-coin" ? path === href : path.startsWith(href);
        return <Link key={href} href={href} className={on ? "on" : ""}>{label}</Link>;
      })}
    </nav>
  );
}
