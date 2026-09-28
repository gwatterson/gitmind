"use client";

import { useState } from "react";
import { errorMessage } from "@/lib/api";
import type { LlmProviderOption } from "@/lib/types";
import { useAuth } from "./AuthProvider";
import { useLlmSettings } from "./LlmSettingsProvider";

/** Shows the active LLM and lets administrators switch provider for new reviews. */
export function ModelSelector() {
  const { user } = useAuth();
  const { settings, refresh, switchProvider } = useLlmSettings();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!settings) {
    return <div className="h-32 animate-pulse glass-card" />;
  }

  const canSwitch = Boolean(user?.is_admin);

  const choose = async (option: LlmProviderOption) => {
    if (!canSwitch || option.id === settings.provider || !option.available) return;
    setPending(option.id);
    setError(null);
    try {
      await switchProvider(option.id);
    } catch (e) {
      setError(errorMessage(e));
      await refresh();
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="glass-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-wider text-slate-200 uppercase">Model</h3>
        <span className="mono text-[11px] text-slate-500">{settings.model}</span>
      </div>

      <div role="radiogroup" aria-label="LLM provider" className="space-y-2">
        {settings.providers.map((option) => {
          const active = option.id === settings.provider;
          const disabled = !canSwitch || !option.available || pending !== null;
          return (
            <button
              key={option.id}
              role="radio"
              aria-checked={active}
              onClick={() => choose(option)}
              disabled={disabled && !active}
              title={option.reason ?? undefined}
              className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                active
                  ? "border-indigo-500/40 bg-indigo-500/10"
                  : "border-white/5 bg-slate-800/30 hover:border-white/10"
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-200">{option.label}</span>
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    active
                      ? "bg-indigo-400"
                      : option.available
                        ? "bg-emerald-400/70"
                        : "bg-slate-600"
                  }`}
                />
              </div>
              <div className="mt-0.5 mono text-[11px] text-slate-500">
                {pending === option.id ? "Switching..." : option.model}
              </div>
              {!option.available && option.reason ? (
                <div className="mt-1 text-[11px] text-amber-400/80">{option.reason}</div>
              ) : null}
            </button>
          );
        })}
      </div>

      <p className="mt-3 text-[11px] text-slate-500">
        {canSwitch
          ? "Applies to reviews started from now on."
          : "Only administrators can change the model."}
      </p>
      {error ? <p className="mt-2 text-xs text-red-400">{error}</p> : null}
    </div>
  );
}
