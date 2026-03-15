"use client";

import { Spinner } from "@/app/components/Spinner";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "success";

const variantStyles: Record<ButtonVariant, { base: string; disabled: string }> = {
  primary: {
    base: "bg-blue-600 text-white hover:bg-blue-500 active:bg-blue-700 shadow-sm hover:shadow-md dark:shadow-slate-900/50",
    disabled: "disabled:bg-blue-600/70 disabled:shadow-none",
  },
  secondary: {
    base: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-400 active:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 dark:hover:border-slate-600 dark:active:bg-slate-600",
    disabled: "disabled:opacity-50",
  },
  success: {
    base: "bg-emerald-600 text-white hover:bg-emerald-500 active:bg-emerald-700 shadow-sm hover:shadow-md dark:shadow-slate-900/50",
    disabled: "disabled:bg-emerald-600/70 disabled:shadow-none",
  },
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  loading?: boolean;
  loadingLabel?: string;
  children: ReactNode;
};

export function Button({
  variant = "secondary",
  loading = false,
  loadingLabel,
  children,
  disabled,
  className = "",
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      type="button"
      disabled={isDisabled}
      className={`
        inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium
        transition-all duration-200 ease-out
        active:scale-[0.97] hover:scale-[1.02]
        focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2
        disabled:scale-100 disabled:cursor-not-allowed disabled:opacity-80
        ${variantStyles[variant].base}
        ${isDisabled ? variantStyles[variant].disabled : ""}
        ${className}
      `.trim().replace(/\s+/g, " ")}
      {...props}
    >
      {loading ? (
        <>
          <Spinner className="h-4 w-4 shrink-0" />
          <span>{loadingLabel ?? "Loading..."}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
}
