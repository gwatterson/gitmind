"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { MetricsDashboard } from "@/components/MetricsDashboard";
import { ModelSelector } from "@/components/ModelSelector";
import { PRList } from "@/components/PRList";
import { clearArchive, errorMessage, getReviews, triggerManualReview } from "@/lib/api";
import type { Review } from "@/lib/types";

type TriggerState =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "ok"; text: string }
  | { kind: "error"; text: string };

function ManualReview({ onQueued }: { onQueued: () => void }) {
  const [repo, setRepo] = useState("");
  const [pr, setPr] = useState("");
  const [state, setState] = useState<TriggerState>({ kind: "idle" });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!repo || !pr) return;
    setState({ kind: "pending" });
    try {
      const data = await triggerManualReview(repo.trim(), parseInt(pr, 10));
      setState({ kind: "ok", text: `Review ${data.review_id.slice(0, 8)} queued.` });
      setTimeout(onQueued, 1500);
    } catch (error) {
      setState({ kind: "error", text: errorMessage(error) });
    }
  };

  return (
    <form onSubmit={submit} className="panel p-4">
      <h2 className="text-sm font-medium text-fg">Review a pull request</h2>
      <p className="mt-1 text-xs text-fg-subtle">Runs the full pipeline on demand.</p>
      <div className="mt-4 space-y-2">
        <label className="block">
          <span className="sr-only">Repository</span>
          <input
            className="field mono"
            placeholder="owner/repository"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="sr-only">Pull request number</span>
          <input
            className="field mono"
            type="number"
            min={1}
            placeholder="Pull request number"
            value={pr}
            onChange={(e) => setPr(e.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={!repo || !pr || state.kind === "pending"}
          className="btn-primary w-full"
        >
          {state.kind === "pending" ? "Starting..." : "Start review"}
        </button>
      </div>
      {state.kind === "ok" || state.kind === "error" ? (
        <p
          role="status"
          className={`mt-3 text-xs ${state.kind === "error" ? "text-danger" : "text-success"}`}
        >
          {state.text}
        </p>
      ) : null}
    </form>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [statsVersion, setStatsVersion] = useState(0);

  // State is only updated in promise callbacks, never synchronously inside the effect
  const fetchReviews = useCallback(
    () =>
      getReviews({ limit: 20 })
        .then((data) => setReviews(data.reviews || []))
        .catch(() => {
          // Unauthorized or backend unreachable: handled by the AuthGate
        })
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    fetchReviews();
    const interval = setInterval(fetchReviews, 10000);
    return () => clearInterval(interval);
  }, [fetchReviews]);

  const handleClearArchive = async () => {
    if (!window.confirm("Delete every review? This cannot be undone and has no effect on GitHub."))
      return;
    try {
      await clearArchive();
      setReviews([]);
      setStatsVersion((v) => v + 1);
    } catch (error) {
      window.alert(`Could not clear the reviews: ${errorMessage(error)}`);
    }
  };

  return (
    <div className="animate-fade-in space-y-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg">Reviews</h1>
          <p className="mt-1 text-sm text-fg-subtle">
            Pull requests reviewed by the security, quality and performance agents.
          </p>
        </div>
        <button onClick={fetchReviews} className="btn-secondary" aria-label="Refresh">
          <RefreshCw className="h-4 w-4" aria-hidden />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      <MetricsDashboard refreshKey={statsVersion} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
        <section aria-labelledby="recent" className="min-w-0 space-y-3">
          <h2 id="recent" className="section-title">
            Recent
          </h2>
          {loading ? <div className="h-48 animate-pulse panel" /> : <PRList reviews={reviews} />}
        </section>

        <aside className="space-y-4">
          <ManualReview onQueued={fetchReviews} />
          <ModelSelector />
          {user?.is_admin ? (
            <button onClick={handleClearArchive} className="btn-danger w-full">
              <Trash2 className="h-4 w-4" aria-hidden />
              Delete all reviews
            </button>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
