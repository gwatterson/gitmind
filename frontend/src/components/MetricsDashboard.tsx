"use client";

import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";
import type { ReviewStats } from "@/lib/types";
import { SEVERITIES } from "./ui";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--color-critical)",
  high: "var(--color-high)",
  medium: "var(--color-medium)",
  low: "var(--color-low)",
  info: "var(--color-info)",
};

function Stat({ label, value, emphasis }: { label: string; value: number; emphasis?: boolean }) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs text-fg-subtle">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold tabular ${emphasis && value > 0 ? "text-warning" : "text-fg"}`}
      >
        {value}
      </p>
    </div>
  );
}

function SeverityBreakdown({ counts }: { counts: Record<string, number> }) {
  const total = SEVERITIES.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
  return (
    <div className="px-5 py-4">
      <p className="text-xs text-fg-subtle">Findings by severity</p>
      {total === 0 ? (
        <p className="mt-3 text-sm text-fg-subtle">None yet</p>
      ) : (
        <>
          <div className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-surface-3">
            {SEVERITIES.map((s) =>
              counts[s] ? (
                <div
                  key={s}
                  style={{ width: `${(counts[s] / total) * 100}%`, background: SEVERITY_COLOR[s] }}
                />
              ) : null,
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
            {SEVERITIES.map((s) =>
              counts[s] ? (
                <span key={s} className="inline-flex items-center gap-1 text-xs text-fg-muted">
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: SEVERITY_COLOR[s] }}
                  />
                  <span className="capitalize">{s}</span>
                  <span className="text-fg-subtle tabular">{counts[s]}</span>
                </span>
              ) : null,
            )}
          </div>
        </>
      )}
    </div>
  );
}

export function MetricsDashboard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [stats, setStats] = useState<ReviewStats | null>(null);

  useEffect(() => {
    const fetchStats = () =>
      getStats()
        .then(setStats)
        .catch(() => {
          // Unauthorized or backend unreachable: handled by the AuthGate
        });
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, [refreshKey]);

  if (!stats) {
    return <div className="h-[86px] animate-pulse panel" />;
  }

  const byStatus = stats.reviews_by_status ?? {};
  return (
    <div className="grid grid-cols-2 divide-line panel md:grid-cols-5 md:divide-x">
      <Stat label="Reviews" value={stats.total_reviews} />
      <Stat label="Needs approval" value={byStatus.hitl_pending ?? 0} emphasis />
      <Stat label="Failed" value={byStatus.failed ?? 0} />
      <Stat label="Published findings" value={stats.total_findings} />
      <div className="col-span-2 border-t border-line md:col-span-1 md:border-t-0">
        <SeverityBreakdown counts={stats.findings_by_severity ?? {}} />
      </div>
    </div>
  );
}
