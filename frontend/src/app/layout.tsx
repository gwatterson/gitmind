import type { Metadata } from "next";
import Image from "next/image";
import "./globals.css";

export const metadata: Metadata = {
  title: "GitMind: Autonomous Code Review Agent",
  description:
    "AI-powered code review agent that analyzes GitHub PRs for security, quality, and performance issues in real-time.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <nav className="sticky top-0 z-50 border-b border-white/5 bg-[#0a0a0f]/80 backdrop-blur-xl">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="flex h-14 items-center justify-between">
              <a href="/" className="group flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br from-indigo-500/20 to-violet-600/20 shadow-lg shadow-indigo-500/10 transition-all duration-300 group-hover:shadow-indigo-500/20">
                  <Image
                    src="/logo.svg"
                    alt="GitMind Logo"
                    width={28}
                    height={28}
                    className="h-7 w-7"
                  />
                </div>
                <span className="text-lg font-bold tracking-tight text-slate-100">
                  Git<span className="text-indigo-400">Mind</span>
                </span>
              </a>
              <div className="flex items-center gap-4">
                <a
                  href="/"
                  className="text-xs font-medium text-slate-400 transition-colors hover:text-slate-200"
                >
                  Dashboard
                </a>
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/docs`}
                  target="_blank"
                  className="text-xs font-medium text-slate-500 transition-colors hover:text-slate-300"
                >
                  API Docs ↗
                </a>
              </div>
            </div>
          </div>
        </nav>
        <main className="relative z-10 mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </body>
    </html>
  );
}
