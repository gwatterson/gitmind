"use client";

import type { Finding } from "@/lib/types";

/**
 * DiffViewer: displays a PR diff with inline finding annotations.
 * Uses a simple syntax-highlighted view (no heavy library dependency).
 */

function parsePatch(patch: string): Array<{
  type: "add" | "del" | "ctx" | "header";
  content: string;
  lineNum: number | null;
}> {
  if (!patch) return [];
  const lines = patch.split("\n");
  const parsed: Array<{
    type: "add" | "del" | "ctx" | "header";
    content: string;
    lineNum: number | null;
  }> = [];

  let currentLine = 0;

  for (const line of lines) {
    if (line.startsWith("@@")) {
      // Extract line number from hunk header
      const match = line.match(/@@ -\d+(?:,\d+)? \+(\d+)/);
      if (match) currentLine = parseInt(match[1], 10) - 1;
      parsed.push({ type: "header", content: line, lineNum: null });
    } else if (line.startsWith("+")) {
      currentLine++;
      parsed.push({ type: "add", content: line.slice(1), lineNum: currentLine });
    } else if (line.startsWith("-")) {
      parsed.push({ type: "del", content: line.slice(1), lineNum: null });
    } else {
      currentLine++;
      parsed.push({ type: "ctx", content: line.slice(1) || line, lineNum: currentLine });
    }
  }

  return parsed;
}

const LINE_COLORS = {
  add: "bg-emerald-500/10 border-l-2 border-emerald-500/40",
  del: "bg-danger/10 border-l-2 border-red-500/40",
  ctx: "border-l-2 border-transparent",
  header: "bg-accent-soft border-l-2 border-accent/30",
};

const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-yellow-500",
  low: "bg-green-500",
  info: "bg-blue-500",
};

export function DiffViewer({
  filename,
  patch,
  findings,
}: {
  filename: string;
  patch: string;
  findings: Finding[];
}) {
  const lines = parsePatch(patch);
  const fileFindings = findings.filter((f) => f.file === filename);
  const findingsByLine = new Map<number, Finding[]>();
  for (const f of fileFindings) {
    if (f.line > 0) {
      const existing = findingsByLine.get(f.line) || [];
      existing.push(f);
      findingsByLine.set(f.line, existing);
    }
  }

  if (!patch) {
    return (
      <div className="panel p-4 text-center text-sm text-fg-subtle">
        No diff available for this file.
      </div>
    );
  }

  return (
    <div className="overflow-hidden panel">
      {/* File header */}
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <svg
          className="h-4 w-4 text-fg-subtle"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        <span className="truncate mono text-sm text-fg-muted">{filename}</span>
        {fileFindings.length > 0 && (
          <span className="ml-auto pill tone-high">
            {fileFindings.length} finding{fileFindings.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Diff lines */}
      <div className="overflow-x-auto mono text-[13px] leading-5">
        {lines.map((line, idx) => (
          <div key={idx}>
            <div className={`flex hover:bg-surface-2 ${LINE_COLORS[line.type]}`}>
              <span className="w-12 shrink-0 border-r border-line px-2 text-right text-fg-subtle select-none">
                {line.lineNum || ""}
              </span>
              <span className="w-5 shrink-0 text-center text-fg-subtle select-none">
                {line.type === "add"
                  ? "+"
                  : line.type === "del"
                    ? "-"
                    : line.type === "header"
                      ? "@@"
                      : ""}
              </span>
              <span className="flex-1 overflow-hidden px-2 whitespace-pre">{line.content}</span>
              {/* Finding indicator dot */}
              {line.lineNum && findingsByLine.has(line.lineNum) && (
                <span className="flex shrink-0 items-center gap-1 px-2">
                  {findingsByLine.get(line.lineNum)!.map((f, fi) => (
                    <span
                      key={fi}
                      className={`h-2 w-2 rounded-full ${
                        SEVERITY_DOT[f.severity] || "bg-fg-subtle"
                      }`}
                      title={f.message}
                    />
                  ))}
                </span>
              )}
            </div>

            {/* Inline finding annotations */}
            {line.lineNum &&
              findingsByLine.has(line.lineNum) &&
              findingsByLine.get(line.lineNum)!.map((f, fi) => (
                <div key={fi} className="ml-12 flex border-l-2 border-warning/50 bg-warning/5">
                  <div className="px-4 py-2 text-xs">
                    <span
                      className={`mr-1.5 inline-block h-2 w-2 rounded-full ${
                        SEVERITY_DOT[f.severity] || "bg-fg-subtle"
                      }`}
                    />
                    <span className="font-medium text-warning">{f.agent}:</span>{" "}
                    <span className="text-fg-muted">{f.message}</span>
                    {f.suggestion && (
                      <p className="mt-0.5 ml-3.5 text-fg-subtle">Fix: {f.suggestion}</p>
                    )}
                  </div>
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}
