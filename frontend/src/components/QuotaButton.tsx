"use client";

import { useEffect, useRef, useState } from "react";
import { useLlmSettings } from "./LlmSettingsProvider";
import { RateLimitGauge } from "./RateLimitGauge";

/**
 * API quota indicator in the navigation bar. Shown only when the active provider
 * is rate limited (Gemini): local models have no quota.
 */
export function QuotaButton() {
  const { settings } = useLlmSettings();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (container.current && !container.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  if (!settings?.rate_limited) return null;

  return (
    <div ref={container} className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label="API quota"
        title="Gemini API quota"
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-line text-fg-muted transition-colors hover:border-line-strong hover:text-fg"
      >
        <svg
          className="h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 13l3-3M5.6 18.4A9 9 0 1118.4 18.4"
          />
          <circle cx="12" cy="13" r="1" fill="currentColor" />
        </svg>
      </button>
      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-lg border border-line bg-surface shadow-2xl">
          <RateLimitGauge />
        </div>
      ) : null}
    </div>
  );
}
