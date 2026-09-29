"use client";

import Link from "next/link";
import { ChevronRight, GitPullRequest } from "lucide-react";
import { parseServerDate } from "@/lib/api";
import type { Review } from "@/lib/types";
import { EmptyState, StatusLabel, VerdictPill } from "./ui";

function timeAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - parseServerDate(dateStr).getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function PRList({ reviews }: { reviews: Review[] }) {
  if (!reviews || reviews.length === 0) {
    return (
      <EmptyState
        icon={GitPullRequest}
        title="No reviews yet"
        hint="Reviews start when a pull request is opened on an installed repository, or from the form on this page."
      />
    );
  }

  return (
    <ul className="divide-y divide-line overflow-hidden panel">
      {reviews.map((review) => (
        <li key={review.id}>
          <Link
            href={`/reviews/${review.id}`}
            className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-surface-2"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-fg">
                {review.pr_title || `Pull request #${review.pr_number}`}
              </p>
              <p className="mt-0.5 flex items-center gap-2 text-xs text-fg-subtle">
                <span className="truncate mono">
                  {review.repo}#{review.pr_number}
                </span>
                {review.pr_author ? <span>· {review.pr_author}</span> : null}
                <span>· {timeAgo(review.created_at)}</span>
              </p>
            </div>
            <div className="hidden w-32 shrink-0 sm:block">
              <StatusLabel status={review.status} />
            </div>
            <div className="w-28 shrink-0 text-right">
              {review.verdict ? <VerdictPill verdict={review.verdict} /> : null}
            </div>
            <ChevronRight
              className="h-4 w-4 shrink-0 text-fg-subtle transition-colors group-hover:text-fg"
              aria-hidden
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}
