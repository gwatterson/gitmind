"use client";

import { useEffect, useState } from "react";
import { PRList } from "@/components/PRList";
import { MetricsDashboard } from "@/components/MetricsDashboard";
import { RateLimitGauge } from "@/components/RateLimitGauge";
import type { Review } from "@/lib/types";

export default function DashboardPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggerRepo, setTriggerRepo] = useState("");
  const [triggerPR, setTriggerPR] = useState("");
  const [triggerStatus, setTriggerStatus] = useState<string | null>(null);
  const [statsVersion, setStatsVersion] = useState(0);

  const fetchReviews = async () => {
    try {
      const apiUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/reviews?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setReviews(data.reviews || []);
      }
    } catch {
      // Backend might not be running
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviews();
    const interval = setInterval(fetchReviews, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleTrigger = async () => {
    if (!triggerRepo || !triggerPR) return;
    setTriggerStatus("triggering...");
    try {
      const apiUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/reviews/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo: triggerRepo,
          pr_number: parseInt(triggerPR),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setTriggerStatus(`✅ Review queued: ${data.review_id?.slice(0, 8)}...`);
        setTimeout(fetchReviews, 2000);
      } else {
        setTriggerStatus(`❌ Error: ${data.detail || "Unknown error"}`);
      }
    } catch (e: unknown) {
      setTriggerStatus(`❌ ${e instanceof Error ? e.message : "Network error"}`);
    }
  };

  const handleClearArchive = async () => {
    if (!window.confirm("Are you sure you want to delete all reviews? This cannot be undone.")) return;
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/reviews`, { method: "DELETE" });
      if (res.ok) {
        setReviews([]);
        setStatsVersion((v) => v + 1);
      } else {
        alert("Failed to clear archive");
      }
    } catch (e) {
      alert("Error clearing archive");
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100 mb-1">Dashboard</h1>
        <p className="text-sm text-slate-500">
          Autonomous code review agent — real-time PR analysis
        </p>
      </div>

      {/* Metrics */}
      <MetricsDashboard refreshKey={statsVersion} />

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* PR List (2/3 width) */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
              Recent Reviews
            </h2>
            <div className="flex gap-2">
              <button
                onClick={handleClearArchive}
                className="btn-secondary text-xs border-red-500/30 text-red-400 hover:bg-red-500/10 hover:border-red-500/50"
              >
                🗑️ Clear Archive
              </button>
              <button
                onClick={fetchReviews}
                className="btn-secondary text-xs"
              >
                ↻ Refresh
              </button>
            </div>
          </div>

          {loading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="glass-card p-4 animate-pulse h-16" />
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
            <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-3">
              Manual Review
            </h3>
            <div className="space-y-2">
              <input
                type="text"
                placeholder="owner/repo"
                value={triggerRepo}
                onChange={(e) => setTriggerRepo(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-800/50 border border-white/5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors mono"
              />
              <input
                type="number"
                placeholder="PR number"
                value={triggerPR}
                onChange={(e) => setTriggerPR(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-800/50 border border-white/5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors mono"
              />
              <button
                onClick={handleTrigger}
                disabled={!triggerRepo || !triggerPR || triggerStatus === "triggering..."}
                className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed"
              >
                🚀 {triggerStatus === "triggering..." ? "Triggering..." : "Trigger Review"}
              </button>
              {triggerStatus && triggerStatus !== "triggering..." && (
                <div className={`p-3 rounded-md border text-sm flex items-start gap-2 ${triggerStatus.startsWith("❌") ? "bg-red-500/10 border-red-500/20 text-red-400" : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"}`}>
                  <p>{triggerStatus}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
