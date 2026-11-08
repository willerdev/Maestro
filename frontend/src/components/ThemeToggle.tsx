"use client";

import { toggleTheme } from "@/lib/theme";

export function ThemeToggle() {
  return (
    <button
      type="button"
      className="ghost theme-toggle"
      onClick={() => {
        const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
        toggleTheme(current);
      }}
    >
      <span className="when-light">Dark</span>
      <span className="when-dark">Light</span>
    </button>
  );
}
