import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  CircleX,
  Clock,
  Gauge,
  LoaderCircle,
  MessageSquare,
  Pause,
  ShieldAlert,
  UserCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { Review } from "@/lib/types";

export const SEVERITIES = ["critical", "high", "medium", "low", "info"] as const;

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
};

export function SeverityPill({ severity }: { severity: string }) {
  return (
    <span className={`pill tone-${SEVERITY_LABEL[severity] ? severity : "neutral"}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {SEVERITY_LABEL[severity] ?? severity}
    </span>
  );
}

export const CATEGORY_ICON: Record<string, LucideIcon> = {
  security: ShieldAlert,
  quality: Wrench,
  performance: Gauge,
};

export function CategoryLabel({ category }: { category: string }) {
  const Icon = CATEGORY_ICON[category] ?? CircleAlert;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-fg-muted capitalize">
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {category}
    </span>
  );
}

type StatusStyle = { label: string; icon: LucideIcon; className: string; spin?: boolean };

export const STATUS: Record<Review["status"], StatusStyle> = {
  pending: { label: "Queued", icon: Clock, className: "text-fg-subtle" },
  running: { label: "Running", icon: LoaderCircle, className: "text-accent", spin: true },
  completed: { label: "Completed", icon: CircleCheck, className: "text-fg-muted" },
  failed: { label: "Failed", icon: CircleX, className: "text-danger" },
  hitl_pending: { label: "Needs approval", icon: UserCheck, className: "text-warning" },
  superseded: { label: "Superseded", icon: CircleSlash, className: "text-fg-subtle" },
  quota_exhausted: { label: "Quota exhausted", icon: Pause, className: "text-warning" },
};

export function StatusLabel({ status }: { status: Review["status"] }) {
  const style = STATUS[status] ?? STATUS.pending;
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${style.className}`}>
      <Icon className={`h-3.5 w-3.5 ${style.spin ? "animate-spin" : ""}`} aria-hidden />
      {style.label}
    </span>
  );
}

type VerdictStyle = { label: string; short: string; icon: LucideIcon; tone: string };

export const VERDICT: Record<string, VerdictStyle> = {
  request_changes: {
    label: "Changes requested",
    short: "Changes",
    icon: CircleX,
    tone: "tone-critical",
  },
  comment: { label: "Comments only", short: "Comments", icon: MessageSquare, tone: "tone-info" },
  approve: { label: "No blocking issues", short: "Clean", icon: CircleCheck, tone: "tone-low" },
};

export function VerdictPill({ verdict }: { verdict: string | null }) {
  if (!verdict || !VERDICT[verdict]) {
    return (
      <span className="pill tone-neutral">
        <CircleDashed className="h-3.5 w-3.5" aria-hidden />
        No verdict
      </span>
    );
  }
  const style = VERDICT[verdict];
  const Icon = style.icon;
  return (
    <span className={`pill ${style.tone}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {style.short}
    </span>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  hint,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center panel px-6 py-10 text-center">
      <Icon className="mb-3 h-5 w-5 text-fg-subtle" aria-hidden />
      <p className="text-sm text-fg">{title}</p>
      {hint ? <p className="mt-1 text-xs text-fg-subtle">{hint}</p> : null}
    </div>
  );
}
