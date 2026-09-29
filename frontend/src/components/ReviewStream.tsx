"use client";

import { useEffect, useState } from "react";
import { createReviewStream } from "@/lib/api";
import type { StreamEvent } from "@/lib/types";

function eventTone(type: string): string {
  if (type.includes("error") || type.includes("failed")) return "bg-danger";
  if (type.includes("hitl")) return "bg-warning";
  if (type.includes("done") || type.includes("complete")) return "bg-success";
  return "bg-fg-subtle";
}

const STAGE: Record<string, string> = {
  review: "Review",
  supervisor: "Supervisor",
  security: "Security",
  quality: "Quality",
  performance: "Performance",
  verify: "Verifier",
  synthesis: "Synthesis",
  hitl: "Approval",
  publish: "GitHub",
  stream: "Stream",
};

/** Timeline of the pipeline steps, streamed over Server-Sent Events. */
export function ReviewStream({ reviewId }: { reviewId: string }) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const sse = createReviewStream(reviewId);
    sse.onopen = () => setConnected(true);
    sse.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as StreamEvent;
        setEvents((prev) => [...prev, event]);
        if (["stream_end", "review_complete", "review_error"].includes(event.type)) {
          sse.close();
          setConnected(false);
        }
      } catch {
        // Ignore malformed events
      }
    };
    sse.onerror = () => {
      sse.close();
      setConnected(false);
    };
    return () => sse.close();
  }, [reviewId]);

  return (
    <div className="panel">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-sm font-medium text-fg">Pipeline</h2>
        <span className="inline-flex items-center gap-1.5 text-xs text-fg-subtle">
          <span
            className={`h-1.5 w-1.5 rounded-full ${connected ? "animate-pulse-dot bg-accent" : "bg-fg-subtle"}`}
            aria-hidden
          />
          {connected ? "Live" : "Finished"}
        </span>
      </div>
      <ol className="max-h-[520px] overflow-y-auto px-4 py-3">
        {events.length === 0 ? (
          <li className="text-sm text-fg-subtle">Waiting for events...</li>
        ) : null}
        {events
          .filter((event) => event.type !== "stream_end")
          .map((event, i) => {
            const stage = STAGE[event.type.split("_")[0]] ?? "";
            return (
              <li key={i} className="relative flex gap-3 pb-3 last:pb-0">
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${eventTone(event.type)}`}
                  aria-hidden
                />
                <div className="min-w-0">
                  {stage ? <p className="text-xs text-fg-subtle">{stage}</p> : null}
                  <p className="text-sm leading-snug text-fg-muted">{event.message}</p>
                </div>
              </li>
            );
          })}
      </ol>
    </div>
  );
}
