import Link from "next/link";
import { Lock } from "lucide-react";
import { PageHeader, btn } from "./ui";

/**
 * Honest placeholder for sections that are not built yet. It never shows sample data or
 * controls that look functional.
 */
export default function MilestonePanel({
  title,
  milestone,
  summary,
  planned,
}: {
  title: string;
  milestone: number;
  summary: string;
  planned: string[];
}) {
  return (
    <>
      <PageHeader title={title} />
      <div className="rounded-2xl border border-dashed border-line-strong bg-surface/60 p-8 sm:p-10">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-surface-3">
            <Lock className="h-4.5 w-4.5 text-muted" />
          </span>
          <div>
            <div className="font-mono text-xs tracking-wider text-accent uppercase">Not built yet · Milestone {milestone}</div>
            <div className="mt-0.5 text-lg font-semibold">{summary}</div>
          </div>
        </div>
        <p className="mt-5 max-w-2xl text-sm leading-relaxed text-ink-2">
          This section is intentionally empty. CLIPFORGE AI ships features milestone by milestone, and nothing here is
          simulated. What this section will do:
        </p>
        <ul className="mt-4 grid max-w-3xl gap-2 text-sm text-ink-2 sm:grid-cols-2">
          {planned.map((p) => (
            <li key={p} className="flex gap-2">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted" />
              {p}
            </li>
          ))}
        </ul>
        <Link href="/projects/new" className={`${btn.secondary} mt-7`}>
          Upload a video to prepare
        </Link>
      </div>
    </>
  );
}
