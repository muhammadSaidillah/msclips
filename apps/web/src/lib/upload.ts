import { API_URL, ApiError, api, type Job, type ProjectSummary, type Upload } from "./api";

export type UploadPhase = "creating" | "uploading" | "finalizing" | "done" | "failed" | "cancelled";

export interface UploadState {
  phase: UploadPhase;
  bytesSent: number; // bytes the server has confirmed + bytes in flight
  totalBytes: number;
  bytesPerSecond: number | null;
  error: string | null;
  upload: Upload | null;
  project: ProjectSummary | null;
  job: Job | null;
}

const CONCURRENCY = 3;
const MAX_CHUNK_ATTEMPTS = 5;

class ChunkError extends Error {
  constructor(
    message: string,
    public retryable: boolean,
  ) {
    super(message);
  }
}

/**
 * Resumable chunked uploader. Progress is computed only from bytes the browser has actually sent
 * and chunks the server has acknowledged; nothing is simulated.
 */
export class ChunkedUploader {
  state: UploadState;
  private xhrs = new Set<XMLHttpRequest>();
  private inFlight = new Map<number, number>();
  private confirmed = new Set<number>();
  private aborted = false;
  private samples: { t: number; b: number }[] = [];

  constructor(
    private file: File,
    private projectName: string,
    private onChange: (s: UploadState) => void,
  ) {
    this.state = {
      phase: "creating",
      bytesSent: 0,
      totalBytes: file.size,
      bytesPerSecond: null,
      error: null,
      upload: null,
      project: null,
      job: null,
    };
  }

  private emit(patch: Partial<UploadState>) {
    this.state = { ...this.state, ...patch };
    this.onChange(this.state);
  }

  private chunkLen(i: number, up: Upload) {
    return Math.min(up.chunk_size, up.size_bytes - i * up.chunk_size);
  }

  private recomputeBytes(up: Upload) {
    let b = 0;
    for (const i of this.confirmed) b += this.chunkLen(i, up);
    for (const v of this.inFlight.values()) b += v;
    const now = performance.now();
    this.samples.push({ t: now, b });
    this.samples = this.samples.filter((s) => now - s.t < 5000);
    const first = this.samples[0];
    const bps = first && now - first.t > 800 ? ((b - first.b) / (now - first.t)) * 1000 : this.state.bytesPerSecond;
    this.emit({ bytesSent: b, bytesPerSecond: bps });
  }

  async start() {
    this.aborted = false;
    try {
      this.emit({ phase: "creating", error: null });
      const res = await api<{ upload: Upload; project: ProjectSummary }>("/uploads", {
        method: "POST",
        body: JSON.stringify({
          filename: this.file.name,
          size_bytes: this.file.size,
          content_type: this.file.type || null,
          project_name: this.projectName || null,
        }),
      });
      this.emit({ upload: res.upload, project: res.project });
      await this.run();
    } catch (e) {
      this.fail(e);
    }
  }

  /** Continue an upload session created earlier (e.g. before a page reload). File must match. */
  async resumeExisting(upload: Upload) {
    if (upload.filename !== this.file.name || upload.size_bytes !== this.file.size) {
      this.emit({
        phase: "failed",
        error: `Pick the same file: expected “${upload.filename}” (${upload.size_bytes} bytes).`,
      });
      return;
    }
    this.emit({ upload });
    return this.retry();
  }

  /** Resume after a failure: asks the server which chunks it already has and sends only the rest. */
  async retry() {
    if (!this.state.upload) return this.start();
    this.aborted = false;
    try {
      await this.run();
    } catch (e) {
      this.fail(e);
    }
  }

  async cancel() {
    this.aborted = true;
    for (const x of this.xhrs) x.abort();
    this.xhrs.clear();
    const up = this.state.upload;
    if (up && this.state.phase !== "done") {
      try {
        await api(`/uploads/${up.id}`, { method: "DELETE" });
      } catch (e) {
        // If cancel itself fails, say so rather than pretending.
        this.emit({ phase: "failed", error: `Cancel failed: ${(e as Error).message}` });
        return;
      }
    }
    this.emit({ phase: "cancelled", bytesPerSecond: null });
  }

  private fail(e: unknown) {
    if (this.aborted) return;
    for (const x of this.xhrs) x.abort();
    this.xhrs.clear();
    this.inFlight.clear();
    this.emit({ phase: "failed", error: (e as Error).message || "Upload failed", bytesPerSecond: null });
  }

  private async run() {
    let up = await api<Upload>(`/uploads/${this.state.upload!.id}`);
    if (up.status !== "active") throw new Error(`This upload is ${up.status} and cannot continue.`);
    this.confirmed = new Set(up.received_chunks);
    this.inFlight.clear();
    this.samples = [];
    this.emit({ phase: "uploading", upload: up, error: null });
    this.recomputeBytes(up);

    const pending: number[] = [];
    for (let i = 0; i < up.total_chunks; i++) if (!this.confirmed.has(i)) pending.push(i);

    const worker = async () => {
      while (pending.length && !this.aborted) {
        const i = pending.shift()!;
        await this.sendWithRetry(i, up);
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, pending.length) }, worker));
    if (this.aborted) return;

    this.emit({ phase: "finalizing", bytesPerSecond: null });
    const done = await api<{ upload: Upload; job: Job }>(`/uploads/${up.id}/complete`, { method: "POST" });
    up = done.upload;
    this.emit({ phase: "done", upload: up, job: done.job, bytesSent: up.size_bytes });
  }

  private async sendWithRetry(i: number, up: Upload) {
    for (let attempt = 1; ; attempt++) {
      try {
        await this.sendChunk(i, up);
        return;
      } catch (e) {
        if (this.aborted) return;
        const err = e as ChunkError;
        if (!err.retryable || attempt >= MAX_CHUNK_ATTEMPTS) throw err;
        await new Promise((r) => setTimeout(r, Math.min(15000, 1000 * 2 ** (attempt - 1))));
      }
    }
  }

  private sendChunk(i: number, up: Upload): Promise<void> {
    const start = i * up.chunk_size;
    const blob = this.file.slice(start, start + this.chunkLen(i, up));
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      this.xhrs.add(xhr);
      xhr.open("PUT", `${API_URL}/uploads/${up.id}/chunks/${i}`);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.upload.onprogress = (ev) => {
        this.inFlight.set(i, ev.loaded);
        this.recomputeBytes(up);
      };
      const cleanup = () => {
        this.xhrs.delete(xhr);
        this.inFlight.delete(i);
      };
      xhr.onload = () => {
        cleanup();
        if (xhr.status >= 200 && xhr.status < 300) {
          this.confirmed.add(i);
          this.recomputeBytes(up);
          resolve();
        } else {
          let msg = `Chunk ${i + 1}/${up.total_chunks} rejected (${xhr.status})`;
          try {
            const d = JSON.parse(xhr.responseText)?.detail;
            if (typeof d === "string") msg = d;
          } catch {}
          this.recomputeBytes(up);
          reject(new ChunkError(msg, xhr.status >= 500 || xhr.status === 408 || xhr.status === 429));
        }
      };
      xhr.onerror = () => {
        cleanup();
        this.recomputeBytes(up);
        reject(new ChunkError("Network error while uploading. Check your connection.", true));
      };
      xhr.onabort = () => {
        cleanup();
        reject(new ChunkError("aborted", false));
      };
      xhr.send(blob);
    });
  }
}

export { ApiError };
