"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Pencil, SearchX, Send, Trash2 } from "lucide-react";
import { DiffViewer } from "@/components/DiffViewer";
import { FindingCard } from "@/components/FindingCard";
import { Markdown } from "@/components/Markdown";
import { ReviewStream } from "@/components/ReviewStream";
import { EmptyState, SEVERITIES, StatusLabel, VERDICT } from "@/components/ui";
import {
  approveReview,
  deleteReview,
  errorMessage,
  getReviewDetail,
  getReviewDiff,
  updateFinding,
} from "@/lib/api";
import type { DiffFile, Finding, Review } from "@/lib/types";

type Tab = "findings" | "diff" | "summary";
type Notice = { tone: "success" | "warning" | "danger"; text: string } | null;
type Busy = "approving" | "deleting" | null;

const CATEGORIES = ["security", "quality", "performance"];

function VerdictBanner({ review, findings }: { review: Review; findings: Finding[] }) {
  const running = review.status === "running" || review.status === "pending";
  const blocking = findings.filter(
    (f) => f.category === "security" && (f.severity === "critical" || f.severity === "high"),
  ).length;
  const verdict = review.verdict ? VERDICT[review.verdict] : null;

  if (running || !verdict) {
    return (
      <div className="flex items-center justify-between gap-4 panel px-5 py-4">
        <div>
          <p className="text-xs text-fg-subtle">Status</p>
          <div className="mt-1">
            <StatusLabel status={review.status} />
          </div>
        </div>
        {review.error ? <p className="max-w-md text-sm text-danger">{review.error}</p> : null}
      </div>
    );
  }

  const Icon = verdict.icon;
  const detail =
    review.verdict === "request_changes"
      ? `${blocking} blocking security finding${blocking === 1 ? "" : "s"} of ${findings.length}`
      : `${findings.length} finding${findings.length === 1 ? "" : "s"}, none blocking`;
  return (
    <div className={`flex items-center gap-4 rounded-lg border px-5 py-4 ${verdict.tone}`}>
      <Icon className="h-6 w-6 shrink-0" aria-hidden />
      <div className="min-w-0">
        <p className="text-base font-semibold">{verdict.label}</p>
        <p className="text-sm text-fg-muted">{detail}</p>
      </div>
      <div className="ml-auto">
        <StatusLabel status={review.status} />
      </div>
    </div>
  );
}

