"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Archive,
  Check,
  CheckCircle2,
  ChevronDown,
  Download,
  Play,
  Scissors,
  Search,
  Sparkles,
  Wand2,
  X,
  XCircle,
} from "lucide-react";
import { Card, ErrorNote, ProgressBar, Spinner, StatusBadge, btn } from "@/components/ui";
import {
  api,
  renderFileUrl,
  rendersZipUrl,
  type AnalysisState,
  type Candidate,
  type Capabilities,
  type StyleCatalog,
  type Render,
} from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";
import { usePolling } from "@/lib/usePolling";

const DURATIONS = [
  { label: "15–30 s", min: 15, max: 30 },
  { label: "30–60 s", min: 30, max: 60 },
  { label: "45–90 s", min: 45, max: 90 },
];
const LANGS = [
  { value: "", label: "Auto-detect" },
  { value: "id", label: "Indonesian" },
  { value: "en", label: "English" },
];
const STAGE_LABEL: Record<string, string> = {
  queued: "Waiting for a worker",
  transcribing: "Transcribing speech",
  analyzing: "AI is choosing the best moments",
};
const SCORE_LABELS: Record<string, string> = {
  hook: "Hook",
  emotion: "Emotion",
  value: "Value",
  standalone: "Standalone",
  retention: "Retention",
  shareability: "Shareability",
};

function ts(s: number) {
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  return `${m}:${sec.toFixed(1).padStart(4, "0")}`;
}

function ScorePill({ score }: { score: number }) {
  const tone = score >= 75 ? "text-ok border-ok/40" : score >= 55 ? "text-warn border-warn/40" : "text-ink-2 border-line-strong";
  return (
    <span className={`tabular rounded-md border px-1.5 py-0.5 font-mono text-xs font-semibold ${tone}`} title="Weighted AI score (not a virality guarantee)">
      {Math.round(score)}
    </span>
  );
}

