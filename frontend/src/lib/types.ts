/**
 * TypeScript types matching backend models.
 */

export interface Review {
    id: string;
    repo: string;
    pr_number: number;
    pr_title: string;
    pr_author: string;
    commit_id: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'hitl_pending';
    verdict: 'approve' | 'comment' | 'request_changes' | null;
    summary: string | null;
    created_at: string;
    completed_at: string | null;
    error: string | null;
}

export interface Finding {
    id: string;
    review_id: string;
    file: string;
    line: number;
    severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
    category: 'security' | 'quality' | 'performance';
    rule_id: string;
    message: string;
    suggestion: string;
    agent: string;
    posted_to_github: boolean;
    github_comment_id: string | null;
    created_at: string;
}

export interface StreamEvent {
    type: string;
    message: string;
    timestamp: string;
    data?: Record<string, unknown>;
}

export interface RateLimitStatus {
    rpm_used: number;
    rpm_max: number;
    rpd_used: number;
    rpd_max: number;
    tpm_used: number;
    tpm_max: number;
    rpd_resets_at: number;
}

export interface ReviewDetail {
    review: Review;
    findings: Finding[];
    events: StreamEvent[];
}

export interface ReviewStats {
    total_reviews: number;
    total_findings: number;
    reviews_by_status: Record<string, number>;
    findings_by_category: Record<string, number>;
    findings_by_severity: Record<string, number>;
}

export interface ReviewsResponse {
    reviews: Review[];
    count: number;
}
