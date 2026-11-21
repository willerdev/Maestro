"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { api, apiJson, clearSession, isSystemAdmin, type User } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

type Scope = "user" | "desk";
type MenuItem = [string, string, IconName, Scope];

const MENUS: { label: string; items: MenuItem[] }[] = [
  { label: "Dashboard", items: [["/dashboard", "Dashboard", "grid", "user"]] },
  {
    label: "Trading",
    items: [
      ["/accounts", "Accounts", "wallet", "user"],
      ["/trades", "Trades", "swap", "user"],
      ["/journal", "Journal", "book", "user"],
    ],
  },
  { label: "Funds", items: [["/funds", "Funds", "fund", "user"]] },
  { label: "Wallet", items: [["/wallet", "Wallet", "coin", "user"]] },
  { label: "Alerts", items: [["/alerts", "Alerts", "bell", "user"]] },
  {
    label: "Reports",
    items: [
      ["/reports", "Reports", "file", "user"],
    ],
  },
  {
    label: "Connect",
    items: [
      ["/contracts", "Contracts", "contract", "user"],
      ["/pass-props", "Pass Props", "shield", "user"],
      ["/project-coin", "Project Coin", "coin", "user"],
      ["/webhooks", "Webhooks", "link", "desk"],
      ["/payments", "Payments", "card", "user"],
      ["/telegram", "Telegram", "send", "user"],
    ],
  },
  {
    label: "System",
    items: [
      ["/users", "Users", "users", "desk"],
      ["/withdrawals", "Withdrawals", "card", "desk"],
      ["/settings", "Settings", "gear", "user"],
      ["/recovery", "Recovery", "lock", "desk"],
      ["/audit", "Audit Logs", "list", "desk"],
      ["/applications", "Applications", "users", "desk"],
    ],
  },
];

const DESK_ROLES = ["SUPER_ADMIN", "ADMIN", "RISK_MANAGER", "TRADER", "VIEWER"];
const PHONE = 1024;
const ICON = 40;
const ICON_GAP = 2;

function menusFor(roles: string[]) {
  const admin = isSystemAdmin(roles);
  return MENUS.map((menu) => ({
    ...menu,
    items: menu.items.filter(([, , , scope]) => admin || scope === "user"),
  })).filter((menu) => menu.items.length);
}

function menuScope(items: MenuItem[]): Scope | "mixed" {
  const scopes = new Set(items.map((item) => item[3]));
  if (scopes.size === 1) return items[0][3];
  return "mixed";
}

function scopeTitle(scope: Scope | "mixed") {
  if (scope === "desk") return "Users do not see this menu";
  if (scope === "mixed") return "Blue: users see this. Amber: users do not.";
  return "Users see this menu";
}

function ScopeDot({ show, scope }: { show: boolean; scope?: Scope | "mixed" }) {
  if (!show || !scope) return null;
  if (scope === "mixed") {
    return (
      <b className="scope-dots" aria-hidden="true">
        <i className="scope-dot user" />
        <i className="scope-dot desk" />
      </b>
    );
  }
  return <i className={`scope-dot ${scope}`} aria-hidden="true" />;
}

export function homeFor(roles: string[]) {
  if (roles.some((role) => DESK_ROLES.includes(role))) return "/dashboard";
  if (roles.includes("INVESTOR")) return "/investor";
  if (roles.includes("PORTAL_TRADER")) return "/trader";
  return "/pending";
}

type IconName = "grid" | "wallet" | "layers" | "swap" | "book" | "shield" | "sliders" | "bell" | "chart" | "file" | "link" | "key" | "card" | "send" | "gear" | "lock" | "list" | "fund" | "users" | "coin" | "contract" | "mine" | "more";

