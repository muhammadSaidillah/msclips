"use client";

import Link from "next/link";
import { Activity, Clock, FolderOpen, HardDrive, Plus, UploadCloud } from "lucide-react";
import ProjectCard from "@/components/ProjectCard";
import { Card, ErrorNote, PageHeader, btn } from "@/components/ui";
import { api, type Dashboard } from "@/lib/api";
import { formatBytes, formatHoursTotal } from "@/lib/format";
import { usePolling } from "@/lib/usePolling";

function Stat({ icon: Icon, label, value, hint }: { icon: typeof Clock; label: string; value: string; hint?: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs text-muted">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="tabular mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export default function DashboardPage() {
  const { data, error, loading, refresh } = usePolling(() => api<Dashboard>("/dashboard"), {
    intervalMs: 3000,
    shouldPoll: (d) => d.active_jobs > 0 || d.project_counts.uploading > 0,
  });

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Your projects and processing activity"
        actions={
          <Link href="/projects/new" className={btn.primary}>
            <Plus className="h-4 w-4" /> New project
          </Link>
        }
      />
      {error && !data && <ErrorNote error={error} onRetry={refresh} />}
      {loading && !data && !error && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-24 rounded-xl" />
          ))}
        </div>
      )}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat icon={FolderOpen} label="Projects" value={String(data.total_projects)} hint={`${data.project_counts.ready} ready`} />
            <Stat icon={Clock} label="Source footage" value={formatHoursTotal(data.total_source_duration_s)} hint="across ready projects" />
            <Stat icon={HardDrive} label="Storage used" value={formatBytes(data.total_source_bytes)} hint="source videos" />
            <Stat
              icon={Activity}
              label="Active jobs"
              value={String(data.active_jobs)}
              hint={data.project_counts.failed ? `${data.project_counts.failed} project(s) need attention` : "queued or running"}
            />
          </div>

          <div className="mt-10 mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-wide text-ink-2 uppercase">Recent projects</h2>
            {data.total_projects > 0 && (
              <Link href="/projects" className="text-sm text-muted hover:text-ink">
                View all
              </Link>
            )}
          </div>
          {data.recent_projects.length === 0 ? (
            <Link
              href="/projects/new"
              className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-line-strong bg-surface/50 px-6 py-16 text-center transition hover:border-accent/50"
            >
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent-soft">
                <UploadCloud className="h-5 w-5 text-accent" />
              </span>
              <div className="text-base font-medium">Upload your first long video</div>
              <div className="max-w-sm text-sm text-muted">
                Podcasts, interviews, webinars. Use footage you own or have permission to repurpose.
              </div>
            </Link>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.recent_projects.map((p) => (
                <ProjectCard key={p.id} p={p} />
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
