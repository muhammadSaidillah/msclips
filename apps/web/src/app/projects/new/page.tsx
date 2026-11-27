"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, FileVideo, RotateCcw, ShieldCheck, UploadCloud, X } from "lucide-react";
import { Card, ErrorNote, PageHeader, ProgressBar, Spinner, btn } from "@/components/ui";
import { formatBytes, formatDuration } from "@/lib/format";
import { ChunkedUploader, type UploadState } from "@/lib/upload";

// Mirrors the server defaults for instant feedback; the server re-validates everything.
const ALLOWED = [".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"];
const MAX_BYTES = 20 * 1024 ** 3;

function validate(file: File): string | null {
  const ext = file.name.includes(".") ? file.name.slice(file.name.lastIndexOf(".")).toLowerCase() : "";
  if (!ALLOWED.includes(ext)) return `“${file.name}” is not a supported video file. Use ${ALLOWED.join(", ")}.`;
  if (file.type && !file.type.startsWith("video/") && file.type !== "application/octet-stream")
    return `“${file.name}” has type ${file.type}, which is not a video.`;
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_BYTES) return `File is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_BYTES)}.`;
  return null;
}

const PHASE_LABEL: Record<UploadState["phase"], string> = {
  creating: "Creating project…",
  uploading: "Uploading",
  finalizing: "Verifying upload with server…",
  done: "Upload confirmed by server",
  failed: "Upload interrupted",
  cancelled: "Upload cancelled",
};

