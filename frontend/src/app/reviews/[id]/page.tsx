"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ReviewStream } from "@/components/ReviewStream";
import { FindingCard } from "@/components/FindingCard";
import { DiffViewer } from "@/components/DiffViewer";
import {
  approveReview,
  deleteReview,
  errorMessage,
  getReviewDetail,
  getReviewDiff,
  updateFinding,
} from "@/lib/api";
import type { Review, Finding, DiffFile } from "@/lib/types";

const VERDICT_CONFIG: Record<string, { label: string; class: string; icon: string }> = {
  approve: { label: "Looks Good", class: "badge-completed", icon: "✅" },
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
  const [diffFiles, setDiffFiles] = useState<DiffFile[] | null>(null);
  const [loadingDiff, setLoadingDiff] = useState(false);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        const data = await getReviewDetail(reviewId);
        setReview(data.review);
        setFindings(data.findings || []);
      } catch {
        // Unauthorized or not found: the page shows its own empty state
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
    // Refresh while running
    const interval = setInterval(fetchDetail, 5000);
    return () => clearInterval(interval);
  }, [reviewId]);

  // Fetch diff on-demand when user switches to "diff" tab
  useEffect(() => {
    if (activeTab === "diff" && !diffFiles && review && review.status !== "running") {
      const fetchDiff = async () => {
        setLoadingDiff(true);
        try {
          const data = await getReviewDiff(reviewId);
          setDiffFiles(data.files || []);
        } catch (error) {
          console.error("Failed to fetch diff", error);
        } finally {
          setLoadingDiff(false);
        }
      };
      fetchDiff();
    }
  }, [activeTab, diffFiles, review, reviewId]);

  const [actionStatus, setActionStatus] = useState<string | null>(null);

  const handleApprove = async () => {
    setActionStatus("approving...");
    try {
      const data = await approveReview(reviewId);
      setReview((prev) => (prev ? { ...prev, status: "completed" } : null));
      if (data.warning) {
        setActionStatus(`⚠️ ${data.warning}`);
      } else {
        setActionStatus("✅ Review approved and posted to GitHub.");
      }
    } catch (error) {
      setActionStatus(`❌ ${errorMessage(error)}`);
    }
  };

  const handleRejectAndDelete = async () => {
    if (
      !confirm(
        "Are you sure you want to delete this review? This action cannot be undone and has no effect on GitHub.",
      )
    )
      return;

    setActionStatus("rejecting...");
    try {
      await deleteReview(reviewId);
      window.location.href = "/";
    } catch (error) {
      setActionStatus(`❌ ${errorMessage(error)}`);
    }
  };

  // Editing states
  const [editingFindingId, setEditingFindingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ message: "", suggestion: "" });

  const startEditing = (f: Finding) => {
    setEditingFindingId(f.id);
    setEditForm({ message: f.message, suggestion: f.suggestion || "" });
  };

  const saveFinding = async (id: string) => {
    try {
      const data = await updateFinding(reviewId, id, editForm);
      setFindings((prev) => prev.map((f) => (f.id === id ? { ...f, ...data.finding } : f)));
      setEditingFindingId(null);
    } catch (error) {
      setActionStatus(`❌ Could not save the finding: ${errorMessage(error)}`);
    }
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
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
        <p className="mb-2 text-xl">🔍</p>
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
    <div className="animate-fade-in space-y-6">
      {/* Back + Header */}
      <div>
        <a
          href="/"
          className="mb-2 inline-block text-xs text-slate-500 transition-colors hover:text-slate-300"
        >
          ← Back to Dashboard
        </a>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="mb-1 text-xl font-bold text-slate-100">
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
                disabled={actionStatus === "approving..." || actionStatus === "rejecting..."}
                className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-40"
              >
                {actionStatus === "approving..." ? "⏳ Approving..." : "✅ Approve & Post"}
              </button>
            )}
            {review.status !== "pending" && review.status !== "running" && (
              <button
                onClick={handleRejectAndDelete}
                disabled={actionStatus === "approving..." || actionStatus === "rejecting..."}
                className="rounded-md bg-rose-600 px-4 py-1.5 text-sm font-medium text-white shadow-lg transition-colors hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {actionStatus === "rejecting..." ? "⏳ Deleting..." : "🗑️ Reject & Delete"}
              </button>
            )}
          </div>
        </div>
        {actionStatus && actionStatus !== "approving..." && actionStatus !== "rejecting..." && (
          <div
            className={`mt-3 rounded-md border p-3 text-sm ${actionStatus.startsWith("❌") ? "border-red-500/20 bg-red-500/10 text-red-400" : actionStatus.startsWith("⚠️") ? "border-amber-500/20 bg-amber-500/10 text-amber-400" : actionStatus.startsWith("🚫") ? "border-rose-500/20 bg-rose-500/10 text-rose-400" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"}`}
          >
            <p>{actionStatus}</p>
          </div>
        )}
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left panel: Reasoning trace */}
        <div className="lg:col-span-1">
          <ReviewStream reviewId={reviewId} />
        </div>

        {/* Right panel: Findings / Diff */}
        <div className="space-y-4 lg:col-span-2">
          {/* Tab switcher */}
          <div className="flex items-center gap-2 border-b border-white/5 pb-2">
            <button
              onClick={() => setActiveTab("findings")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                activeTab === "findings"
                  ? "bg-indigo-500/10 text-indigo-400"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              🔍 Findings ({findings.length})
            </button>
            <button
              onClick={() => setActiveTab("diff")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
                activeTab === "diff"
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
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-600">Category:</span>
                {["all", "security", "quality", "performance"].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setFilterCategory(cat)}
                    className={`badge cursor-pointer text-[11px] transition-all ${
                      filterCategory === cat
                        ? "border border-indigo-500/30 bg-indigo-500/20 text-indigo-400"
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
                    className={`badge cursor-pointer text-[11px] transition-all ${
                      filterSeverity === sev
                        ? "border border-indigo-500/30 bg-indigo-500/20 text-indigo-400"
                        : "bg-slate-800/50 text-slate-500"
                    }`}
                  >
                    {sev === "all" ? `All` : `${sev} (${severityCounts[sev] || 0})`}
                  </button>
                ))}
              </div>

              {/* Finding cards */}
              {filteredFindings.map((finding) => (
                <div key={finding.id} className="group relative">
                  {editingFindingId === finding.id ? (
                    <div className="glass-card space-y-3 border border-indigo-500/50 p-4">
                      <div className="text-sm font-semibold text-slate-200">Edit Finding</div>
                      <textarea
                        className="w-full rounded border border-white/10 bg-slate-900/50 p-2 text-sm text-slate-300 focus:border-indigo-500 focus:outline-none"
                        rows={3}
                        value={editForm.message}
                        onChange={(e) => setEditForm({ ...editForm, message: e.target.value })}
                      />
                      <textarea
                        className="w-full rounded border border-white/10 bg-slate-900/50 p-2 font-mono text-sm text-slate-300 focus:border-indigo-500 focus:outline-none"
                        rows={3}
                        placeholder="Suggestion (optional)"
                        value={editForm.suggestion}
                        onChange={(e) => setEditForm({ ...editForm, suggestion: e.target.value })}
                      />
                      <div className="mt-2 flex justify-end gap-2">
                        <button
                          className="rounded-md border border-white/5 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-slate-700"
                          onClick={() => setEditingFindingId(null)}
                        >
                          Cancel
                        </button>
                        <button
                          className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs text-white transition-colors hover:bg-indigo-500"
                          onClick={() => saveFinding(finding.id)}
                        >
                          Save Changes
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <FindingCard finding={finding} />
                      {review.status === "hitl_pending" && finding.id && (
                        <button
                          onClick={() => startEditing(finding)}
                          className="absolute right-3 top-3 rounded-md border border-white/10 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 opacity-0 shadow-lg transition-opacity hover:bg-slate-700 group-hover:opacity-100"
                        >
                          ✏️ Edit
                        </button>
                      )}
                    </>
                  )}
                </div>
              ))}
              {filteredFindings.length === 0 && (
                <div className="glass-card p-6 text-center">
                  <p className="text-sm text-slate-500">
                    {findings.length === 0
                      ? "No findings yet. The review may still be running."
                      : "No findings match the selected filters."}
                  </p>
                </div>
              )}
            </div>
          )}

          {activeTab === "diff" && (
            <div className="space-y-4">
              {review.status === "running" ? (
                <div className="glass-card animate-pulse p-6 text-center">
                  <p className="text-sm text-slate-500">
                    Diff viewer will display annotated code once the review completes.
                  </p>
                </div>
              ) : loadingDiff ? (
                <div className="glass-card animate-pulse p-6 text-center">
                  <p className="text-sm text-slate-500">Loading diff data...</p>
                </div>
              ) : diffFiles && diffFiles.length > 0 ? (
                diffFiles.map((file, idx) => (
                  <DiffViewer
                    key={idx}
                    filename={file.filename}
                    patch={file.patch}
                    findings={findings}
                  />
                ))
              ) : (
                <div className="glass-card p-6 text-center">
                  <p className="text-sm text-slate-500">No diff data available for this review.</p>
                </div>
              )}
            </div>
          )}

          {/* Summary */}
          {review.summary && (
            <div className="glass-card p-4">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-200">
                Review Summary
              </h3>
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
                {review.summary}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
