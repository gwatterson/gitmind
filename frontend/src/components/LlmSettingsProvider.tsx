"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getLlmSettings, setLlmProvider } from "@/lib/api";
import type { LlmSettings } from "@/lib/types";
import { useAuth } from "./AuthProvider";

interface LlmSettingsContextValue {
  settings: LlmSettings | null;
  refresh: () => Promise<void>;
  switchProvider: (provider: LlmSettings["provider"]) => Promise<void>;
}

const LlmSettingsContext = createContext<LlmSettingsContextValue>({
  settings: null,
  refresh: async () => {},
  switchProvider: async () => {},
});

export function useLlmSettings(): LlmSettingsContextValue {
  return useContext(LlmSettingsContext);
}

/** Active LLM provider, shared by the navigation bar and the dashboard. */
export function LlmSettingsProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [settings, setSettings] = useState<LlmSettings | null>(null);

  // State is only updated in promise callbacks, never synchronously inside the effect
  const refresh = useCallback(
    () =>
      getLlmSettings().then(setSettings, () => {
        // Signed out or backend unreachable: handled by the AuthGate
      }),
    [],
  );

  useEffect(() => {
    if (user) refresh();
  }, [user, refresh]);

  const switchProvider = useCallback(async (provider: LlmSettings["provider"]) => {
    setSettings(await setLlmProvider(provider));
  }, []);

  return (
    <LlmSettingsContext.Provider
      value={{ settings: user ? settings : null, refresh, switchProvider }}
    >
      {children}
    </LlmSettingsContext.Provider>
  );
}
