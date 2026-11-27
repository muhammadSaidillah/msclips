"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  ArrowLeft,
  AudioLines,
  Check,
  Clock,
  Film,
  Gauge,
  Pencil,
  Ratio,
  RotateCcw,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { Card, ErrorNote, ProgressBar, Spinner, StatusBadge, btn } from "@/components/ui";
import { api, sourceUrl, thumbnailUrl, type Job, type ProjectDetail } from "@/lib/api";
import { formatBitrate, formatBytes, formatChannels, formatContainer, formatDuration, formatRelative } from "@/lib/format";
import { ChunkedUploader, type UploadState } from "@/lib/upload";
import { usePolling } from "@/lib/usePolling";

function Meta({ label, value, mono = true }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`mt-0.5 truncate text-sm text-ink ${mono ? "tabular font-mono" : ""}`}>{value ?? "—"}</dd>
    </div>
  );
}

function Highlight({ icon: Icon, label, value, sub }: { icon: typeof Clock; label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-3.5">
      <div className="flex items-center gap-1.5 text-xs text-muted">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className="tabular mt-1.5 text-lg font-semibold">{value}</div>
      {sub && <div className="text-xs text-muted capitalize">{sub}</div>}
    </div>
  );
}

function JobRow({ job, onCancel }: { job: Job; onCancel: (id: string) => void }) {
  const active = job.status === "queued" || job.status === "running";
  return (
    <div className="space-y-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-medium">Metadata extraction</div>
          <div className="text-xs text-muted">
            {job.stage ?? "waiting for a worker"} · attempt {Math.max(job.attempts, 1)}/{job.max_attempts} · {formatRelative(job.created_at)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={job.status} />
          {job.status === "queued" && (
            <button className="text-xs text-muted hover:text-ink" onClick={() => onCancel(job.id)}>
              Cancel
            </button>
          )}
        </div>
      </div>
      {active && <ProgressBar value={job.progress} tone="info" />}
      {job.error && <div className="text-xs text-bad">{job.error}</div>}
    </div>
  );
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [resume, setResume] = useState<UploadState | null>(null);
  const resumer = useRef<ChunkedUploader | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: p, error, loading, refresh, setData } = usePolling(() => api<ProjectDetail>(`/projects/${id}`), {
    intervalMs: 1200,
    shouldPoll: (d) => d.status === "processing" || d.jobs.some((j) => j.status === "queued" || j.status === "running"),
    deps: [id],
  });

  const act = async (fn: () => Promise<unknown>) => {
    setWorking(true);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setWorking(false);
    }
  };

  if (loading && !p) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-8 w-64 rounded-lg" />
        <div className="skeleton aspect-video w-full max-w-3xl rounded-xl" />
      </div>
    );
  }
  if (error && !p) {
    return (
      <div className="space-y-4">
        <Link href="/projects" className={btn.ghost}>
          <ArrowLeft className="h-4 w-4" /> My Projects
        </Link>
        <ErrorNote error={error} onRetry={refresh} />
      </div>
    );
  }
  if (!p) return null;
  const m = p.metadata;
  const activeJob = p.jobs.find((j) => j.status === "queued" || j.status === "running");
  const canReprocess = (p.status === "failed" || p.status === "ready") && !activeJob && (p.source || p.upload?.status === "completed");

  return (
    <>
      <Link href="/projects" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> My Projects
      </Link>

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="w-full min-w-0 sm:flex-1">
          {editing ? (
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                act(async () => {
                  const d = await api<ProjectDetail>(`/projects/${p.id}`, { method: "PATCH", body: JSON.stringify({ name: draft }) });
                  setData(d);
                  setEditing(false);
                });
              }}
            >
              <input
                autoFocus
                value={draft}
                maxLength={200}
                onChange={(e) => setDraft(e.target.value)}
                className="w-full max-w-md rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-xl font-semibold focus:border-accent/60 focus:outline-none"
              />
              <button aria-label="Save name" className={btn.ghost} disabled={!draft.trim() || working}>
                <Check className="h-4 w-4" />
              </button>
              <button type="button" aria-label="Cancel rename" className={btn.ghost} onClick={() => setEditing(false)}>
                <X className="h-4 w-4" />
              </button>
            </form>
          ) : (
            <div className="flex items-center gap-2">
              <h1 className="truncate text-2xl font-semibold tracking-tight">{p.name}</h1>
              <button
                aria-label="Rename project"
                className="rounded p-1 text-muted hover:text-ink"
                onClick={() => {
                  setDraft(p.name);
                  setEditing(true);
                }}
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
            <StatusBadge status={p.status} />
            <span>Created {formatRelative(p.created_at)}</span>
            {p.source_filename && <span className="truncate">· {p.source_filename}</span>}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {canReprocess && (
            <button
              className={btn.secondary}
              disabled={working}
              onClick={() => act(async () => (await api(`/projects/${p.id}/reprocess`, { method: "POST" }), refresh()))}
            >
              <RotateCcw className="h-4 w-4" /> {p.status === "failed" ? "Retry processing" : "Re-extract metadata"}
            </button>
          )}
          <button className={btn.danger} onClick={() => setConfirmDelete(true)} disabled={working}>
            <Trash2 className="h-4 w-4" /> Delete
          </button>
        </div>
      </div>

      {confirmDelete && (
        <Card className="mb-6 flex flex-wrap items-center justify-between gap-3 border-bad/40 p-4">
          <span className="text-sm text-ink-2">
            Delete this project and its stored video{p.source ? ` (${formatBytes(p.source.size_bytes)})` : ""}? This cannot be undone.
          </span>
          <div className="flex gap-2">
            <button className={btn.secondary} onClick={() => setConfirmDelete(false)}>
              Keep
            </button>
            <button
              className={btn.danger}
              disabled={working}
              onClick={() =>
                act(async () => {
                  await api(`/projects/${p.id}`, { method: "DELETE" });
                  router.push("/projects");
                })
              }
            >
              {working ? <Spinner /> : <Trash2 className="h-4 w-4" />} Delete permanently
            </button>
          </div>
        </Card>
      )}

      {actionError && (
        <div className="mb-6">
          <ErrorNote error={actionError} />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <div className="overflow-hidden rounded-xl border border-line bg-black">
            {p.status === "ready" && p.source ? (
              <video
                key={p.source.id}
                controls
                preload="metadata"
                poster={p.has_thumbnail ? thumbnailUrl(p) : undefined}
                src={sourceUrl(p.id)}
                className="aspect-video w-full bg-black object-contain"
              />
            ) : (
              <div className="grid aspect-video place-items-center bg-surface-2 text-muted">
                <div className="flex flex-col items-center gap-2 text-sm">
                  {p.status === "processing" ? <Spinner className="h-6 w-6 text-info" /> : <Film className="h-7 w-7" />}
                  {p.status === "processing" && "Processing… the preview appears once the server confirms the video."}
                  {p.status === "uploading" && "Upload not finished."}
                  {p.status === "failed" && "No playable video."}
                  {p.status === "cancelled" && "Upload was cancelled."}
                </div>
              </div>
            )}
          </div>

          {p.status === "failed" && p.status_message && <ErrorNote error={p.status_message} />}

          {p.status === "uploading" && p.upload?.status === "active" && (
            <Card className="p-5">
              <div className="flex items-center gap-2 text-sm font-medium">
                <UploadCloud className="h-4 w-4 text-warn" /> Upload incomplete
              </div>
              <p className="mt-1.5 text-sm text-ink-2">
                The server has {formatBytes(resume?.bytesSent ?? p.upload.received_bytes)} of {formatBytes(p.upload.size_bytes)}. Select{" "}
                <span className="font-mono text-ink">{p.upload.filename}</span> again to continue from there.
              </p>
              <div className="mt-4 space-y-3">
                <ProgressBar value={(resume?.bytesSent ?? p.upload.received_bytes) / p.upload.size_bytes} />
                {resume?.error && <ErrorNote error={resume.error} />}
                <div className="flex gap-2">
                  {(!resume || resume.phase === "failed") && (
                    <button className={btn.primary} onClick={() => fileRef.current?.click()}>
                      <RotateCcw className="h-4 w-4" /> Resume upload
                    </button>
                  )}
                  {resume && ["uploading", "finalizing"].includes(resume.phase) && (
                    <span className="flex items-center gap-2 text-sm text-ink-2">
                      <Spinner /> {resume.phase === "uploading" ? "Uploading…" : "Verifying…"}
                    </span>
                  )}
                  <button
                    className={btn.secondary}
                    onClick={() =>
                      act(async () => {
                        resumer.current?.cancel();
                        await api(`/uploads/${p.upload!.id}`, { method: "DELETE" }).catch(() => {});
                        await refresh();
                      })
                    }
                  >
                    Cancel upload
                  </button>
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (!f || !p.upload) return;
                    const u = new ChunkedUploader(f, p.name, (s) => {
                      setResume(s);
                      if (s.phase === "done") refresh();
                    });
                    resumer.current = u;
                    u.resumeExisting(p.upload);
                  }}
                />
              </div>
            </Card>
          )}

          {m && (
            <Card className="p-5">
              <h2 className="text-sm font-semibold">Video summary</h2>
              <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                <Highlight icon={Clock} label="Duration" value={formatDuration(m.duration_s)} />
                <Highlight icon={Film} label="Resolution" value={`${m.display_width}×${m.display_height}`} />
                <Highlight icon={Ratio} label="Aspect ratio" value={m.aspect_ratio} sub={m.orientation} />
                <Highlight icon={Gauge} label="Frame rate" value={m.fps ? `${m.fps} fps` : "—"} />
              </div>
              <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
                <Meta label="Video codec" value={m.video_codec} />
                <Meta label="Pixel format" value={m.pixel_format} />
                <Meta label="Bitrate" value={formatBitrate(m.bit_rate)} />
                <Meta label="Container" value={formatContainer(m.container, p.source?.filename)} />
                <Meta label="Coded size" value={`${m.width}×${m.height}`} />
                <Meta label="Rotation" value={`${m.rotation}°`} />
                <Meta label="File size" value={formatBytes(p.source?.size_bytes)} />
                <Meta label="Storage" value={p.source?.storage_backend} />
              </dl>
              <div className="mt-6 rounded-xl border border-line bg-surface-2 p-4">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <AudioLines className={`h-4 w-4 ${m.has_audio ? "text-ok" : "text-warn"}`} />
                  {m.has_audio ? `Audio detected (${m.audio_track_count} track${m.audio_track_count > 1 ? "s" : ""})` : "No audio track"}
                </div>
                {m.has_audio ? (
                  <dl className="mt-3 grid grid-cols-3 gap-4">
                    <Meta label="Codec" value={m.audio_codec} />
                    <Meta label="Channels" value={formatChannels(m.audio_channels)} />
                    <Meta label="Sample rate" value={m.audio_sample_rate ? `${(m.audio_sample_rate / 1000).toFixed(1)} kHz` : "—"} />
                  </dl>
                ) : (
                  <p className="mt-1.5 text-xs text-muted">Transcription and clip discovery need speech; this video has no audio stream.</p>
                )}
              </div>
            </Card>
          )}
        </div>

        <aside className="space-y-4">
          <Card className="p-5">
            <h3 className="mb-3 text-sm font-semibold">Processing</h3>
            {p.jobs.length === 0 ? (
              <p className="text-sm text-muted">No jobs yet. Processing starts when the upload completes.</p>
            ) : (
              <div className="divide-y divide-line">
                {p.jobs.map((j) => (
                  <JobRow
                    key={j.id}
                    job={j}
                    onCancel={(jid) => act(async () => (await api(`/jobs/${jid}/cancel`, { method: "POST" }), refresh()))}
                  />
                ))}
              </div>
            )}
          </Card>

          {p.source && (
            <Card className="p-5">
              <h3 className="mb-3 text-sm font-semibold">Source file</h3>
              <dl className="space-y-3">
                <Meta label="Filename" value={p.source.filename} mono={false} />
                <Meta label="SHA-256" value={<span title={p.source.sha256 ?? ""}>{p.source.sha256?.slice(0, 16)}…</span>} />
                <Meta label="Stored" value={new Date(p.source.created_at).toLocaleString()} mono={false} />
              </dl>
            </Card>
          )}

          <Card className="border-dashed p-5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles className="h-4 w-4 text-accent" /> Next: AI clip discovery
            </div>
            <p className="mt-2 text-sm text-muted">
              Transcription, scene analysis and clip scoring arrive in Milestone 2. Your stored video and metadata will be used as-is.
            </p>
          </Card>
        </aside>
      </div>
    </>
  );
}