function Icon({ name }: { name: IconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      {name === "grid" ? <path {...common} d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /> : null}
      {name === "wallet" ? <path {...common} d="M3 8h18v11H3zM3 8l2-3h12l2 3M16 13h3" /> : null}
      {name === "layers" ? <path {...common} d="M12 3l9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 16l9 5 9-5" /> : null}
      {name === "swap" ? <path {...common} d="M7 7h11l-3-3M17 17H6l3 3" /> : null}
      {name === "book" ? <path {...common} d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 0-3 3zM5 4v16" /> : null}
      {name === "shield" ? <path {...common} d="M12 3l8 3v6c0 5-3.4 8-8 9-4.6-1-8-4-8-9V6z" /> : null}
      {name === "sliders" ? <path {...common} d="M4 7h16M4 17h16M8 7v4M16 13v4" /> : null}
      {name === "bell" ? <path {...common} d="M6 16V10a6 6 0 1 1 12 0v6l2 2H4zM10 20a2 2 0 0 0 4 0" /> : null}
      {name === "chart" ? <path {...common} d="M4 19V5M4 19h16M8 15l4-5 3 3 5-7" /> : null}
      {name === "file" ? <path {...common} d="M7 3h7l5 5v13H7zM14 3v5h5" /> : null}
      {name === "link" ? <path {...common} d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1" /> : null}
      {name === "key" ? <path {...common} d="M8 15a4 4 0 1 1 3-6l9 3v3h-3v2h-3l-2-2" /> : null}
      {name === "card" ? <path {...common} d="M3 7h18v11H3zM3 11h18" /> : null}
      {name === "send" ? <path {...common} d="M4 12l16-7-6 16-3-6z" /> : null}
      {name === "gear" ? <path {...common} d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.5 1.5M16.9 16.9l1.5 1.5M18.4 5.6l-1.5 1.5M7.1 16.9l-1.5 1.5" /> : null}
      {name === "lock" ? <path {...common} d="M8 11V8a4 4 0 0 1 8 0v3M6 11h12v9H6z" /> : null}
      {name === "list" ? <path {...common} d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" /> : null}
      {name === "users" ? <path {...common} d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2M9.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M20 21v-2a3.5 3.5 0 0 0-2.5-3.3M16.5 5.1a3 3 0 0 1 0 5.6" /> : null}
      {name === "fund" ? <path {...common} d="M4 20V10l8-6 8 6v10H4zM9 20v-6h6v6" /> : null}
      {name === "coin" ? <path {...common} d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9 12h6" /> : null}
      {name === "contract" ? <path {...common} d="M7 3h7l5 5v13H7zM14 3v5h5M9 13h6M9 17h4" /> : null}
      {name === "mine" ? <path {...common} d="M4 20h16M9 20l7-11 4 2-7 9M14 9l4-4" /> : null}
      {name === "more" ? (
        <>
          <circle cx="6" cy="12" r="1.7" fill="currentColor" />
          <circle cx="12" cy="12" r="1.7" fill="currentColor" />
          <circle cx="18" cy="12" r="1.7" fill="currentColor" />
        </>
      ) : null}
    </svg>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [visibleCount, setVisibleCount] = useState(99);
  const iconsRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    api("/api/v1/auth/me")
      .then(async (response) => {
        if (!response.ok) {
          router.replace("/login");
          return;
        }
        const me = await response.json();
        if (cancelled) return;
        setUser(me);
        const home = homeFor(me.roles || []);
        if (home !== "/dashboard") {
          router.replace(home);
          return;
        }
        if (pathname !== "/setup" && pathname !== "/contracts") {
          try {
            const setup = await apiJson<{ complete: boolean }>("/api/v1/setup/status");
            if (!setup.complete) {
              router.replace("/setup");
              return;
            }
          } catch {
            if (!cancelled) setReady(true);
            return;
          }
        }
        if (!cancelled) setReady(true);
      })
      .catch(() => router.replace("/login"));
    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  useEffect(() => {
    setOpenMenu(null);
    setMoreOpen(false);
  }, [pathname]);

  useEffect(() => {
    function close(event: Event) {
      const node = event.target as Node | null;
      if (moreRef.current?.contains(node) || (node instanceof Element && node.closest(".desk-menu, .desk-drop"))) return;
      setOpenMenu(null);
      setMoreOpen(false);
    }
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);

  const menus = menusFor(user?.roles || []).filter((menu) => menu.items.length);
  const links = menus.flatMap((menu) => menu.items);
  const showScopes = isSystemAdmin(user?.roles);
  const extra = links.slice(visibleCount);
  const moreOn = extra.some(([href]) => pathname === href || pathname.startsWith(`${href}/`));

  useLayoutEffect(() => {
    const bar = iconsRef.current;
    function fit() {
      const phone = window.matchMedia(`(max-width: ${PHONE}px)`).matches;
      if (!bar || !phone) {
        setVisibleCount(links.length);
        return;
      }
      const width = Math.floor(bar.clientWidth);
      const shown = Math.floor((width + ICON_GAP) / (ICON + ICON_GAP));
      if (shown >= links.length) {
        setVisibleCount(links.length);
        return;
      }
      setVisibleCount(Math.max(0, Math.min(links.length - 1, shown)));
    }
    fit();
    if (!bar) return;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    observer?.observe(bar);
    window.addEventListener("resize", fit);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, [links.length, ready]);

  async function logout() {
    await api("/api/v1/auth/logout", { method: "POST" });
    clearSession();
    router.replace("/login");
  }

  if (!ready) {
    return <div className="min-h-screen grid place-items-center text-muted">Loading desk…</div>;
  }

  return (
    <div className="desk-shell">
      <aside className="desk-rail">
        <Link href="/dashboard" className="desk-mark" title="Maestro">M</Link>
        <nav className="flex flex-col items-stretch gap-1" onMouseDown={(event) => event.stopPropagation()}>
          {links.map(([href, label, icon, scope]) => {
            const on = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className={on ? "on" : ""}
                title={showScopes ? `${label} · ${scopeTitle(scope)}` : label}
                aria-label={label}
              >
                <Icon name={icon} />
                <span>{label}</span>
                <ScopeDot show={showScopes} scope={scope} />
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="desk-main">
        <header className="desk-top">
          <Link href="/dashboard" className="desk-mark phone-mark" title="Maestro">M</Link>
          <nav className="desk-menu">
            {menus.map((menu) => {
              const active = menu.items.some(([href]) => pathname === href || pathname.startsWith(`${href}/`));
              const group = menuScope(menu.items);
              if (menu.items.length === 1) {
                const [href, label, , scope] = menu.items[0];
                return (
                  <Link
                    key={label}
                    href={href}
                    className={active ? "on" : ""}
                    title={showScopes ? scopeTitle(scope) : undefined}
                  >
                    {label}
                    <ScopeDot show={showScopes} scope={scope} />
                  </Link>
                );
              }
              const open = openMenu === menu.label;
              return (
                <div key={menu.label} className="desk-drop">
                  <button
                    type="button"
                    className={active ? "menu on" : "menu"}
                    aria-expanded={open}
                    title={showScopes ? scopeTitle(group) : undefined}
                    onClick={() => setOpenMenu(open ? null : menu.label)}
                  >
                    {menu.label}
                    <ScopeDot show={showScopes} scope={group} />
                  </button>
                  {open ? (
                    <div className="desk-sub">
                      {menu.items.map(([href, label, , scope]) => {
                        const on = pathname === href || pathname.startsWith(`${href}/`);
                        return (
                          <Link
                            key={href}
                            href={href}
                            className={on ? "on" : ""}
                            title={showScopes ? scopeTitle(scope) : undefined}
                          >
                            {label}
                            <ScopeDot show={showScopes} scope={scope} />
                          </Link>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </nav>
          <nav className={`desk-icons${moreOpen ? " open" : ""}`}>
            <div className="desk-icon-row" ref={iconsRef}>
              {links.slice(0, visibleCount).map(([href, label, icon]) => {
                const on = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <Link key={href} href={href} className={`desk-icon${on ? " on" : ""}`} title={label} aria-label={label}>
                    <Icon name={icon} />
                  </Link>
                );
              })}
            </div>
            {extra.length ? (
              <div className="desk-more" ref={moreRef}>
                <button
                  type="button"
                  className={`desk-icon${moreOn || moreOpen ? " on" : ""}`}
                  aria-label="More"
                  aria-expanded={moreOpen}
                  title="More"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    setMoreOpen((open) => !open);
                  }}
                >
                  <Icon name="more" />
                </button>
                {moreOpen ? (
                  <div className="desk-sub">
                    {extra.map(([href, label, icon]) => {
                      const on = pathname === href || pathname.startsWith(`${href}/`);
                      return (
                        <Link key={href} href={href} className={on ? "on" : ""}>
                          <Icon name={icon} />
                          {label}
                        </Link>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            ) : null}
          </nav>
          <div className="desk-user">
            {showScopes ? (
              <div className="desk-legend" aria-label="Menu dots">
                <span><i className="scope-dot user" /> Users see</span>
                <span><i className="scope-dot desk" /> Hidden</span>
              </div>
            ) : null}
            <span>{user?.email}</span>
            <ThemeToggle />
            <button className="ghost" onClick={logout}>Log out</button>
          </div>
        </header>
        <main className="desk-content">{children}</main>
      </div>
    </div>
  );
}

export function PageTitle({ title, detail }: { title: string; detail?: ReactNode }) {
  return (
    <header className="page-head">
      <h1>{title}</h1>
      {detail ? <p className="text-sm text-muted">{detail}</p> : null}
    </header>
  );
}