function CandidateCard({
  c,
  checked,
  onToggle,
  onReject,
  onPreview,
}: {
  c: Candidate;
  checked: boolean;
  onToggle: () => void;
  onReject: () => void;
  onPreview: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rejected = c.status === "rejected";
  return (
    <div
      className={`rounded-xl border p-4 transition ${
        rejected ? "border-line bg-surface/40 opacity-55" : checked ? "border-accent/60 bg-accent-soft/40" : "border-line bg-surface-2"
      }`}
    >
      <div className="flex items-start gap-3">
        <button
          aria-label={checked ? "Deselect clip" : "Select clip"}
          onClick={onToggle}
          disabled={rejected}
          className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded border ${
            checked ? "border-accent bg-accent text-[#160a04]" : "border-line-strong"
          }`}
        >
          {checked && <Check className="h-3.5 w-3.5" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted">#{c.rank}</span>
            <span className="text-sm font-semibold">{c.title}</span>
            <ScorePill score={c.score} />
            <span className="rounded-full border border-line px-2 py-px text-[11px] text-ink-2 capitalize">{c.category}</span>
          </div>
          <div className="tabular mt-1 font-mono text-xs text-muted">
            {ts(c.start_s)} → {ts(c.end_s)} · {formatDuration(c.end_s - c.start_s)} · confidence {Math.round(c.confidence * 100)}%
          </div>
          <p className="mt-2 text-sm text-ink">
            <span className="text-muted">Hook: </span>“{c.hook}”
          </p>
          <p className="mt-1 text-sm text-ink-2">{c.reason}</p>
          {open && (
            <div className="mt-3 space-y-3">
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                {Object.entries(c.scores).map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-surface-3 px-2 py-1.5 text-center">
                    <div className="text-[10px] text-muted">{SCORE_LABELS[k] ?? k}</div>
                    <div className="tabular font-mono text-sm">{v}/10</div>
                  </div>
                ))}
              </div>
              <blockquote className="rounded-lg border-l-2 border-line-strong bg-surface-3/60 p-3 text-sm leading-relaxed text-ink-2">
                {c.transcript_text}
              </blockquote>
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-1.5">
            <button className={`${btn.ghost} px-2 py-1 text-xs`} onClick={onPreview}>
              <Play className="h-3.5 w-3.5" /> Preview
            </button>
            <button className={`${btn.ghost} px-2 py-1 text-xs`} onClick={() => setOpen(!open)}>
              <ChevronDown className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`} /> {open ? "Less" : "Transcript & scores"}
            </button>
            <button className={`${btn.ghost} px-2 py-1 text-xs`} onClick={onReject}>
              {rejected ? "Restore" : (
                <>
                  <X className="h-3.5 w-3.5" /> Reject
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function RenderCard({ r }: { r: Render }) {
  const [showQc, setShowQc] = useState(false);
  const active = r.status === "queued" || r.status === "rendering";
  const qcTone = r.qc?.status === "pass" ? "text-ok" : r.qc?.status === "warn" ? "text-warn" : "text-bad";
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface-2" data-testid="render-card">
      <div className="relative mx-auto aspect-[9/16] w-full bg-black">
        {r.status === "succeeded" ? (
          <video src={renderFileUrl(r.id)} controls preload="metadata" className="h-full w-full object-contain" />
        ) : (
          <div className="grid h-full place-items-center p-4 text-center text-sm text-muted">
            {active ? (
              <div className="w-full space-y-3">
                <Spinner className="mx-auto h-6 w-6 text-info" />
                <div>{r.job?.stage ?? "Waiting for a worker"}</div>
                <ProgressBar value={r.job?.progress ?? 0} tone="info" />
                <div className="tabular font-mono text-xs">{Math.round((r.job?.progress ?? 0) * 100)}%</div>
              </div>
            ) : (
              <div className="space-y-2">
                <XCircle className="mx-auto h-6 w-6 text-bad" />
                <div className="text-bad">Render failed</div>
                <div className="text-xs">{r.error}</div>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium" title={r.title}>
              #{r.rank} {r.title}
            </div>
            <div className="text-xs text-muted">
              {formatDuration(r.duration_s)} · {r.settings.resolved_style_name ?? r.settings.subtitle_style ?? "style"}
              {r.settings.captions === false ? " · no captions" : ""}
              {r.file_size_bytes ? ` · ${formatBytes(r.file_size_bytes)}` : ""}
            </div>
          </div>
          <StatusBadge status={r.status === "rendering" ? "running" : r.status} />
        </div>
        {r.qc && (
          <button className={`flex items-center gap-1.5 text-xs ${qcTone}`} onClick={() => setShowQc(!showQc)}>
            {r.qc.status === "pass" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
            Quality check: {r.qc.status === "pass" ? "passed" : r.qc.status === "warn" ? "passed with warnings" : "failed"}
            <ChevronDown className={`h-3 w-3 transition ${showQc ? "rotate-180" : ""}`} />
          </button>
        )}
        {showQc && r.qc && (
          <ul className="space-y-1.5 rounded-lg bg-surface-3/60 p-2.5 text-xs">
            {r.qc.checks.map((c) => (
              <li key={c.name} className="flex gap-2">
                <span className={c.status === "pass" ? "text-ok" : c.status === "warn" ? "text-warn" : "text-bad"}>
                  {c.status === "pass" ? "✓" : c.status === "warn" ? "!" : "✕"}
                </span>
                <span className="text-ink-2">
                  {c.detail}
                  {c.fix && <span className="block text-muted">{c.fix}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
        {r.status === "succeeded" && (
          <a href={renderFileUrl(r.id, true)} className={`${btn.secondary} w-full py-1.5 text-xs`}>
            <Download className="h-3.5 w-3.5" /> Download MP4
          </a>
        )}
      </div>
    </div>
  );
}

const STYLE_GROUPS = [
  { id: "podcast", label: "Your editing skills" },
  { id: "showcase", label: "Before / After showcase" },
  { id: "basic", label: "MSclips basic captions" },
] as const;

export default function ClipStudio({
  projectId,
  durationS,
  hasAudio,
  onPreview,
}: {
  projectId: string;
  durationS: number;
  hasAudio: boolean;
  onPreview: (start: number, end: number) => void;
}) {
  const [count, setCount] = useState(5);
  const [dur, setDur] = useState(1);
  const [lang, setLang] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [sort, setSort] = useState<"score" | "time">("score");
  const [style, setStyle] = useState("auto");
  const [captions, setCaptions] = useState(true);
  const [showHook, setShowHook] = useState(true);

  const { data: catalog } = usePolling(() => api<StyleCatalog>("/styles"), { shouldPoll: () => false });
  const chosen = catalog?.styles.find((s) => s.id === style);

  const { data: caps } = usePolling(() => api<Capabilities>("/capabilities"), { shouldPoll: () => false });
  const analysis = usePolling(() => api<AnalysisState>(`/projects/${projectId}/analysis`), {
    intervalMs: 1500,
    shouldPoll: (d) => !!d.job && (d.job.status === "queued" || d.job.status === "running"),
    deps: [projectId],
  });
  const renders = usePolling(() => api<Render[]>(`/projects/${projectId}/renders`), {
    intervalMs: 1500,
    shouldPoll: (d) => d.some((r) => r.status === "queued" || r.status === "rendering"),
    deps: [projectId],
  });

  const st = analysis.data;
  const running = !!st?.job && (st.job.status === "queued" || st.job.status === "running");
  const cands = useMemo(() => {
    let list = st?.candidates ?? [];
    if (q) list = list.filter((c) => (c.title + " " + c.hook + " " + c.transcript_text).toLowerCase().includes(q.toLowerCase()));
    if (cat) list = list.filter((c) => c.category === cat);
    return [...list].sort((a, b) => (sort === "score" ? b.score - a.score : a.start_s - b.start_s));
  }, [st?.candidates, q, cat, sort]);
  const categories = Array.from(new Set((st?.candidates ?? []).map((c) => c.category)));

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const startAnalysis = () =>
    act(async () => {
      const d = DURATIONS[dur];
      await api(`/projects/${projectId}/analysis`, {
        method: "POST",
        body: JSON.stringify({ clip_count: count, min_duration_s: d.min, max_duration_s: d.max, language: lang || null }),
      });
      setSelected(new Set());
      analysis.refresh();
    });

  const toggleReject = (c: Candidate) =>
    act(async () => {
      await api(`/candidates/${c.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: c.status === "rejected" ? "proposed" : "rejected" }),
      });
      setSelected((s) => {
        const n = new Set(s);
        n.delete(c.id);
        return n;
      });
      analysis.refresh();
    });

  const renderSelected = (ids: string[]) =>
    act(async () => {
      await api(`/projects/${projectId}/renders`, {
        method: "POST",
        body: JSON.stringify({ candidate_ids: ids, edit_style: style, captions, show_hook: showHook }),
      });
      setSelected(new Set());
      renders.refresh();
    });

  const maxClips = Math.max(1, Math.min(15, Math.floor(durationS / DURATIONS[dur].min)));
  const succeeded = (renders.data ?? []).filter((r) => r.status === "succeeded").length;

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold">Find the best clips with AI</h2>
        </div>
        <p className="mt-1 text-sm text-muted">
          The video is transcribed with word timestamps, then the AI reads the transcript and picks the strongest standalone moments.
          Cut points are snapped to word and sentence boundaries.
        </p>

        {!hasAudio && <div className="mt-4"><ErrorNote error="This video has no audio track, so there is no speech to analyse." /></div>}
        {caps && !caps.ai.api_key_configured && (
          <div className="mt-4 flex gap-3 rounded-xl border border-warn/30 bg-warn/10 p-3 text-sm text-ink-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
            <span>
              No Claude API key is configured on the server (<span className="font-mono">ANTHROPIC_API_KEY</span>). Transcription will run,
              but choosing clips will stop with an error until a key is set.
            </span>
          </div>
        )}

        <div className="mt-5 grid gap-5 md:grid-cols-[1fr_auto_auto]">
          <label className="block">
            <span className="flex justify-between text-xs font-medium text-ink-2">
              <span>Number of clips</span>
              <span className="tabular font-mono text-ink">{Math.min(count, maxClips)}</span>
            </span>
            <input
              type="range"
              min={1}
              max={maxClips}
              value={Math.min(count, maxClips)}
              onChange={(e) => setCount(Number(e.target.value))}
              className="mt-3 w-full accent-[var(--color-accent)]"
              data-testid="clip-count"
            />
          </label>
          <div>
            <span className="text-xs font-medium text-ink-2">Clip length</span>
            <div className="mt-2 flex gap-1.5">
              {DURATIONS.map((d, i) => (
                <button
                  key={d.label}
                  onClick={() => setDur(i)}
                  className={`rounded-lg border px-2.5 py-1.5 text-xs ${dur === i ? "border-accent/60 bg-accent-soft text-ink" : "border-line text-ink-2"}`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
          <label className="block">
            <span className="text-xs font-medium text-ink-2">Spoken language</span>
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              className="mt-2 block w-full rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-sm"
            >
              {LANGS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button className={btn.primary} onClick={startAnalysis} disabled={busy || running || !hasAudio}>
            <Wand2 className="h-4 w-4" /> {st?.run ? "Analyse again" : "Find clips"}
          </button>
          {caps && <span className="text-xs text-muted">Transcription: {caps.transcription.engine} · AI: {caps.ai.model}</span>}
        </div>

        {running && st?.run && st.job && (
          <div className="mt-5 space-y-2 rounded-xl border border-line bg-surface-2 p-4" data-testid="analysis-progress">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                <Spinner className="h-3.5 w-3.5 text-info" /> {STAGE_LABEL[st.run.status] ?? st.job.stage}
              </span>
              <span className="tabular font-mono text-xs text-ink-2">{Math.round(st.job.progress * 100)}%</span>
            </div>
            <ProgressBar value={st.job.progress} tone="info" />
            {st.job.stage && st.job.stage.toLowerCase() !== (STAGE_LABEL[st.run.status] ?? "").toLowerCase() && (
              <div className="text-xs text-muted">{st.job.stage}</div>
            )}
          </div>
        )}
        {st?.run?.status === "failed" && st.run.error && (
          <div className="mt-5">
            <ErrorNote error={st.run.error} />
          </div>
        )}
        {err && (
          <div className="mt-5">
            <ErrorNote error={err} />
          </div>
        )}
        {st?.transcript && (
          <div className="mt-4 text-xs text-muted">
            Transcript: {st.transcript.word_count} words, language <span className="font-mono">{st.transcript.language}</span> ({st.transcript.engine})
          </div>
        )}
      </Card>

      {st?.run?.status === "succeeded" && (
        <Card className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">
                {st.candidates.length} clip candidate{st.candidates.length === 1 ? "" : "s"}
              </h2>
              {st.run.notes && <p className="mt-1 text-sm text-muted">{st.run.notes}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className={btn.secondary}
                disabled={busy}
                onClick={() =>
                  setSelected(new Set(st.candidates.filter((c) => c.status !== "rejected").map((c) => c.id)))
                }
              >
                Select all
              </button>
            </div>
          </div>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="relative flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search clips"
                className="w-full rounded-lg border border-line bg-surface-2 py-1.5 pr-3 pl-9 text-sm placeholder:text-muted"
              />
            </label>
            <select value={cat} onChange={(e) => setCat(e.target.value)} className="rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-sm">
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select value={sort} onChange={(e) => setSort(e.target.value as "score" | "time")} className="rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-sm">
              <option value="score">Sort by score</option>
              <option value="time">Sort by time</option>
            </select>
          </div>
          <div className="mt-4 space-y-3">
            {cands.map((c) => (
              <CandidateCard
                key={c.id}
                c={c}
                checked={selected.has(c.id)}
                onToggle={() =>
                  setSelected((s) => {
                    const n = new Set(s);
                    if (n.has(c.id)) n.delete(c.id);
                    else n.add(c.id);
                    return n;
                  })
                }
                onReject={() => toggleReject(c)}
                onPreview={() => onPreview(c.start_s, c.end_s)}
              />
            ))}
          </div>
          <div className="sticky bottom-3 mt-5 flex flex-wrap items-center gap-3 rounded-xl border border-line-strong bg-surface-3/95 p-3 backdrop-blur">
            <span className="text-sm">
              <span className="tabular font-semibold">{selected.size}</span> selected
            </span>
            <select value={style} onChange={(e) => setStyle(e.target.value)} className="max-w-full rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-sm" aria-label="Editing style">
              <option value="auto">Auto: best style per clip</option>
              {STYLE_GROUPS.map((g) => (
                <optgroup key={g.id} label={g.label}>
                  {(catalog?.styles ?? []).filter((s) => s.group === g.id).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input type="checkbox" checked={captions} onChange={(e) => setCaptions(e.target.checked)} className="accent-[var(--color-accent)]" />
              Captions
            </label>
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input type="checkbox" checked={showHook} onChange={(e) => setShowHook(e.target.checked)} className="accent-[var(--color-accent)]" />
              Hook title (first 3 s)
            </label>
            <button className={`${btn.primary} ml-auto`} disabled={busy || selected.size === 0} onClick={() => renderSelected(Array.from(selected))}>
              <Scissors className="h-4 w-4" /> Render {selected.size || ""} clip{selected.size === 1 ? "" : "s"}
            </button>
            <p className="w-full text-xs text-muted" data-testid="style-help">
              {style === "auto"
                ? "MSclips picks a style for each clip from the AI's label (e.g. educational → Explainer, story → Sinematik Lukis)."
                : chosen
                  ? `${chosen.tagline} From ${chosen.source}.${chosen.omitted.length ? ` Not included yet: ${chosen.omitted.join(", ")}.` : ""}`
                  : ""}
            </p>
          </div>
        </Card>
      )}

      {renders.data && renders.data.length > 0 && (
        <Card className="p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Rendered clips</h2>
              <p className="mt-0.5 text-xs text-muted">1080×1920 · H.264/AAC · 30 fps. Each file is checked after rendering.</p>
            </div>
            {succeeded > 0 && (
              <a href={rendersZipUrl(projectId)} className={btn.secondary}>
                <Archive className="h-4 w-4" /> Download all ({succeeded}) as ZIP
              </a>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
            {renders.data.map((r) => (
              <RenderCard key={r.id} r={r} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
