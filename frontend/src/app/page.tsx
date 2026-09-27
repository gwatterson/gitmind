"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { MetricsDashboard } from "@/components/MetricsDashboard";
import { PRList } from "@/components/PRList";
import { RateLimitGauge } from "@/components/RateLimitGauge";
import { clearArchive, errorMessage, getReviews, triggerManualReview } from "@/lib/api";
import type { Review } from "@/lib/types";

type TriggerState =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "ok"; text: string }
  | { kind: "error"; text: string };

export default function DashboardPage() {
  const { user } = useAuth();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggerRepo, setTriggerRepo] = useState("");
  const [triggerPR, setTriggerPR] = useState("");
  const [trigger, setTrigger] = useState<TriggerState>({ kind: "idle" });
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

  const handleTrigger = async () => {
    if (!triggerRepo || !triggerPR) return;
    setTrigger({ kind: "pending" });
    try {
      const data = await triggerManualReview(triggerRepo.trim(), parseInt(triggerPR, 10));
      setTrigger({ kind: "ok", text: `Review queued: ${data.review_id.slice(0, 8)}` });
      setTimeout(fetchReviews, 2000);
    } catch (error) {
      setTrigger({ kind: "error", text: errorMessage(error) });
    }
  };

  const handleClearArchive = async () => {
    if (!window.confirm("Are you sure you want to delete all reviews? This cannot be undone."))
      return;
    try {
      await clearArchive();
      setReviews([]);
      setStatsVersion((v) => v + 1);
    } catch (error) {
      alert(`Failed to clear archive: ${errorMessage(error)}`);
    }
  };

  return (
    <div className="animate-fade-in space-y-6">
      {/* Header */}
      <div>
        <h1 className="mb-1 text-2xl font-bold text-slate-100">Dashboard</h1>
        <p className="text-sm text-slate-500">
          Autonomous code review agent for real-time PR analysis
        </p>
      </div>

      {/* Metrics */}
      <MetricsDashboard refreshKey={statsVersion} />

      {/* Main grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* PR List (2/3 width) */}
        <div className="space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
              Recent Reviews
            </h2>
            <div className="flex gap-2">
              {user?.is_admin ? (
                <button
                  onClick={handleClearArchive}
                  className="btn-secondary border-red-500/30 text-xs text-red-400 hover:border-red-500/50 hover:bg-red-500/10"
                >
                  Clear Archive
                </button>
              ) : null}
              <button onClick={fetchReviews} className="btn-secondary text-xs">
                ↻ Refresh
              </button>
            </div>
          </div>

          {loading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="glass-card h-16 animate-pulse p-4" />
              ))}
            </div>
          ) : (
            <PRList reviews={reviews} />
          )}
        </div>

        {/* Sidebar (1/3 width) */}
        <div className="space-y-4">
          <RateLimitGauge />

          {/* Manual trigger */}
          <div className="glass-card p-4">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-200">
              Manual Review
            </h3>
            <div className="space-y-2">
              <input
                type="text"
                placeholder="owner/repo"
                aria-label="Repository (owner/repo)"
                value={triggerRepo}
                onChange={(e) => setTriggerRepo(e.target.value)}
                className="mono w-full rounded-lg border border-white/5 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 transition-colors placeholder:text-slate-600 focus:border-indigo-500/50 focus:outline-none"
              />
              <input
                type="number"
                placeholder="PR number"
                aria-label="Pull request number"
                value={triggerPR}
                onChange={(e) => setTriggerPR(e.target.value)}
                className="mono w-full rounded-lg border border-white/5 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 transition-colors placeholder:text-slate-600 focus:border-indigo-500/50 focus:outline-none"
              />
              <button
                onClick={handleTrigger}
                disabled={!triggerRepo || !triggerPR || trigger.kind === "pending"}
                className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-40"
              >
                {trigger.kind === "pending" ? "Triggering..." : "Trigger Review"}
              </button>
              {trigger.kind === "ok" || trigger.kind === "error" ? (
                <div
                  className={`flex items-start gap-2 rounded-md border p-3 text-sm ${trigger.kind === "error" ? "border-red-500/20 bg-red-500/10 text-red-400" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"}`}
                >
                  <p>{trigger.text}</p>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
