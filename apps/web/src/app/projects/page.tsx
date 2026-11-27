"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";
import ProjectCard from "@/components/ProjectCard";
import { ErrorNote, PageHeader, btn } from "@/components/ui";
import { api, type ProjectStatus, type ProjectSummary } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

const FILTERS: { value: "" | ProjectStatus; label: string }[] = [
  { value: "", label: "All" },
  { value: "ready", label: "Ready" },
  { value: "processing", label: "Processing" },
  { value: "uploading", label: "Uploading" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

const PAGE = 24;

export default function ProjectsPage() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState<"" | ProjectStatus>("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(q);
      setOffset(0);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (debounced) params.set("q", debounced);
  if (status) params.set("status", status);
  const { data, error, loading, refresh } = usePolling(
    () => api<{ items: ProjectSummary[]; total: number }>(`/projects?${params}`),
    {
      intervalMs: 3000,
      shouldPoll: (d) => d.items.some((p) => p.status === "processing" || p.status === "uploading"),
      deps: [debounced, status, offset],
    },
  );

  return (
    <>
      <PageHeader
        title="My Projects"
        subtitle={data ? `${data.total} project${data.total === 1 ? "" : "s"}` : undefined}
        actions={
          <Link href="/projects/new" className={btn.primary}>
            <Plus className="h-4 w-4" /> New project
          </Link>
        }
      />
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name or filename"
            className="w-full rounded-lg border border-line bg-surface py-2 pr-3 pl-9 text-sm placeholder:text-muted focus:border-accent/60 focus:outline-none"
          />
        </label>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => {
                setStatus(f.value);
                setOffset(0);
              }}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                status === f.value ? "border-accent/60 bg-accent-soft text-ink" : "border-line text-ink-2 hover:border-line-strong"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorNote error={error} onRetry={refresh} />}
      {loading && !data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton aspect-[4/3] rounded-xl" />
          ))}
        </div>
      )}
      {data && data.items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-line-strong px-6 py-14 text-center text-sm text-muted">
          {debounced || status ? "No projects match these filters." : "No projects yet."}
        </div>
      )}
      {data && data.items.length > 0 && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((p) => (
              <ProjectCard key={p.id} p={p} />
            ))}
          </div>
          {data.total > PAGE && (
            <div className="mt-8 flex items-center justify-center gap-3 text-sm">
              <button className={btn.secondary} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Previous
              </button>
              <span className="tabular text-muted">
                {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
              </span>
              <button className={btn.secondary} disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