function FilterChips({
  label,
  options,
  value,
  counts,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  counts: Record<string, number>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label={label}>
      {["all", ...options].map((option) => {
        const active = value === option;
        const count = option === "all" ? undefined : (counts[option] ?? 0);
        if (count === 0 && !active) return null;
        return (
          <button
            key={option}
            onClick={() => onChange(option)}
            aria-pressed={active}
            className={`rounded-md px-2 py-1 text-xs capitalize transition-colors ${
              active ? "bg-surface-3 text-fg" : "text-fg-subtle hover:text-fg"
            }`}
          >
            {option === "all" ? `All ${label.toLowerCase()}` : option}
            {count !== undefined ? (
              <span className="ml-1 text-fg-subtle tabular">{count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export default function ReviewDetailPage() {
  const params = useParams();
  const reviewId = params.id as string;
  const router = useRouter();

  const [review, setReview] = useState<Review | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("findings");
  const [category, setCategory] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [diffFiles, setDiffFiles] = useState<DiffFile[] | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ message: "", suggestion: "" });

  useEffect(() => {
    const fetchDetail = () =>
      getReviewDetail(reviewId)
        .then((data) => {
          setReview(data.review);
          setFindings(data.findings || []);
        })
        .catch(() => {
          // Unauthorized or not found: the page shows its own empty state
        })
        .finally(() => setLoading(false));
    fetchDetail();
    const interval = setInterval(fetchDetail, 5000);
    return () => clearInterval(interval);
  }, [reviewId]);

  useEffect(() => {
    if (tab !== "diff" || diffFiles || !review || review.status === "running") return;
    getReviewDiff(reviewId)
      .then((data) => setDiffFiles(data.files || []))
      .catch(() => setDiffFiles([]));
  }, [tab, diffFiles, review, reviewId]);

  const handleApprove = async () => {
    setBusy("approving");
    try {
      const data = await approveReview(reviewId);
      setReview((prev) => (prev ? { ...prev, status: "completed" } : null));
      setNotice(
        data.warning
          ? { tone: "warning", text: data.warning }
          : { tone: "success", text: "Review approved and posted to GitHub." },
      );
    } catch (error) {
      setNotice({ tone: "danger", text: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("Delete this review? It cannot be undone and has no effect on GitHub."))
      return;
    setBusy("deleting");
    try {
      await deleteReview(reviewId);
      router.push("/");
    } catch (error) {
      setNotice({ tone: "danger", text: errorMessage(error) });
      setBusy(null);
    }
  };

  const saveFinding = async (id: string) => {
    try {
      const data = await updateFinding(reviewId, id, editForm);
      setFindings((prev) => prev.map((f) => (f.id === id ? { ...f, ...data.finding } : f)));
      setEditingId(null);
    } catch (error) {
      setNotice({ tone: "danger", text: `Could not save the finding: ${errorMessage(error)}` });
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-16 animate-pulse panel" />
        <div className="h-20 animate-pulse panel" />
        <div className="h-72 animate-pulse panel" />
      </div>
    );
  }

  if (!review) {
    return <EmptyState icon={SearchX} title="Review not found" hint="It may have been deleted." />;
  }

  const categoryCounts: Record<string, number> = {};
  const severityCounts: Record<string, number> = {};
  findings.forEach((f) => {
    categoryCounts[f.category] = (categoryCounts[f.category] || 0) + 1;
    severityCounts[f.severity] = (severityCounts[f.severity] || 0) + 1;
  });
  const visible = findings.filter(
    (f) =>
      (category === "all" || f.category === category) &&
      (severity === "all" || f.severity === severity),
  );
  const canEdit = review.status === "hitl_pending";
  const finished = review.status !== "pending" && review.status !== "running";

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-fg-subtle hover:text-fg"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Reviews
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-fg">
              {review.pr_title || `Pull request #${review.pr_number}`}
            </h1>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-fg-subtle">
              <span className="mono">
                {review.repo}#{review.pr_number}
              </span>
              {review.pr_author ? <span>· {review.pr_author}</span> : null}
              {review.llm_model ? (
                <span
                  title={review.prompt_versions ? `Prompts: ${review.prompt_versions}` : undefined}
                >
                  · <span className="mono">{review.llm_model}</span>
                </span>
              ) : null}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {finished ? (
              <button onClick={handleDelete} disabled={busy !== null} className="btn-secondary">
                <Trash2 className="h-4 w-4" aria-hidden />
                {busy === "deleting" ? "Deleting..." : "Delete"}
              </button>
            ) : null}
            {review.status === "hitl_pending" ? (
              <button onClick={handleApprove} disabled={busy !== null} className="btn-primary">
                <Send className="h-4 w-4" aria-hidden />
                {busy === "approving" ? "Posting..." : "Approve and post"}
              </button>
            ) : null}
          </div>
        </div>
      </div>

      <VerdictBanner review={review} findings={findings} />

      {notice ? (
        <p
          role="status"
          className={`rounded-md border px-4 py-3 text-sm ${
            notice.tone === "danger"
              ? "tone-critical"
              : notice.tone === "warning"
                ? "tone-medium"
                : "tone-low"
          }`}
        >
          {notice.text}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <section className="min-w-0 space-y-4">
          <div className="flex items-center gap-1 border-b border-line" role="tablist">
            {(
              [
                ["findings", `Findings`, findings.length],
                ["diff", "Diff", null],
                ["summary", "Summary", null],
              ] as const
            ).map(([id, label, count]) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
                  tab === id
                    ? "border-fg text-fg"
                    : "border-transparent text-fg-subtle hover:text-fg"
                }`}
              >
                {label}
                {count !== null ? (
                  <span className="ml-1.5 text-fg-subtle tabular">{count}</span>
                ) : null}
              </button>
            ))}
          </div>

          {tab === "findings" ? (
            <div className="space-y-3">
              {findings.length > 0 ? (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <FilterChips
                    label="Severities"
                    options={[...SEVERITIES]}
                    value={severity}
                    counts={severityCounts}
                    onChange={setSeverity}
                  />
                  <FilterChips
                    label="Categories"
                    options={CATEGORIES}
                    value={category}
                    counts={categoryCounts}
                    onChange={setCategory}
                  />
                </div>
              ) : null}

              {visible.map((finding) =>
                editingId === finding.id ? (
                  <div key={finding.id} className="space-y-3 panel border-accent/50 p-4">
                    <p className="text-sm font-medium text-fg">Edit finding</p>
                    <textarea
                      className="field"
                      rows={3}
                      aria-label="Message"
                      value={editForm.message}
                      onChange={(e) => setEditForm({ ...editForm, message: e.target.value })}
                    />
                    <textarea
                      className="field mono"
                      rows={3}
                      aria-label="Suggested fix"
                      placeholder="Suggested fix (optional)"
                      value={editForm.suggestion}
                      onChange={(e) => setEditForm({ ...editForm, suggestion: e.target.value })}
                    />
                    <div className="flex justify-end gap-2">
                      <button className="btn-secondary" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                      <button className="btn-primary" onClick={() => saveFinding(finding.id)}>
                        Save
                      </button>
                    </div>
                  </div>
                ) : (
                  <FindingCard
                    key={finding.id}
                    finding={finding}
                    actions={
                      canEdit ? (
                        <button
                          onClick={() => {
                            setEditingId(finding.id);
                            setEditForm({
                              message: finding.message,
                              suggestion: finding.suggestion || "",
                            });
                          }}
                          className="inline-flex items-center gap-1 text-xs text-fg-subtle hover:text-fg"
                        >
                          <Pencil className="h-3.5 w-3.5" aria-hidden />
                          Edit
                        </button>
                      ) : null
                    }
                  />
                ),
              )}

              {visible.length === 0 ? (
                <EmptyState
                  icon={SearchX}
                  title={
                    findings.length === 0
                      ? finished
                        ? "No issues found"
                        : "The agents are still reviewing"
                      : "No findings match these filters"
                  }
                />
              ) : null}
            </div>
          ) : null}

          {tab === "diff" ? (
            <div className="space-y-4">
              {review.status === "running" ? (
                <EmptyState icon={SearchX} title="The diff is shown when the review completes" />
              ) : diffFiles === null ? (
                <div className="h-48 animate-pulse panel" />
              ) : diffFiles && diffFiles.length > 0 ? (
                diffFiles.map((file) => (
                  <DiffViewer
                    key={file.filename}
                    filename={file.filename}
                    patch={file.patch}
                    findings={findings}
                  />
                ))
              ) : (
                <EmptyState icon={SearchX} title="No diff available for this review" />
              )}
            </div>
          ) : null}

          {tab === "summary" ? (
            review.summary ? (
              <div className="panel p-5">
                <Markdown>{review.summary}</Markdown>
              </div>
            ) : (
              <EmptyState icon={SearchX} title="The summary is written when the review completes" />
            )
          ) : null}
        </section>

        <aside>
          <ReviewStream reviewId={reviewId} />
        </aside>
      </div>
    </div>
  );
}
