/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { Film } from "lucide-react";
import { thumbnailUrl, type ProjectSummary } from "@/lib/api";
import { formatBytes, formatDuration, formatRelative } from "@/lib/format";
import { StatusBadge } from "./ui";

export default function ProjectCard({ p }: { p: ProjectSummary }) {
  return (
    <Link
      href={`/projects/${p.id}`}
      className="group overflow-hidden rounded-xl border border-line bg-surface transition hover:border-line-strong hover:bg-surface-2"
    >
      <div className="relative aspect-video bg-surface-2">
        {p.has_thumbnail ? (
          <img src={thumbnailUrl(p)} alt="" className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="grid h-full place-items-center text-muted">
            <Film className="h-7 w-7" />
          </div>
        )}
        {p.duration_s != null && (
          <span className="tabular absolute right-2 bottom-2 rounded bg-black/75 px-1.5 py-0.5 font-mono text-[11px]">
            {formatDuration(p.duration_s)}
          </span>
        )}
        <span className="absolute top-2 left-2">
          <StatusBadge status={p.status} />
        </span>
      </div>
      <div className="space-y-1 p-3.5">
        <div className="truncate text-sm font-medium">{p.name}</div>
        <div className="flex items-center gap-2 text-xs text-muted">
          <span>{formatRelative(p.created_at)}</span>
          {p.source_size_bytes != null && <span>· {formatBytes(p.source_size_bytes)}</span>}
          {p.width && p.height && (
            <span className="tabular">
              · {p.width}×{p.height}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
