"use client";

import { ArrowUpRight } from "lucide-react";
import type { Finding } from "@/lib/types";
import { CategoryLabel, SeverityPill } from "./ui";

const EDGE: Record<string, string> = {
  critical: "var(--color-critical)",
  high: "var(--color-high)",
  medium: "var(--color-medium)",
  low: "var(--color-low)",
  info: "var(--color-info)",
};

export function FindingCard({ finding, actions }: { finding: Finding; actions?: React.ReactNode }) {
  return (
    <article
      className="overflow-hidden panel border-l-2"
      style={{ borderLeftColor: EDGE[finding.severity] ?? "var(--color-line)" }}
    >
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <SeverityPill severity={finding.severity} />
          <CategoryLabel category={finding.category} />
          {finding.cwe ? (
            <a
              href={`https://cwe.mitre.org/data/definitions/${finding.cwe.replace("CWE-", "")}.html`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-0.5 mono text-xs text-fg-muted hover:text-accent"
            >
              {finding.cwe}
              <ArrowUpRight className="h-3 w-3" aria-hidden />
            </a>
          ) : null}
          <div className="ml-auto flex items-center gap-3">
            {finding.confidence !== null && finding.confidence !== undefined ? (
              <span className="text-xs text-fg-subtle tabular" title="Confidence">
                {Math.round(finding.confidence * 100)}%
              </span>
            ) : null}
            {actions}
          </div>
        </div>

        <p className="mt-3 text-[15px] leading-relaxed text-fg">{finding.message}</p>

        <p className="mt-2 mono text-xs text-fg-subtle">
          {finding.file}
          {finding.line > 0 ? `:${finding.line}` : " (outside the changed lines)"}
          {finding.rule_id ? <span className="ml-3">{finding.rule_id}</span> : null}
        </p>

        {finding.evidence ? (
          <pre className="mt-3 overflow-x-auto rounded-md border border-line bg-canvas px-3 py-2 mono text-xs leading-relaxed text-fg-muted">
            {finding.evidence}
          </pre>
        ) : null}

        {finding.suggestion ? (
          <div className="mt-3 border-t border-line pt-3">
            <p className="text-xs font-medium text-fg-subtle">Suggested fix</p>
            <p className="mt-1 text-sm leading-relaxed whitespace-pre-wrap text-fg-muted">
              {finding.suggestion}
            </p>
          </div>
        ) : null}

        {finding.agent !== finding.category ? (
          <p className="mt-3 text-xs text-fg-subtle">Reported by the {finding.agent} agent.</p>
        ) : null}
      </div>
    </article>
  );
}
