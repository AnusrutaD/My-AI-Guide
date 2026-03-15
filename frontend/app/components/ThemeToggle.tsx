"use client";

import { useTheme } from "@/app/context/ThemeContext";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
      onClick={toggleTheme}
      className="group relative inline-flex h-9 w-16 shrink-0 cursor-pointer items-center rounded-full border-2 border-slate-300 bg-slate-200 shadow-inner transition-all duration-300 ease-out hover:border-slate-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:border-slate-600 dark:bg-slate-700 dark:hover:border-slate-500"
    >
      <span
        className={`pointer-events-none flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-md transition-all duration-300 ease-out ${
          isDark ? "translate-x-8" : "translate-x-1"
        }`}
      >
        <span className="text-sm" aria-hidden>
          {isDark ? "🌙" : "☀️"}
        </span>
      </span>
    </button>
  );
}
