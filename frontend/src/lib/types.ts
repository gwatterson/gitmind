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
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "hitl_pending"
    | "superseded"
    | "quota_exhausted";
  verdict: "approve" | "comment" | "request_changes" | null;
  summary: string | null;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  llm_provider: string | null;
  llm_model: string | null;
}

export interface Finding {
  id: string;
  review_id: string;
  file: string;
  line: number;
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: "security" | "quality" | "performance";
  rule_id: string;
  message: string;
  suggestion: string;
  agent: string;
  confidence: number | null;
  cwe: string | null;
  evidence: string | null;
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

export interface DiffFile {
  filename: string;
  patch: string;
}

export interface ReviewsResponse {
  reviews: Review[];
  count: number;
}

export interface User {
  kind: "user" | "api_key" | "dev";
  login: string;
  name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  scopes: string[];
}

export interface AuthMe {
  user: User;
  auth_disabled: boolean;
}

export interface LlmProviderOption {
  id: "gemini" | "ollama";
  label: string;
  model: string;
  available: boolean;
  reason: string | null;
}

export interface LlmSettings {
  provider: "gemini" | "ollama";
  model: string;
  rate_limited: boolean;
  providers: LlmProviderOption[];
}
