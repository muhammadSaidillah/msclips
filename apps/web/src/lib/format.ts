export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDuration(s: number | null | undefined): string {
  if (s == null) return "—";
  const total = Math.round(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  const pad = (x: number) => String(x).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

export function formatHoursTotal(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

export function formatRelative(iso: string): string {
  const d = new Date(iso).getTime();
  const diff = (Date.now() - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function formatBitrate(bps: number | null | undefined): string {
  if (!bps) return "—";
  return bps >= 1_000_000 ? `${(bps / 1_000_000).toFixed(1)} Mbps` : `${Math.round(bps / 1000)} kbps`;
}

export function formatChannels(n: number | null | undefined): string {
  if (!n) return "—";
  return n === 1 ? "Mono" : n === 2 ? "Stereo" : `${n} ch`;
}

/** ffprobe reports demuxer families like "mov,mp4,m4a,3gp,3g2,mj2"; show the file's actual container. */
export function formatContainer(format: string | null | undefined, filename?: string | null): string {
  if (!format) return "—";
  const ext = filename?.split(".").pop()?.toLowerCase();
  if (format.startsWith("mov,mp4")) return ext === "mov" ? "QuickTime (MOV)" : ext === "m4v" ? "M4V" : "MP4";
  if (format.startsWith("matroska")) return ext === "webm" ? "WebM" : "Matroska (MKV)";
  if (format === "avi") return "AVI";
  return format.split(",")[0].toUpperCase();
}
