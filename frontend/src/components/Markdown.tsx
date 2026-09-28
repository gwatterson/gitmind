"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Raw HTML in the source is not rendered (react-markdown default), so LLM output
// cannot inject markup into the page.
const components: Components = {
  h1: ({ children }) => (
    <h3 className="mt-4 mb-2 text-base font-semibold text-slate-100">{children}</h3>
  ),
  h2: ({ children }) => (
    <h3 className="mt-4 mb-2 text-base font-semibold text-slate-100">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="mt-4 mb-1.5 text-sm font-semibold text-slate-100 first:mt-0">{children}</h4>
  ),
  p: ({ children }) => <p className="mb-2 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 ml-5 list-disc space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 ml-5 list-decimal space-y-1">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold text-slate-100">{children}</strong>,
  code: ({ children }) => (
    <code className="rounded bg-slate-800/60 px-1 py-0.5 mono text-[12px] text-indigo-300">
      {children}
    </code>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-indigo-400 hover:underline"
    >
      {children}
    </a>
  ),
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm text-slate-300">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
