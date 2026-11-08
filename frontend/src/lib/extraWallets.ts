export type ExtraWalletId = "ledger" | "binance" | "bybit" | "okx";

export type ExtraWallet = {
  id: ExtraWalletId;
  label: string;
  address: string;
  connectedAt: string;
};

const STORAGE = "maestro-extra-wallets";

export const EXTRA_WALLETS: { id: ExtraWalletId; label: string; install: string }[] = [
  { id: "ledger", label: "Ledger Nano", install: "https://www.ledger.com/ledger-live" },
  { id: "binance", label: "Binance Web3 Wallet", install: "https://www.binance.com/en/web3wallet" },
  { id: "bybit", label: "Bybit Wallet", install: "https://www.bybit.com/web3" },
  { id: "okx", label: "OKX Wallet", install: "https://www.okx.com/web3" },
];

type Eip1193 = { request: (args: { method: string; params?: unknown[] }) => Promise<unknown> };

type HidDevice = {
  opened: boolean;
  open: () => Promise<void>;
  sendReport: (reportId: number, data: Uint8Array) => Promise<void>;
  addEventListener: (type: "inputreport", listener: (event: { data: DataView }) => void) => void;
  removeEventListener: (type: "inputreport", listener: (event: { data: DataView }) => void) => void;
};

function readStore(): ExtraWallet[] {
  try {
    const raw = localStorage.getItem(STORAGE);
    const rows = raw ? JSON.parse(raw) : [];
    return Array.isArray(rows) ? rows.filter((row) => row && typeof row.address === "string" && typeof row.id === "string") : [];
  } catch {
    return [];
  }
}

export function loadExtraWallets(): ExtraWallet[] {
  if (typeof window === "undefined") return [];
  return readStore();
}

export function forgetExtraWallet(id: ExtraWalletId) {
  localStorage.setItem(STORAGE, JSON.stringify(readStore().filter((row) => row.id !== id)));
}

function remember(id: ExtraWalletId, address: string): ExtraWallet {
  const label = EXTRA_WALLETS.find((row) => row.id === id)?.label || id;
  const row = { id, label, address, connectedAt: new Date().toISOString() };
  localStorage.setItem(STORAGE, JSON.stringify([row, ...readStore().filter((item) => item.id !== id)]));
  return row;
}

function asProvider(value: unknown): Eip1193 | null {
  if (!value || typeof value !== "object") return null;
  if ("request" in value && typeof (value as Eip1193).request === "function") return value as Eip1193;
  if ("ethereum" in value) return asProvider((value as { ethereum?: unknown }).ethereum);
  return null;
}

function injected(id: ExtraWalletId): Eip1193 | null {
  const host = window as Window & {
    binancew3w?: { ethereum?: unknown };
    BinanceChain?: unknown;
    bybitWallet?: unknown;
    okxwallet?: unknown;
    ethereum?: { isBinance?: boolean };
  };
  if (id === "binance") return asProvider(host.binancew3w) || asProvider(host.BinanceChain) || (host.ethereum?.isBinance ? asProvider(host.ethereum) : null);
  if (id === "bybit") return asProvider(host.bybitWallet);
  if (id === "okx") return asProvider(host.okxwallet);
  return null;
}

async function connectInjected(id: ExtraWalletId): Promise<string> {
  const provider = injected(id);
  const spec = EXTRA_WALLETS.find((row) => row.id === id);
  if (!provider || !spec) throw new Error(`Install ${spec?.label || "the wallet"} in this browser, then try again. ${spec?.install || ""}`.trim());
  const accounts = await provider.request({ method: "eth_requestAccounts" });
  const address = Array.isArray(accounts) ? String(accounts[0] || "") : "";
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) throw new Error(`${spec.label} did not return a public address.`);
  return address;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  parts.forEach((part) => {
    out.set(part, offset);
    offset += part.length;
  });
  return out;
}

function frames(apdu: Uint8Array): Uint8Array[] {
  const packets: Uint8Array[] = [];
  let sequence = 0;
  let offset = 0;
  do {
    const first = packets.length === 0;
    const packet = new Uint8Array(64);
    packet[0] = 0x01;
    packet[1] = 0x01;
    packet[2] = 0x05;
    packet[3] = (sequence >> 8) & 0xff;
    packet[4] = sequence & 0xff;
    const start = first ? 7 : 5;
    if (first) {
      packet[5] = (apdu.length >> 8) & 0xff;
      packet[6] = apdu.length & 0xff;
    }
    const chunk = apdu.subarray(offset, offset + (64 - start));
    packet.set(chunk, start);
    packets.push(packet);
    offset += chunk.length;
    sequence += 1;
  } while (offset < apdu.length);
  return packets;
}

