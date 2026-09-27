"use client";

import Link from "next/link";
import { parseServerDate } from "@/lib/api";
import type { Review } from "@/lib/types";

const STATUS_CONFIG: Record<string, { label: string; class: string; icon: string }> = {
  pending: { label: "Pending", class: "badge-pending", icon: "⏳" },
  running: { label: "Running", class: "badge-running", icon: "⚙️" },
  completed: { label: "Completed", class: "badge-completed", icon: "✅" },
  failed: { label: "Failed", class: "badge-failed", icon: "❌" },
  hitl_pending: { label: "Awaiting Review", class: "badge-pending", icon: "✋" },
  superseded: { label: "Superseded", class: "badge-info", icon: "⤼" },
  quota_exhausted: { label: "Quota Exhausted", class: "badge-failed", icon: "⏸" },
};

const VERDICT_CONFIG: Record<string, { label: string; class: string }> = {
  approve: { label: "Looks Good", class: "badge-completed" },
  comment: { label: "Comment", class: "badge-info" },
  request_changes: { label: "Changes Requested", class: "badge-critical" },
};

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const d = parseServerDate(dateStr).getTime();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function PRList({ reviews }: { reviews: Review[] }) {
  if (!reviews || reviews.length === 0) {
    return (
      <div className="glass-card p-8 text-center">
        <p className="mb-2 text-xl">📭</p>
        <p className="text-sm text-slate-400">No reviews yet</p>
        <p className="mt-1 text-xs text-slate-600">
          Trigger a review via webhook or the manual endpoint
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {reviews.map((review, i) => {
        const status = STATUS_CONFIG[review.status] || STATUS_CONFIG.pending;
        const verdict = review.verdict ? VERDICT_CONFIG[review.verdict] : null;

        return (
          <Link key={review.id} href={`/reviews/${review.id}`} className="block">
            <div
              className="animate-slide-up cursor-pointer glass-card p-4 transition-all duration-200"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center gap-2">
                    <h3 className="truncate text-sm font-semibold text-slate-100">
                      {review.pr_title || `PR #${review.pr_number}`}
                    </h3>
                    <span className={`badge ${status.class}`}>
                      {status.icon} {status.label}
                    </span>
                    {verdict && <span className={`badge ${verdict.class}`}>{verdict.label}</span>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span className="mono">{review.repo}</span>
                    <span>#{review.pr_number}</span>
                    {review.pr_author && <span>by {review.pr_author}</span>}
                    <span>{timeAgo(review.created_at)}</span>
                  </div>
                </div>
                <svg
                  className="mt-1 h-4 w-4 shrink-0 text-slate-600"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
