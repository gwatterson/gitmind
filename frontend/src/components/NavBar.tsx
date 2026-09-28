"use client";

import Image from "next/image";
import Link from "next/link";
import { API_URL } from "@/lib/api";
import { useAuth } from "./AuthProvider";

function UserMenu() {
  const { user, authDisabled, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="flex items-center gap-3">
      {authDisabled ? (
        <span className="badge badge-pending" title="AUTH_DISABLED=true on the backend">
          Auth disabled
        </span>
      ) : null}
      <span className="flex items-center gap-2 text-xs text-slate-300">
        {user.avatar_url ? (
          <Image
            src={user.avatar_url}
            alt=""
            width={24}
            height={24}
            className="h-6 w-6 rounded-full"
            unoptimized
          />
        ) : null}
        {user.login}
        {user.is_admin ? <span className="text-[10px] text-indigo-400">admin</span> : null}
      </span>
      {!authDisabled ? (
        <button
          onClick={logout}
          className="text-xs font-medium text-slate-500 transition-colors hover:text-slate-300"
        >
          Sign out
        </button>
      ) : null}
    </div>
  );
}

export function NavBar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-white/5 bg-[#0a0a0f]/80 backdrop-blur-xl">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          <Link href="/" className="group flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-linear-to-br from-indigo-500/20 to-violet-600/20 shadow-lg shadow-indigo-500/10 transition-all duration-300 group-hover:shadow-indigo-500/20">
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
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-xs font-medium text-slate-400 transition-colors hover:text-slate-200"
            >
              Dashboard
            </Link>
            <a
              href={`${API_URL}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-slate-500 transition-colors hover:text-slate-300"
            >
              API Docs ↗
            </a>
            <UserMenu />
          </div>
        </div>
      </div>
    </nav>
  );
}
