"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useAuth } from "./AuthProvider";
import { useLlmSettings } from "./LlmSettingsProvider";
import { QuotaButton } from "./QuotaButton";

function ActiveModel() {
  const { settings } = useLlmSettings();
  if (!settings) return null;
  return (
    <span
      className="hidden items-center gap-2 text-xs text-fg-subtle md:inline-flex"
      title="Model used for new reviews"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-success" aria-hidden />
      <span className="mono text-fg-muted">{settings.model}</span>
    </span>
  );
}

function UserMenu() {
  const { user, authDisabled, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="flex items-center gap-3 border-l border-line pl-4">
      {authDisabled ? (
        <span className="pill tone-medium" title="AUTH_DISABLED=true on the backend">
          Auth off
        </span>
      ) : null}
      <span className="flex items-center gap-2 text-sm text-fg-muted">
        {user.avatar_url ? (
          <Image
            src={user.avatar_url}
            alt=""
            width={22}
            height={22}
            className="h-[22px] w-[22px] rounded-full"
            unoptimized
          />
        ) : null}
        {user.login}
        {user.is_admin ? <span className="text-xs text-fg-subtle">admin</span> : null}
      </span>
      {!authDisabled ? (
        <button onClick={logout} className="text-sm text-fg-subtle hover:text-fg">
          Sign out
        </button>
      ) : null}
    </div>
  );
}

export function NavBar() {
  return (
    <header className="sticky top-0 z-50 border-b border-line bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2.5">
            <Image src="/logo.svg" alt="" width={22} height={22} className="h-[22px] w-[22px]" />
            <span className="text-[15px] font-semibold tracking-tight text-fg">GitMind</span>
          </Link>
          <nav className="flex items-center gap-5 text-sm">
            <Link href="/" className="text-fg-muted hover:text-fg">
              Reviews
            </Link>
            <a
              href={`${API_URL}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-fg-subtle hover:text-fg"
            >
              API
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
            </a>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <ActiveModel />
          <QuotaButton />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
