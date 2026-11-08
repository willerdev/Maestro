import { apiJson } from "@/lib/api";

type WalletChoice = { configured: boolean; wallet: string; provider?: string };

export function keepDefaultWallet() {
  return apiJson<WalletChoice>("/api/v1/payments/provider").then((current) => {
    if (current.configured || current.wallet === "hosted") return current;
    return apiJson<WalletChoice>("/api/v1/payments/provider", {
      method: "PUT",
      body: JSON.stringify({ provider: "nowpayments", wallet: "hosted", sandbox: false, credentials: {} }),
    });
  });
}
