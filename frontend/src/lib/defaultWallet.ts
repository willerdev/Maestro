import { apiJson } from "@/lib/api";

type WalletChoice = { configured: boolean; wallet: string; provider?: string };

export function publicWalletLabel(provider?: string | null, wallet?: string | null) {
  if (wallet === "hosted" || !provider || provider === "nowpayments") return "Default wallet";
  return provider;
}

export function keepDefaultWallet() {
  return apiJson<WalletChoice>("/api/v1/payments/provider").catch(() => ({ configured: false, wallet: "hosted" }));
}
