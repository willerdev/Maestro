import { beginRequest } from "@/lib/busy";

function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    const { protocol, hostname, port } = window.location;
    if (port === "3000") {
      return `${protocol}//${hostname}:8000`;
    }
    return window.location.origin;
  }
  return "http://127.0.0.1:8000";
}

const API = apiBase();

export type User = {
  id: string;
  email: string;
  full_name: string;
  organization_id: string;
  roles: string[];
};

export function isSystemAdmin(roles?: string[]) {
  return Boolean(roles?.includes("SUPER_ADMIN") || roles?.includes("ADMIN"));
}

function accessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem("tg_access");
}

export function deviceId(): string {
  if (typeof window === "undefined") return "";
  const key = "tg_device";
  try {
    let id = window.localStorage.getItem(key);
    if (!id) {
      id = window.crypto?.randomUUID?.() || `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
      window.localStorage.setItem(key, id);
    }
    return id;
  } catch {
    return "";
  }
}

export function saveSession(token: string, refreshToken?: string) {
  sessionStorage.setItem("tg_access", token);
  if (typeof refreshToken === "string" && refreshToken) {
    sessionStorage.setItem("tg_refresh", refreshToken);
  }
}

export function clearSession() {
  sessionStorage.removeItem("tg_access");
  sessionStorage.removeItem("tg_refresh");
}

let refreshTask: Promise<boolean> | null = null;

function refreshAccess(): Promise<boolean> {
  if (refreshTask) return refreshTask;
  const stored = typeof window !== "undefined" ? sessionStorage.getItem("tg_refresh") || "" : "";
  refreshTask = fetch(`${API}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: {
      "X-Tradeguard-Request": "1",
      ...(stored ? { "Content-Type": "application/json" } : {}),
    },
    body: stored ? JSON.stringify({ refresh_token: stored }) : undefined,
  })
    .then(async (refreshed) => {
      if (!refreshed.ok) return false;
      const body = await refreshed.json();
      if (typeof body.access_token === "string") {
        saveSession(body.access_token, typeof body.refresh_token === "string" ? body.refresh_token : undefined);
      }
      return typeof body.access_token === "string";
    })
    .catch(() => false)
    .finally(() => {
      refreshTask = null;
    });
  return refreshTask;
}

export async function api(path: string, options: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(options.headers);
  headers.set("X-Tradeguard-Request", "1");
  headers.set("Cache-Control", "no-store");
  const device = deviceId();
  if (device) headers.set("X-Device-Id", device);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const method = (options.method || "GET").toUpperCase();
  const done = beginRequest(method);
  try {
    const freshPath = method === "GET" ? `${path}${path.includes("?") ? "&" : "?"}_=${Date.now()}` : path;
    const response = await fetch(`${API}${freshPath}`, { ...options, headers, credentials: "include", cache: "no-store" });
    if (response.status === 401 && retry && !path.startsWith("/api/v1/auth/login") && !path.startsWith("/api/v1/auth/refresh")) {
      const refreshed = await refreshAccess();
      if (refreshed) return api(path, options, false);
    }
    return response;
  } finally {
    done();
  }
}

export async function apiJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await api(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Request failed";
    throw new Error(detail);
  }
  return body as T;
}
