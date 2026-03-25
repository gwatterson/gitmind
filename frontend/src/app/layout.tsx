import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GitMind — Autonomous Code Review Agent",
  description:
    "AI-powered code review agent that analyzes GitHub PRs for security, quality, and performance issues in real-time.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <nav className="sticky top-0 z-50 border-b border-white/5 backdrop-blur-xl bg-[#0a0a0f]/80">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-14">
              <a href="/" className="flex items-center gap-3 group">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-indigo-500/20 to-violet-600/20 border border-white/10 shadow-lg shadow-indigo-500/10 group-hover:shadow-indigo-500/20 transition-all duration-300">
                  <img src="/logo.svg" alt="GitMind Logo" className="w-7 h-7" />
                </div>
                <span className="text-lg font-bold text-slate-100 tracking-tight">
                  Git<span className="text-indigo-400">Mind</span>
                </span>
              </a>
              <div className="flex items-center gap-4">
                <a
                  href="/"
                  className="text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Dashboard
                </a>
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/docs`}
                  target="_blank"
                  className="text-xs font-medium text-slate-500 hover:text-slate-300 transition-colors"
                >
                  API Docs ↗
                </a>
              </div>
            </div>
          </div>
        </nav>
        <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
