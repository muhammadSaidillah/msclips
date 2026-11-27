export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");

export type ProjectStatus = "uploading" | "processing" | "ready" | "failed" | "cancelled";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type UploadStatus = "active" | "completed" | "cancelled" | "failed";

export interface ProjectSummary {
  id: string;
  name: string;
  status: ProjectStatus;
  status_message: string | null;
  created_at: string;
  updated_at: string;
  has_thumbnail: boolean;
  source_filename: string | null;
  source_size_bytes: number | null;
  duration_s: number | null;
  width: number | null;
  height: number | null;
  aspect_ratio: string | null;
}

export interface VideoMetadata {
  container: string | null;
  duration_s: number;
  width: number;
  height: number;
  rotation: number;
  display_width: number;
  display_height: number;
  aspect_ratio: string;
  orientation: string;
  fps: number | null;
  video_codec: string | null;
  pixel_format: string | null;
  bit_rate: number | null;
  has_audio: boolean;
  audio_codec: string | null;
  audio_channels: number | null;
  audio_sample_rate: number | null;
  audio_track_count: number;
}

export interface Job {
  id: string;
  project_id: string;
  type: string;
  status: JobStatus;
  progress: number;
  stage: string | null;
  attempts: number;
  max_attempts: number;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Upload {
  id: string;
  project_id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  chunk_size: number;
  total_chunks: number;
  received_chunks: number[];
  received_bytes: number;
  status: UploadStatus;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Asset {
  id: string;
  kind: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  sha256: string | null;
  storage_backend: string;
  created_at: string;
}

export interface ProjectDetail extends ProjectSummary {
  source: Asset | null;
  metadata: VideoMetadata | null;
  upload: Upload | null;
  jobs: Job[];
}

export interface Dashboard {
  project_counts: Record<ProjectStatus, number>;
  total_projects: number;
  total_source_bytes: number;
  total_source_duration_s: number;
  active_jobs: number;
  recent_projects: ProjectSummary[];
}

export interface Health {
  ok: boolean;
  checks: Record<string, { ok: boolean; error?: string; backend?: string }>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return fallback;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...(init?.body && typeof init.body === "string" ? { "Content-Type": "application/json" } : {}), ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Cannot reach the MSclips Maker API at ${API_URL}. Is the backend running?`);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = undefined;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = (body as { detail?: unknown })?.detail ?? body;
    throw new ApiError(res.status, messageFrom(detail, `Request failed (${res.status})`), detail);
  }
  return body as T;
}

export const thumbnailUrl = (p: { id: string; updated_at: string }) =>
  `${API_URL}/projects/${p.id}/thumbnail?v=${encodeURIComponent(p.updated_at)}`;
export const sourceUrl = (id: string) => `${API_URL}/projects/${id}/source`;

export interface Candidate {
  id: string;
  rank: number;
  title: string;
  start_s: number;
  end_s: number;
  hook: string;
  category: string;
  reason: string;
  transcript_text: string;
  scores: Record<string, number>;
  score: number;
  confidence: number;
  editing_style: string | null;
  status: "proposed" | "selected" | "rejected";
}

export interface AnalysisState {
  run: {
    id: string;
    status: "queued" | "transcribing" | "analyzing" | "succeeded" | "failed";
    clip_count: number;
    min_duration_s: number;
    max_duration_s: number;
    language: string | null;
    model: string | null;
    error: string | null;
    notes: string | null;
    created_at: string;
  } | null;
  job: Job | null;
  transcript: {
    language: string;
    language_probability: number | null;
    engine: string;
    duration_s: number;
    segment_count: number;
    word_count: number;
  } | null;
  candidates: Candidate[];
}

export interface QcCheck {
  name: string;
  status: "pass" | "warn" | "fail";
  detail: string;
  fix: string | null;
}

export interface Render {
  id: string;
  candidate_id: string;
  rank: number;
  title: string;
  duration_s: number;
  status: "queued" | "rendering" | "succeeded" | "failed";
  error: string | null;
  settings: {
    edit_style?: string;
    subtitle_style?: string;
    captions?: boolean;
    show_hook: boolean;
    resolved_style?: string;
    resolved_style_name?: string;
    style_reason?: string;
  };
  crop: { mode: string; face_frames: number; sampled_frames: number } | null;
  qc: { status: "pass" | "warn" | "fail"; checks: QcCheck[] } | null;
  job: Job | null;
  file_size_bytes: number | null;
  filename: string | null;
  created_at: string;
}

export interface EditStyle {
  id: string;
  name: string;
  tagline: string;
  source: string;
  group: "basic" | "podcast" | "showcase";
  grade: string;
  zoom: string;
  framing: string;
  showcase: boolean;
  omitted: string[];
}

export interface StyleCatalog {
  default: string;
  styles: EditStyle[];
}

export interface Capabilities {
  transcription: { engine: string; device: string };
  ai: { model: string; api_key_configured: boolean };
}

export const renderFileUrl = (id: string, download = false) =>
  `${API_URL}/renders/${id}/file${download ? "?download=true" : ""}`;
export const rendersZipUrl = (projectId: string) => `${API_URL}/projects/${projectId}/renders.zip`;
