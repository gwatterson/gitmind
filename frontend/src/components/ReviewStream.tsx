"use client";

import { useEffect, useState } from "react";
import type { StreamEvent } from "@/lib/types";

const EVENT_ICONS: Record<string, string> = {
    review_start: "🚀",
    supervisor_start: "🧠",
    supervisor_done: "✅",
    security_start: "🔒",
    security_done: "🛡️",
    quality_start: "📐",
    quality_done: "📋",
    performance_start: "⚡",
    performance_done: "🏎️",
    synthesis_start: "🔄",
    synthesis_done: "📝",
    hitl_waiting: "✋",
    hitl_approved: "👍",
    review_complete: "🎉",
    review_error: "❌",
    stream_end: "🏁",
};

function getEventColor(type: string): string {
    if (type.includes("error")) return "text-red-400";
    if (type.includes("done") || type.includes("complete")) return "text-emerald-400";
    if (type.includes("start")) return "text-sky-400";
    if (type.includes("hitl")) return "text-amber-400";
    return "text-slate-400";
}

export function ReviewStream({ reviewId }: { reviewId: string }) {
    const [events, setEvents] = useState<StreamEvent[]>([]);
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const sse = new EventSource(`${apiUrl}/api/stream/${reviewId}`);

        sse.onopen = () => setConnected(true);

        sse.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data) as StreamEvent;
                setEvents((prev) => [...prev, event]);
                if (
                    event.type === "stream_end" ||
                    event.type === "review_complete" ||
                    event.type === "review_error"
                ) {
                    sse.close();
                    setConnected(false);
                }
            } catch {
                // Ignore parse errors
            }
        };

        sse.onerror = () => {
            sse.close();
            setConnected(false);
        };

        return () => sse.close();
    }, [reviewId]);

    return (
        <div className="glass-card p-4">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
                    Reasoning Trace
                </h3>
                <span
                    className={`badge ${connected ? "badge-running" : "badge-completed"}`}
                >
                    <span
                        className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-sky-400 animate-pulse-glow" : "bg-emerald-400"
                            }`}
                    />
                    {connected ? "Live" : "Finished"}
                </span>
            </div>

            <div className="space-y-1 max-h-[500px] overflow-y-auto pr-2">
                {events.length === 0 && (
                    <p className="text-sm text-slate-500 italic">Waiting for events…</p>
                )}
                {events.map((event, i) => (
                    <div
                        key={i}
                        className="flex items-start gap-3 py-1.5 animate-slide-up"
                    >
                        <span className="text-base mt-0.5 flex-shrink-0">
                            {EVENT_ICONS[event.type] || "•"}
                        </span>
                        <div className="flex-1 min-w-0">
                            <p
                                className={`text-sm mono leading-relaxed ${getEventColor(
                                    event.type
                                )}`}
                            >
                                {event.message}
                            </p>
                        </div>
                        <span className="text-[10px] text-slate-600 mono flex-shrink-0 mt-0.5">
                            {event.timestamp
                                ? new Date(event.timestamp).toLocaleTimeString()
                                : ""}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}
