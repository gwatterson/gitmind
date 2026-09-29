"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { getAuthStatus, loginUrl } from "@/lib/api";

const ERROR_MESSAGES: Record<string, string> = {
  not_allowed: "Your GitHub account is not on the list of allowed users for this instance.",
  github: "GitHub sign-in failed. Please try again.",
};

function LoginContent({ backendDown, onRetry }: { backendDown: boolean; onRetry: () => void }) {
  const params = useSearchParams();
  const [oauthConfigured, setOauthConfigured] = useState(true);

  useEffect(() => {
    if (backendDown) return;
    getAuthStatus()
      .then((status) => setOauthConfigured(status.oauth_configured))
      .catch(() => setOauthConfigured(true));
  }, [backendDown]);
  const error = params.get("error");
  const next =
    typeof window !== "undefined" && window.location.pathname !== "/login"
      ? window.location.pathname + window.location.search
      : "/";

  return (
    <div className="mx-auto mt-16 max-w-md">
      <div className="space-y-5 panel p-8 text-center">
        <div>
          <h1 className="mb-1 text-xl font-semibold text-fg">Sign in to GitMind</h1>
          <p className="text-sm text-fg-subtle">
            Access is limited to the GitHub accounts and organizations configured by the
            administrator.
          </p>
        </div>

        {backendDown ? (
          <div className="rounded-md border border-warning/20 bg-warning/10 p-3 text-sm text-warning">
            The backend is not reachable. Check that it is running, then retry.
          </div>
        ) : null}
        {!backendDown && !oauthConfigured ? (
          <div className="rounded-md border border-warning/20 bg-warning/10 p-3 text-left text-sm text-warning">
            GitHub sign-in is not configured on the server. Set GITHUB_OAUTH_CLIENT_ID and
            GITHUB_OAUTH_CLIENT_SECRET in backend/.env (see GUIDE.md), or set AUTH_DISABLED=true for
            local development only.
          </div>
        ) : null}
        {error && ERROR_MESSAGES[error] ? (
          <div className="rounded-md border border-danger/20 bg-danger/10 p-3 text-sm text-danger">
            {ERROR_MESSAGES[error]}
          </div>
        ) : null}

        {backendDown ? (
          <button onClick={onRetry} className="btn-secondary w-full">
            Retry
          </button>
        ) : oauthConfigured ? (
          <a href={loginUrl(next)} className="btn-primary block w-full">
            Sign in with GitHub
          </a>
        ) : null}
      </div>
    </div>
  );
}

export function LoginScreen(props: { backendDown: boolean; onRetry: () => void }) {
  // useSearchParams needs a Suspense boundary in the App Router
  return (
    <Suspense fallback={null}>
      <LoginContent {...props} />
    </Suspense>
  );
}
