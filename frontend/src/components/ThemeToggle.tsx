"use client";

import { toggleTheme } from "@/lib/theme";

export function ThemeToggle() {
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label="Light or dark"
      title="Light or dark"
      onClick={() => {
        const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
        toggleTheme(current);
      }}
    >
      <svg className="when-light" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          d="M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4l1.4-1.4M17 7l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"
        />
      </svg>
      <svg className="when-dark" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M16 14.5A6.5 6.5 0 0 1 9.5 8 6.5 6.5 0 1 0 16 14.5z"
        />
      </svg>
    </button>
  );
}
