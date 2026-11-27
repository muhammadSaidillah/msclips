"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { API_URL, ApiError, type Health } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const LABELS: Record<string, string> = {
  database: "PostgreSQL database",
  queue: "Job queue (Redis)",
  storage: "Object storage",
  ffmpeg: "FFmpeg / ffprobe",
};

async function fetchHealth(): Promise<Health> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/health`, { cache: "no-store" });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}.`);
  }
  return res.json(); // 503 still carries the per-check breakdown
}

export default function SettingsPage() {
  const { data, error, loading } = usePolling(fetchHealth, { intervalMs: 10000 });
  return (
    <>
      <PageHeader title="Settings" subtitle="System status and configuration" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-sm font-semibold">System health</h2>
          <p className="mt-1 text-xs text-muted">Live checks from the backend, refreshed every 10 seconds.</p>
          <div className="mt-4 space-y-2">
            {loading && !data && <Spinner />}
            {error && !data && <ErrorNote error={error} />}
            {data &&
              Object.entries(data.checks).map(([k, c]) => (
                <div key={k} className="flex items-start gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2.5">
                  {c.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-ok" /> : <XCircle className="mt-0.5 h-4 w-4 text-bad" />}
                  <div className="min-w-0 flex-1">
                    <div className="text-sm">
                      {LABELS[k] ?? k}
                      {c.backend && <span className="ml-2 font-mono text-xs text-muted">{c.backend}</span>}
                    </div>
                    {c.error && <div className="mt-0.5 truncate text-xs text-bad">{c.error}</div>}
                  </div>
                </div>
              ))}
          </div>
        </Card>
        <Card className="p-5">
          <h2 className="text-sm font-semibold">Account</h2>
          <p className="mt-2 text-sm text-ink-2">
            This build runs in single-user local mode. Secure OAuth sign-in is added before any multi-user or public deployment.
          </p>
          <h2 className="mt-6 text-sm font-semibold">API endpoint</h2>
          <p className="mt-2 font-mono text-xs break-all text-ink-2">{API_URL}</p>
        </Card>
      </div>
    </>
  );
}
