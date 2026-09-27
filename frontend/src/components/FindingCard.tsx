"use client";

import type { Finding } from "@/lib/types";

const SEVERITY_CONFIG: Record<string, { class: string; icon: string; label: string }> = {
  critical: { class: "badge-critical", icon: "🔴", label: "Critical" },
  high: { class: "badge-high", icon: "🟠", label: "High" },
  medium: { class: "badge-medium", icon: "🟡", label: "Medium" },
  low: { class: "badge-low", icon: "🟢", label: "Low" },
  info: { class: "badge-info", icon: "🔵", label: "Info" },
};

const CATEGORY_ICONS: Record<string, string> = {
  security: "🔒",
  quality: "📐",
  performance: "⚡",
};

export function FindingCard({
  finding,
  onEdit,
}: {
  finding: Finding;
  onEdit?: (finding: Finding) => void;
}) {
  const severity = SEVERITY_CONFIG[finding.severity] || SEVERITY_CONFIG.info;
  const catIcon = CATEGORY_ICONS[finding.category] || "📋";

  return (
    <div className="animate-slide-up glass-card p-4 transition-all duration-200">
      <div className="flex items-start gap-3">
        {/* Severity indicator */}
        <div
          className="w-1 shrink-0 self-stretch rounded-full"
          style={{
            background: `var(--${finding.severity})`,
          }}
        />

        <div className="min-w-0 flex-1">
          {/* Header */}
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className={`badge ${severity.class}`}>
              {severity.icon} {severity.label}
            </span>
            <span
              className="badge"
              style={{ background: "var(--glass-bg)", color: "var(--text-secondary)" }}
            >
              {catIcon} {finding.category}
            </span>
            {finding.rule_id && (
              <span className="rounded-sm bg-slate-800/50 px-1.5 py-0.5 mono text-[10px] text-slate-600">
                {finding.rule_id}
              </span>
            )}
            <span className="ml-auto text-xs text-slate-600">by {finding.agent} agent</span>
          </div>

          {/* File location */}
          <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <span className="truncate mono">{finding.file}</span>
            {finding.line > 0 && <span className="mono text-slate-600">:L{finding.line}</span>}
          </div>

          {/* Message */}
          <p className="mb-2 text-sm leading-relaxed text-slate-300">{finding.message}</p>

          {/* Suggestion */}
          {finding.suggestion && (
            <div className="mt-2 rounded-lg border border-indigo-500/10 bg-indigo-500/5 p-3">
              <p className="mb-1 text-xs font-medium text-indigo-400">💡 Suggestion</p>
              <p className="mono text-xs leading-relaxed whitespace-pre-wrap text-slate-400">
                {finding.suggestion}
              </p>
            </div>
          )}

          {/* Edit button for HITL */}
          {onEdit && (
            <button onClick={() => onEdit(finding)} className="mt-3 btn-secondary text-xs">
              ✏️ Edit
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function FindingsList({
  findings,
  onEdit,
}: {
  findings: Finding[];
  onEdit?: (finding: Finding) => void;
}) {
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [filterSeverity, setFilterSeverity] = useState<string>("all");

  const filtered = findings.filter((f) => {
    if (filterCategory !== "all" && f.category !== filterCategory) return false;
    if (filterSeverity !== "all" && f.severity !== filterSeverity) return false;
    return true;
  });

  return (
    <div>
      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-slate-500">Filter:</span>
        {["all", "security", "quality", "performance"].map((cat) => (
          <button
            key={cat}
            onClick={() => setFilterCategory(cat)}
            className={`badge cursor-pointer transition-all ${
              filterCategory === cat
                ? "border border-indigo-500/30 bg-indigo-500/20 text-indigo-400"
                : "border border-transparent bg-slate-800/50 text-slate-500"
            }`}
          >
            {cat === "all" ? "All" : `${CATEGORY_ICONS[cat] || ""} ${cat}`}
          </button>
        ))}
        <span className="text-slate-700">|</span>
        {["all", "critical", "high", "medium", "low", "info"].map((sev) => (
          <button
            key={sev}
            onClick={() => setFilterSeverity(sev)}
            className={`badge cursor-pointer transition-all ${
              filterSeverity === sev
                ? "border border-indigo-500/30 bg-indigo-500/20 text-indigo-400"
                : "border border-transparent bg-slate-800/50 text-slate-500"
            }`}
          >
            {sev === "all" ? "All" : `${(SEVERITY_CONFIG[sev] || {}).icon || ""} ${sev}`}
          </button>
        ))}
      </div>

      {/* Results */}
      <div className="space-y-2">
        {filtered.map((finding) => (
          <FindingCard key={finding.id} finding={finding} onEdit={onEdit} />
        ))}
        {filtered.length === 0 && (
          <p className="py-4 text-center text-sm text-slate-500">
            No findings match the selected filters.
          </p>
        )}
      </div>
    </div>
  );
}

import { useState } from "react";
