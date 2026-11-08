export type CoinWallet = {
  address: string;
  public_key: string;
  available: string;
  confirmed: string;
  pending: string;
  pending_rewards: string;
  mined: string;
  premium_available?: string;
  pow_mined?: string;
  received: string;
  sent: string;
  withdrawn: string;
  lifetime_earnings: string;
  converted?: string;
  usdt_available?: string;
  usdt_total?: string;
  exchange_label?: string;
  symbol: string;
  market_value: null;
  confirmation_rule: string;
  coin: { name: string; symbol: string; fee: string; difficulty: number; max_supply: string; initial_reward: string };
};

export type HybridPlan = {
  id: string;
  code: string;
  name: string;
  price: string;
  currency: string;
  multiplier: string;
  duration_days: number;
  daily_limit: string;
  benefits: string;
  enabled: boolean;
  base_daily: string;
  speed_daily: string;
  extra_daily: string;
  active: boolean;
  free: boolean;
};

export type HybridView = {
  paused: boolean;
  plan: HybridPlan | null;
  multiplier: string;
  base_daily: string;
  speed_daily: string;
  mining: string;
  expires_at: string;
  premium_available: string;
  premium_lifetime: string;
  today_premium: string;
  week_premium: string;
  month_premium: string;
  today_pow: string;
  today_total: string;
  week_total: string;
  month_total: string;
  detail: string;
  purchases: { reference: string; plan: string; amount: string; status: string; method: string; created_at: string; invoice_url: string }[];
  rewards: { amount: string; kind: string; multiplier: string; created_at: string; note: string }[];
};

export type MiningView = {
  status: string;
  hashrate: number;
  hashes: number;
  duration_seconds: number;
  difficulty: number;
  height: number;
  current_block: number | null;
  success: number;
  failed: number;
  blocks_mined: number;
  rewards: string;
  cpu_percent: number;
  last_block_hash: string;
  last_reward: string;
  network_hashrate: number;
  network_scope: string;
  symbol: string;
  hashrate_samples: { t: number; hashrate: number }[];
  coin: { name: string; symbol: string; fee: string; difficulty: number; max_supply: string; initial_reward: string };
  hybrid?: HybridView;
};

export type Dashboard = {
  span: string;
  market_value: null;
  market_value_label: string;
  network_mode: string;
  network_detail: string;
  wallet: CoinWallet | null;
  mining: MiningView;
  hybrid?: HybridView;
  rewards: { height: number; hash: string; reward: string; timestamp: number; status: string; tx_hash: string; confirmations: number }[];
  series: {
    rewards: { t: number; amount: string }[];
    hashrate: { t: number; hashrate: number }[];
    blocks_per_day: { day: string; count: number }[];
    balance: { t: number; balance: string }[];
  };
};

export type ActivityItem = {
  tx_hash: string;
  type: string;
  kind: string;
  amount: string;
  fee: string;
  sender: string;
  recipient: string;
  block_height: number | null;
  timestamp: number | null;
  status: string;
  confirmations: number;
};

export function when(stamp: number | null) {
  if (!stamp) return "Pending";
  return new Date(stamp * 1000).toLocaleString();
}

export function typeLabel(type: string) {
  if (type === "mining_reward") return "Mining reward";
  if (type === "incoming") return "Incoming transfer";
  if (type === "outgoing") return "Outgoing transfer";
  if (type === "network_fee") return "Network fee";
  return type;
}
