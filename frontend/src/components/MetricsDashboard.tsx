"use client";

import { useEffect, useState } from "react";
import type { ReviewStats } from "@/lib/types";

const CATEGORY_COLORS: Record<string, string> = {
  security: "#ef4444",
  quality: "#3b82f6",
  performance: "#eab308",
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
  info: "#3b82f6",
};

function StatCard({
  label,
  value,
  icon,
  gradient,
}: {
  label: string;
  value: number | string;
  icon: string;
  gradient: string;
}) {
  return (
    <div className="glass-card animate-fade-in flex items-center gap-3 p-4">
      <div
        className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg text-lg"
        style={{ background: gradient }}
      >
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-100">{value}</p>
        <p className="text-xs text-slate-500">{label}</p>
      </div>
    </div>
  );
}

function MiniBar({
  items,
  colors,
}: {
  items: Record<string, number>;
  colors: Record<string, string>;
}) {
  const total = Object.values(items).reduce((a, b) => a + b, 0);
  if (total === 0) return <p className="text-xs text-slate-600">No data</p>;

  return (
    <div>
      <div className="mb-2 flex h-2 overflow-hidden rounded-full bg-slate-800">
        {Object.entries(items).map(([key, count]) => (
          <div
            key={key}
            className="h-full transition-all duration-500"
            style={{
              width: `${(count / total) * 100}%`,
              background: colors[key] || "#64748b",
            }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {Object.entries(items).map(([key, count]) => (
          <div key={key} className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: colors[key] || "#64748b" }}
            />
            <span className="text-[10px] capitalize text-slate-500">
              {key}: {count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MetricsDashboard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [stats, setStats] = useState<ReviewStats | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const res = await fetch(`${apiUrl}/api/stats`);
        if (res.ok) setStats(await res.json());
      } catch {
        // silent
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, [refreshKey]);

  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="glass-card h-20 animate-pulse p-4" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Total Reviews"
          value={stats.total_reviews}
          icon="📊"
          gradient="linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))"
        />
        <StatCard
          label="Total Findings"
          value={stats.total_findings}
          icon="🔍"
          gradient="linear-gradient(135deg, rgba(236,72,153,0.2), rgba(239,68,68,0.2))"
        />
        <StatCard
          label="Completed"
          value={stats.reviews_by_status?.completed || 0}
          icon="✅"
          gradient="linear-gradient(135deg, rgba(34,197,94,0.2), rgba(16,185,129,0.2))"
        />
        <StatCard
          label="Failed"
          value={stats.reviews_by_status?.failed || 0}
          icon="❌"
          gradient="linear-gradient(135deg, rgba(239,68,68,0.2), rgba(220,38,38,0.2))"
        />
      </div>

      {/* Distribution bars */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="glass-card p-4">
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Findings by Category
          </h4>
          <MiniBar items={stats.findings_by_category || {}} colors={CATEGORY_COLORS} />
        </div>
        <div className="glass-card p-4">
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Findings by Severity
          </h4>
          <MiniBar items={stats.findings_by_severity || {}} colors={SEVERITY_COLORS} />
        </div>
      </div>
    </div>
  );
}
