/**
 * API client for the GitMind backend.
 */

import type {
    ReviewsResponse,
    ReviewDetail,
    RateLimitStatus,
    ReviewStats,
} from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${API_URL}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!res.ok) {
        const error = await res.text();
        throw new Error(`API error ${res.status}: ${error}`);
    }
    return res.json();
}

// ── Reviews ──

export async function getReviews(params?: {
    limit?: number;
    offset?: number;
    status?: string;
}): Promise<ReviewsResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    if (params?.status) query.set('status', params.status);
    const qs = query.toString();
    return fetchJSON(`/api/reviews${qs ? `?${qs}` : ''}`);
}

export async function getReviewDetail(id: string): Promise<ReviewDetail> {
    return fetchJSON(`/api/reviews/${id}`);
}

export async function triggerManualReview(repo: string, pr_number: number) {
    return fetchJSON('/api/reviews/trigger', {
        method: 'POST',
        body: JSON.stringify({ repo, pr_number }),
    });
}

export async function approveReview(id: string) {
    return fetchJSON(`/api/reviews/${id}/approve`, { method: 'POST' });
}

export async function updateFinding(
    reviewId: string,
    findingId: string,
    data: { message?: string; suggestion?: string; severity?: string },
) {
    return fetchJSON(`/api/reviews/${reviewId}/findings/${findingId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
    });
}

// ── Stats & Monitoring ──

export async function getStats(): Promise<ReviewStats> {
    return fetchJSON('/api/stats');
}

export async function getRateLimitStatus(): Promise<RateLimitStatus> {
    return fetchJSON('/api/rate-limit/status');
}

export async function getHealth() {
    return fetchJSON('/api/health');
}

// ── SSE Stream ──

export function createReviewStream(reviewId: string): EventSource {
    return new EventSource(`${API_URL}/api/stream/${reviewId}`);
}