export default function NewProjectPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [state, setState] = useState<UploadState | null>(null);
  const uploader = useRef<ChunkedUploader | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const busy = state && ["creating", "uploading", "finalizing"].includes(state.phase);

  useEffect(() => {
    if (!busy) return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [busy]);

  useEffect(() => {
    if (state?.phase === "done" && state.project) {
      const t = setTimeout(() => router.push(`/projects/${state.project!.id}`), 900);
      return () => clearTimeout(t);
    }
  }, [state?.phase, state?.project, router]);

  const pick = useCallback(
    (f: File | undefined) => {
      if (!f || busy) return;
      const err = validate(f);
      setFileError(err);
      setFile(err ? null : f);
      setState(null);
      if (!err && !name) setName(f.name.replace(/\.[^.]+$/, ""));
    },
    [busy, name],
  );

  const start = () => {
    if (!file) return;
    const u = new ChunkedUploader(file, name.trim(), setState);
    uploader.current = u;
    u.start();
  };

  const reset = () => {
    uploader.current = null;
    setState(null);
    setFile(null);
    setName("");
  };

  const pct = state ? state.bytesSent / Math.max(1, state.totalBytes) : 0;
  const eta =
    state?.phase === "uploading" && state.bytesPerSecond && state.bytesPerSecond > 0
      ? (state.totalBytes - state.bytesSent) / state.bytesPerSecond
      : null;

  return (
    <>
      <PageHeader title="New Project" subtitle="Upload one long video. CLIPFORGE stores it and extracts its technical metadata." />

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-5">
          {!state && (
            <div
              role="button"
              tabIndex={0}
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                pick(e.dataTransfer.files?.[0]);
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-14 text-center transition ${
                drag ? "border-accent bg-accent-soft" : "border-line-strong bg-surface/60 hover:border-accent/50"
              }`}
            >
              <span className="grid h-14 w-14 place-items-center rounded-2xl bg-surface-3">
                <UploadCloud className={`h-6 w-6 ${drag ? "text-accent" : "text-ink-2"}`} />
              </span>
              <div className="text-base font-medium">Drop a video here, or click to browse</div>
              <div className="text-sm text-muted">
                {ALLOWED.join(" ")} · up to {formatBytes(MAX_BYTES)}
              </div>
              <input
                ref={inputRef}
                type="file"
                accept={ALLOWED.join(",") + ",video/*"}
                className="hidden"
                data-testid="file-input"
                onChange={(e) => {
                  pick(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </div>
          )}

          {fileError && <ErrorNote error={fileError} />}

          {file && (
            <Card className="p-5">
              <div className="flex items-start gap-4">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-surface-3">
                  <FileVideo className="h-5 w-5 text-accent" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium" title={file.name}>
                    {file.name}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {formatBytes(file.size)} · {file.type || "unknown type"}
                  </div>
                </div>
                {!state && (
                  <button aria-label="Remove file" className={btn.ghost} onClick={reset}>
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>

              {!state && (
                <div className="mt-5 space-y-4">
                  <label className="block">
                    <span className="text-xs font-medium text-ink-2">Project name</span>
                    <input
                      value={name}
                      maxLength={200}
                      onChange={(e) => setName(e.target.value)}
                      className="mt-1.5 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm focus:border-accent/60 focus:outline-none"
                    />
                  </label>
                  <button className={`${btn.primary} w-full sm:w-auto`} onClick={start}>
                    <UploadCloud className="h-4 w-4" /> Upload and create project
                  </button>
                </div>
              )}

              {state && (
                <div className="mt-5 space-y-3" data-testid="upload-progress">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 font-medium">
                      {busy && <Spinner className="h-3.5 w-3.5 text-accent" />}
                      {state.phase === "done" && <CheckCircle2 className="h-4 w-4 text-ok" />}
                      {PHASE_LABEL[state.phase]}
                    </span>
                    <span className="tabular font-mono text-xs text-ink-2">{(pct * 100).toFixed(1)}%</span>
                  </div>
                  <ProgressBar value={pct} tone={state.phase === "done" ? "ok" : "accent"} />
                  <div className="tabular flex flex-wrap justify-between gap-2 text-xs text-muted">
                    <span>
                      {formatBytes(state.bytesSent)} of {formatBytes(state.totalBytes)}
                    </span>
                    {state.phase === "uploading" && (
                      <span>
                        {state.bytesPerSecond ? `${formatBytes(state.bytesPerSecond)}/s` : "measuring speed…"}
                        {eta != null && ` · ${formatDuration(eta)} left`}
                      </span>
                    )}
                  </div>
                  {state.error && <ErrorNote error={state.error} />}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {(state.phase === "uploading" || state.phase === "creating") && (
                      <button className={btn.secondary} onClick={() => uploader.current?.cancel()}>
                        <X className="h-4 w-4" /> Cancel upload
                      </button>
                    )}
                    {state.phase === "failed" && (
                      <>
                        <button className={btn.primary} onClick={() => uploader.current?.retry()}>
                          <RotateCcw className="h-4 w-4" /> {state.upload ? "Resume upload" : "Retry"}
                        </button>
                        {state.upload && (
                          <button className={btn.secondary} onClick={() => uploader.current?.cancel()}>
                            Discard
                          </button>
                        )}
                      </>
                    )}
                    {state.phase === "cancelled" && (
                      <button className={btn.secondary} onClick={reset}>
                        Choose another file
                      </button>
                    )}
                    {state.phase === "done" && <span className="text-sm text-muted">Opening project…</span>}
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>

        <aside className="space-y-4">
          <Card className="p-5">
            <h3 className="text-sm font-semibold">What happens next</h3>
            <ol className="mt-3 space-y-3 text-sm text-ink-2">
              {[
                ["Upload", "Sent in 8 MB chunks. Interrupted uploads resume where they stopped."],
                ["Verify & store", "The server checks size and SHA-256, then moves the file to storage."],
                ["Read metadata", "Duration, resolution, FPS, aspect ratio and audio tracks via ffprobe."],
                ["Thumbnail", "A poster frame is extracted and the project is marked ready."],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-3">
                  <span className="tabular grid h-5 w-5 shrink-0 place-items-center rounded-full bg-surface-3 font-mono text-[11px] text-ink">
                    {i + 1}
                  </span>
                  <span>
                    <span className="font-medium text-ink">{t}.</span> {d}
                  </span>
                </li>
              ))}
            </ol>
          </Card>
          <Card className="flex gap-3 p-5 text-sm text-ink-2">
            <ShieldCheck className="h-4.5 w-4.5 shrink-0 text-ok" />
            <span>Only upload videos you own or have permission to repurpose.</span>
          </Card>
        </aside>
      </div>
    </>
  );
}
