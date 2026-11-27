import type { ProjectStatus, JobStatus } from "@/lib/api";
import { AlertTriangle, Loader2 } from "lucide-react";

const STATUS_STYLE: Record<string, { dot: string; text: string; label: string }> = {
  uploading: { dot: "bg-warn", text: "text-warn", label: "Uploading" },
  processing: { dot: "bg-info animate-pulse", text: "text-info", label: "Processing" },
  ready: { dot: "bg-ok", text: "text-ok", label: "Ready" },
  failed: { dot: "bg-bad", text: "text-bad", label: "Failed" },
  cancelled: { dot: "bg-muted", text: "text-muted", label: "Cancelled" },
  queued: { dot: "bg-muted animate-pulse", text: "text-ink-2", label: "Queued" },
  running: { dot: "bg-info animate-pulse", text: "text-info", label: "Running" },
  succeeded: { dot: "bg-ok", text: "text-ok", label: "Succeeded" },
};

export function StatusBadge({ status }: { status: ProjectStatus | JobStatus }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.cancelled;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2/80 px-2 py-0.5 text-xs font-medium ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

export function ProgressBar({ value, tone = "accent" }: { value: number; tone?: "accent" | "info" | "ok" }) {
  const color = tone === "info" ? "bg-info" : tone === "ok" ? "bg-ok" : "bg-accent";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
      <div className={`h-full rounded-full ${color} transition-[width] duration-300`} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={`rounded-xl border border-line bg-surface ${className}`}>{children}</div>;
}

export function ErrorNote({ error, onRetry }: { error: Error | string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-bad/30 bg-bad/10 p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
      <div className="flex-1 text-ink-2">{typeof error === "string" ? error : error.message}</div>
      {onRetry && (
        <button onClick={onRetry} className="text-xs font-medium text-ink underline-offset-2 hover:underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} />;
}

export const btn = {
  primary:
    "inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#160a04] transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50",
  secondary:
    "inline-flex items-center justify-center gap-2 rounded-lg border border-line-strong bg-surface-2 px-4 py-2 text-sm font-medium text-ink transition hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-50",
  ghost:
    "inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-ink-2 transition hover:bg-surface-2 hover:text-ink disabled:opacity-50",
  danger:
    "inline-flex items-center justify-center gap-2 rounded-lg border border-bad/40 px-4 py-2 text-sm font-medium text-bad transition hover:bg-bad/10 disabled:opacity-50",
};