function ledgerPath(path: string): Uint8Array {
  const items = path.split("/").slice(1).map((item) => {
    const hardened = item.endsWith("'");
    return (hardened ? 0x80000000 : 0) + Number(item.replace("'", ""));
  });
  const data = new Uint8Array(1 + items.length * 4);
  data[0] = items.length;
  items.forEach((value, index) => {
    data[index * 4 + 1] = (value >>> 24) & 0xff;
    data[index * 4 + 2] = (value >>> 16) & 0xff;
    data[index * 4 + 3] = (value >>> 8) & 0xff;
    data[index * 4 + 4] = value & 0xff;
  });
  return data;
}

function exchange(device: HidDevice, apdu: Uint8Array): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const parts: Uint8Array[] = [];
    let expected = -1;
    let got = 0;
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("Unlock the Ledger, open the Ethereum app, and confirm the address on the device."));
    }, 60000);
    function onReport(event: { data: DataView }) {
      const packet = new Uint8Array(event.data.buffer, event.data.byteOffset, event.data.byteLength);
      if (packet.length < 7 || packet[2] !== 0x05) return;
      if (expected < 0) {
        expected = (packet[5] << 8) | packet[6];
        const slice = packet.subarray(7, 7 + expected);
        parts.push(slice);
        got = slice.length;
      } else {
        const slice = packet.subarray(5, 5 + (expected - got));
        parts.push(slice);
        got += slice.length;
      }
      if (got >= expected) {
        cleanup();
        resolve(concat(parts).subarray(0, expected));
      }
    }
    function cleanup() {
      window.clearTimeout(timer);
      device.removeEventListener("inputreport", onReport);
    }
    device.addEventListener("inputreport", onReport);
    (async () => {
      for (const packet of frames(apdu)) await device.sendReport(0x00, packet);
    })().catch((err: unknown) => {
      cleanup();
      reject(err instanceof Error ? err : new Error("The Ledger connection failed"));
    });
  });
}

function ledgerAddress(body: Uint8Array): string {
  if (body.length < 2) throw new Error("The Ledger returned an empty reply");
  const status = (body[body.length - 2] << 8) | body[body.length - 1];
  const data = body.subarray(0, -2);
  if (status === 0x6985) throw new Error("The Ledger rejected the request. Confirm it on the device.");
  if (status !== 0x9000) throw new Error("Open the Ethereum app on the Ledger, then try again.");
  const keyLength = data[0] || 0;
  const addressLength = data[1 + keyLength] || 0;
  const address = new TextDecoder().decode(data.subarray(2 + keyLength, 2 + keyLength + addressLength));
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) throw new Error("The Ledger did not return an Ethereum address.");
  return address;
}

async function connectLedger(): Promise<string> {
  const hid = (navigator as Navigator & { hid?: { requestDevice: (options: { filters: { vendorId: number }[] }) => Promise<HidDevice[]> } }).hid;
  if (!hid) throw new Error("Open this page in Chrome or Edge, then connect the Ledger.");
  const picked = await hid.requestDevice({ filters: [{ vendorId: 0x2c97 }] });
  const device = picked[0];
  if (!device) throw new Error("No Ledger was selected.");
  if (!device.opened) await device.open();
  const path = ledgerPath("44'/60'/0'/0/0");
  const apdu = new Uint8Array(5 + path.length);
  apdu.set([0xe0, 0x02, 0x01, 0x00, path.length]);
  apdu.set(path, 5);
  return ledgerAddress(await exchange(device, apdu));
}

export async function connectExtraWallet(id: ExtraWalletId): Promise<ExtraWallet> {
  try {
    const address = id === "ledger" ? await connectLedger() : await connectInjected(id);
    return remember(id, address);
  } catch (err) {
    if (err instanceof DOMException && err.name === "NotAllowedError") throw new Error("The wallet connection was cancelled.");
    throw err instanceof Error ? err : new Error("The wallet did not connect");
  }
}
