"use client";

import { useState } from "react";
import { Check } from "lucide-react";
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
    return <div className="h-40 animate-pulse panel" />;
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
    <div className="panel p-4">
      <h2 className="text-sm font-medium text-fg">Model</h2>
      <p className="mt-1 text-xs text-fg-subtle">
        {canSwitch
          ? "Used for reviews started from now on."
          : "Only administrators can change the model."}
      </p>

      <div role="radiogroup" aria-label="LLM provider" className="mt-4 space-y-1.5">
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
              className={`flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                active
                  ? "border-accent/50 bg-accent-soft"
                  : "border-line bg-surface-2 hover:border-line-strong"
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm text-fg">{option.label}</div>
                <div className="truncate mono text-xs text-fg-subtle">
                  {pending === option.id ? "Switching..." : option.model}
                </div>
                {!option.available && option.reason ? (
                  <div className="mt-1 text-xs text-warning">{option.reason}</div>
                ) : null}
              </div>
              {active ? <Check className="h-4 w-4 shrink-0 text-accent" aria-hidden /> : null}
            </button>
          );
        })}
      </div>
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
    </div>
  );
}
