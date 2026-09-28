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

function confidenceLabel(confidence: number): { text: string; className: string } {
  const pct = Math.round(confidence * 100);
  if (confidence >= 0.8) return { text: `${pct}% confidence`, className: "text-emerald-400/80" };
  if (confidence >= 0.5) return { text: `${pct}% confidence`, className: "text-slate-400" };
  return { text: `${pct}% confidence`, className: "text-amber-400/80" };
}

export function FindingCard({ finding }: { finding: Finding }) {
  const severity = SEVERITY_CONFIG[finding.severity] || SEVERITY_CONFIG.info;
  const catIcon = CATEGORY_ICONS[finding.category] || "📋";
  const confidence =
    finding.confidence !== null && finding.confidence !== undefined
      ? confidenceLabel(finding.confidence)
      : null;

  return (
    <div className="animate-slide-up glass-card p-4 transition-all duration-200">
      <div className="flex items-start gap-3">
        {/* Severity indicator */}
        <div
          className="w-1 shrink-0 self-stretch rounded-full"
          style={{ background: `var(--${finding.severity})` }}
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
            {finding.cwe ? (
              <a
                href={`https://cwe.mitre.org/data/definitions/${finding.cwe.replace("CWE-", "")}.html`}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-sm bg-red-500/10 px-1.5 py-0.5 mono text-[10px] text-red-300 hover:underline"
              >
                {finding.cwe}
              </a>
            ) : null}
            {finding.rule_id ? (
              <span className="rounded-sm bg-slate-800/50 px-1.5 py-0.5 mono text-[10px] text-slate-500">
                {finding.rule_id}
              </span>
            ) : null}
            <span className="ml-auto flex items-center gap-3 text-xs">
              {confidence ? <span className={confidence.className}>{confidence.text}</span> : null}
              <span className="text-slate-600">
                {finding.agent === finding.category
                  ? `by ${finding.agent} agent`
                  : `found by ${finding.agent} agent`}
              </span>
            </span>
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
            {finding.line > 0 ? (
              <span className="mono text-slate-600">:L{finding.line}</span>
            ) : (
              <span className="text-slate-600">(not on a changed line)</span>
            )}
          </div>

          {/* Message */}
          <p className="mb-2 text-sm leading-relaxed text-slate-300">{finding.message}</p>

          {/* Quoted code */}
          {finding.evidence ? (
            <pre className="mb-2 overflow-x-auto rounded-md border border-white/5 bg-black/30 px-3 py-2 mono text-[11px] leading-relaxed text-slate-400">
              {finding.evidence}
            </pre>
          ) : null}

          {/* Suggestion */}
          {finding.suggestion ? (
            <div className="mt-2 rounded-lg border border-indigo-500/10 bg-indigo-500/5 p-3">
              <p className="mb-1 text-xs font-medium text-indigo-400">💡 Suggestion</p>
              <p className="mono text-xs leading-relaxed whitespace-pre-wrap text-slate-400">
                {finding.suggestion}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
