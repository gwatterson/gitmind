"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ReviewStream } from "@/components/ReviewStream";
import { FindingCard } from "@/components/FindingCard";
import { DiffViewer } from "@/components/DiffViewer";
import type { Review, Finding, StreamEvent } from "@/lib/types";

const VERDICT_CONFIG: Record<string, { label: string; class: string; icon: string }> = {
    approve: { label: "Approved", class: "badge-completed", icon: "✅" },
    comment: { label: "Comment", class: "badge-info", icon: "💬" },
    request_changes: { label: "Changes Requested", class: "badge-critical", icon: "🔴" },
};

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const CATEGORY_ICONS: Record<string, string> = {
    security: "🔒",
    quality: "📐",
    performance: "⚡",
};

export default function ReviewDetailPage() {
    const params = useParams();
    const reviewId = params.id as string;

    const [review, setReview] = useState<Review | null>(null);
    const [findings, setFindings] = useState<Finding[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<"findings" | "diff">("findings");
    const [filterCategory, setFilterCategory] = useState("all");
    const [filterSeverity, setFilterSeverity] = useState("all");

    useEffect(() => {
        const fetchDetail = async () => {
            try {
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
                const res = await fetch(`${apiUrl}/api/reviews/${reviewId}`);
                if (res.ok) {
                    const data = await res.json();
                    setReview(data.review);
                    setFindings(data.findings || []);
                }
            } catch {
                // silent
            } finally {
                setLoading(false);
            }
        };

        fetchDetail();
        // Refresh while running
        const interval = setInterval(fetchDetail, 5000);
        return () => clearInterval(interval);
    }, [reviewId]);

    const [approveStatus, setApproveStatus] = useState<string | null>(null);

    const handleApprove = async () => {
        setApproveStatus("approving...");
        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
            const res = await fetch(`${apiUrl}/api/reviews/${reviewId}/approve`, {
                method: "POST",
            });
            const data = await res.json();
            if (res.ok) {
                setReview((prev) => (prev ? { ...prev, status: "completed" } : null));
                if (data.warning) {
                    setApproveStatus(`⚠️ ${data.warning}`);
                } else {
                    setApproveStatus("✅ Review approved and posted to GitHub.");
                }
            } else {
                setApproveStatus(`❌ ${data.detail || "Failed to approve"}`);
            }
        } catch (e) {
            setApproveStatus(`❌ ${e instanceof Error ? e.message : "Network error"}`);
        }
    };

    if (loading) {
        return (
            <div className="space-y-4 animate-pulse">
                <div className="glass-card h-20" />
                <div className="grid grid-cols-2 gap-4">
                    <div className="glass-card h-60" />
                    <div className="glass-card h-60" />
                </div>
            </div>
        );
    }

    if (!review) {
        return (
            <div className="glass-card p-8 text-center">
                <p className="text-xl mb-2">🔍</p>
                <p className="text-slate-400">Review not found</p>
            </div>
        );
    }

    const verdict = review.verdict ? VERDICT_CONFIG[review.verdict] : null;

    // Group findings by category
    const categoryCounts: Record<string, number> = {};
    const severityCounts: Record<string, number> = {};
    findings.forEach((f) => {
        categoryCounts[f.category] = (categoryCounts[f.category] || 0) + 1;
        severityCounts[f.severity] = (severityCounts[f.severity] || 0) + 1;
    });

    const filteredFindings = findings.filter((f) => {
        if (filterCategory !== "all" && f.category !== filterCategory) return false;
        if (filterSeverity !== "all" && f.severity !== filterSeverity) return false;
        return true;
    });

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Back + Header */}
            <div>
                <a
                    href="/"
                    className="text-xs text-slate-500 hover:text-slate-300 transition-colors mb-2 inline-block"
                >
                    ← Back to Dashboard
                </a>
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <h1 className="text-xl font-bold text-slate-100 mb-1">
                            {review.pr_title || `PR #${review.pr_number}`}
                        </h1>
                        <div className="flex items-center gap-3 text-xs text-slate-500">
                            <span className="mono">{review.repo}</span>
                            <span>#{review.pr_number}</span>
                            {review.pr_author && <span>by {review.pr_author}</span>}
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {verdict && (
                            <span className={`badge text-sm ${verdict.class}`}>
                                {verdict.icon} {verdict.label}
                            </span>
                        )}
                        {review.status === "hitl_pending" && (
                            <button
                                onClick={handleApprove}
                                disabled={approveStatus === "approving..."}
                                className="btn-primary text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                                {approveStatus === "approving..." ? "⏳ Approving..." : "✅ Approve & Post"}
                            </button>
                        )}
                    </div>
                </div>
                {approveStatus && approveStatus !== "approving..." && (
                    <div className={`mt-3 p-3 rounded-md border text-sm ${approveStatus.startsWith("❌") ? "bg-red-500/10 border-red-500/20 text-red-400" : approveStatus.startsWith("⚠️") ? "bg-amber-500/10 border-amber-500/20 text-amber-400" : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"}`}>
                        <p>{approveStatus}</p>
                    </div>
                )}
            </div>

            {/* Main content */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left panel — Reasoning trace */}
                <div className="lg:col-span-1">
                    <ReviewStream reviewId={reviewId} />
                </div>

                {/* Right panel — Findings / Diff */}
                <div className="lg:col-span-2 space-y-4">
                    {/* Tab switcher */}
                    <div className="flex items-center gap-2 border-b border-white/5 pb-2">
                        <button
                            onClick={() => setActiveTab("findings")}
                            className={`text-sm font-medium px-3 py-1.5 rounded-md transition-all ${activeTab === "findings"
                                ? "bg-indigo-500/10 text-indigo-400"
                                : "text-slate-500 hover:text-slate-300"
                                }`}
                        >
                            🔍 Findings ({findings.length})
                        </button>
                        <button
                            onClick={() => setActiveTab("diff")}
                            className={`text-sm font-medium px-3 py-1.5 rounded-md transition-all ${activeTab === "diff"
                                ? "bg-indigo-500/10 text-indigo-400"
                                : "text-slate-500 hover:text-slate-300"
                                }`}
                        >
                            📄 Diff
                        </button>
                    </div>

                    {activeTab === "findings" && (
                        <div className="space-y-3">
                            {/* Filters */}
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-xs text-slate-600">Category:</span>
                                {["all", "security", "quality", "performance"].map((cat) => (
                                    <button
                                        key={cat}
                                        onClick={() => setFilterCategory(cat)}
                                        className={`badge cursor-pointer transition-all text-[11px] ${filterCategory === cat
                                            ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30"
                                            : "bg-slate-800/50 text-slate-500"
                                            }`}
                                    >
                                        {cat === "all"
                                            ? `All (${findings.length})`
                                            : `${CATEGORY_ICONS[cat] || ""} ${cat} (${categoryCounts[cat] || 0})`}
                                    </button>
                                ))}
                                <span className="text-slate-800">|</span>
                                <span className="text-xs text-slate-600">Severity:</span>
                                {["all", ...SEVERITY_ORDER].map((sev) => (
                                    <button
                                        key={sev}
                                        onClick={() => setFilterSeverity(sev)}
                                        className={`badge cursor-pointer transition-all text-[11px] ${filterSeverity === sev
                                            ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30"
                                            : "bg-slate-800/50 text-slate-500"
                                            }`}
                                    >
                                        {sev === "all" ? `All` : `${sev} (${severityCounts[sev] || 0})`}
                                    </button>
                                ))}
                            </div>

                            {/* Finding cards */}
                            {filteredFindings.map((finding) => (
                                <FindingCard key={finding.id} finding={finding} />
                            ))}
                            {filteredFindings.length === 0 && (
                                <div className="glass-card p-6 text-center">
                                    <p className="text-slate-500 text-sm">
                                        {findings.length === 0
                                            ? "No findings yet — review may still be running."
                                            : "No findings match the selected filters."}
                                    </p>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === "diff" && (
                        <div className="glass-card p-6 text-center">
                            <p className="text-slate-500 text-sm">
                                Diff viewer will display annotated code once the review completes.
                            </p>
                        </div>
                    )}

                    {/* Summary */}
                    {review.summary && (
                        <div className="glass-card p-4">
                            <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-2">
                                Review Summary
                            </h3>
                            <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                                {review.summary}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
