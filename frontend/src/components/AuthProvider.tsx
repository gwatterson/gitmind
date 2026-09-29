"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiError, UNAUTHORIZED_EVENT, getMe, logout as apiLogout } from "@/lib/api";
import type { User } from "@/lib/types";
import { LoginScreen } from "./LoginScreen";

type AuthState =
  | { status: "loading" }
  | { status: "signed-out"; backendDown: boolean }
  | { status: "signed-in"; user: User; authDisabled: boolean };

interface AuthContextValue {
  state: AuthState;
  user: User | null;
  authDisabled: boolean;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  state: { status: "loading" },
  user: null,
  authDisabled: false,
  reload: async () => {},
  logout: async () => {},
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

/** Loads the signed-in user and keeps the session state for the whole app. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  // State is only updated in promise callbacks, never synchronously inside the effect
  const reload = useCallback(
    () =>
      getMe().then(
        (me) => setState({ status: "signed-in", user: me.user, authDisabled: me.auth_disabled }),
        (error) => setState({ status: "signed-out", backendDown: !(error instanceof ApiError) }),
      ),
    [],
  );

  useEffect(() => {
    reload();
    const onUnauthorized = () => setState({ status: "signed-out", backendDown: false });
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [reload]);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setState({ status: "signed-out", backendDown: false });
    }
  }, []);

  const value: AuthContextValue = {
    state,
    user: state.status === "signed-in" ? state.user : null,
    authDisabled: state.status === "signed-in" && state.authDisabled,
    reload,
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Renders its children only for signed-in users, the sign-in screen otherwise. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { state, reload } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const signedInOnLoginPage = state.status === "signed-in" && pathname === "/login";

  useEffect(() => {
    if (signedInOnLoginPage) router.replace("/");
  }, [signedInOnLoginPage, router]);

  if (state.status === "loading" || signedInOnLoginPage) {
    return <div className="h-40 animate-pulse panel" />;
  }
  if (state.status === "signed-out") {
    return <LoginScreen backendDown={state.backendDown} onRetry={reload} />;
  }
  return <>{children}</>;
}
