/**
 * API client for the GitMind backend.
 *
 * Every request sends the session cookie and the CSRF header required by the
 * backend for state-changing calls. A 401 response broadcasts an event so the
 * UI can switch to the sign-in screen.
 */

import type {
  AuthMe,
  DiffFile,
  Finding,
  RateLimitStatus,
  ReviewDetail,
  ReviewStats,
  ReviewsResponse,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const UNAUTHORIZED_EVENT = "gitmind:unauthorized";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "gitmind",
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (res.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // Non-JSON error body: keep the status text
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Human-readable message for any error thrown by this client. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Network error";
}

// ── Auth ──

export function getAuthStatus(): Promise<{ oauth_configured: boolean; auth_disabled: boolean }> {
  return request("/auth/status");
}

export function getMe(): Promise<AuthMe> {
  return request("/auth/me");
}

export function logout(): Promise<void> {
  return request("/auth/logout", { method: "POST" });
}

export function loginUrl(next: string = "/"): string {
  return `${API_URL}/auth/login?next=${encodeURIComponent(next)}`;
}

// ── Reviews ──

export function getReviews(
  params: { limit?: number; offset?: number; status?: string } = {},
): Promise<ReviewsResponse> {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  if (params.status) query.set("status", params.status);
  const qs = query.toString();
  return request(`/api/reviews${qs ? `?${qs}` : ""}`);
}

export function getReviewDetail(id: string): Promise<ReviewDetail> {
  return request(`/api/reviews/${encodeURIComponent(id)}`);
}

export function getReviewDiff(id: string): Promise<{ files: DiffFile[] }> {
  return request(`/api/reviews/${encodeURIComponent(id)}/diff`);
}

export function triggerManualReview(
  repo: string,
  prNumber: number,
): Promise<{ review_id: string; status: string }> {
  return request("/api/reviews/trigger", { method: "POST", body: { repo, pr_number: prNumber } });
}

export function approveReview(id: string): Promise<{ github_posted: boolean; warning?: string }> {
  return request(`/api/reviews/${encodeURIComponent(id)}/approve`, { method: "POST" });
}

export function deleteReview(id: string): Promise<void> {
  return request(`/api/reviews/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function clearArchive(): Promise<void> {
  return request("/api/reviews", { method: "DELETE" });
}

export function updateFinding(
  reviewId: string,
  findingId: string,
  data: { message?: string; suggestion?: string; severity?: string },
): Promise<{ finding: Finding }> {
  return request(
    `/api/reviews/${encodeURIComponent(reviewId)}/findings/${encodeURIComponent(findingId)}`,
    {
      method: "PATCH",
      body: data,
    },
  );
}

// ── Stats & Monitoring ──

export function getStats(): Promise<ReviewStats> {
  return request("/api/stats");
}

export function getRateLimitStatus(): Promise<RateLimitStatus> {
  return request("/api/rate-limit/status");
}

// ── SSE Stream ──

export function createReviewStream(reviewId: string): EventSource {
  return new EventSource(`${API_URL}/api/stream/${encodeURIComponent(reviewId)}`, {
    withCredentials: true,
  });
}

// ── Dates ──

/**
 * Parse a backend timestamp. The API returns UTC times as "YYYY-MM-DD HH:MM:SS"
 * without a zone, which browsers would otherwise read as local time.
 */
export function parseServerDate(value: string): Date {
  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  return new Date(hasZone ? value : `${value.replace(" ", "T")}Z`);
}
