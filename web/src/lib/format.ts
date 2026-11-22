/** Small display helpers. Pure functions: easy to test, no React. */

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "just now", "5 minutes ago", "yesterday", ... */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((Date.parse(iso) - now) / 1000);
  if (Math.abs(seconds) < 45) return "just now";
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size || unit === "minute") {
      return relative.format(Math.round(seconds / size), unit);
    }
  }
  return "just now";
}

/** 83 -> "1:23", 3725 -> "1:02:05" */
export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = String(s % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}`
    : `${minutes}:${seconds}`;
}

/** 43.46 -> "43s", 75 -> "1m 15s" */
export function length(totalSeconds: number): string {
  const s = Math.round(totalSeconds);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

/** Elapsed time between two moments, e.g. "2m 05s" */
export function elapsed(fromIso: string, toMs: number = Date.now()): string {
  return length(Math.max(0, (toMs - Date.parse(fromIso)) / 1000));
}

/** A URL shortened for display: "youtube.com/watch?v=R6Ml…" */
export function shortUrl(url: string, max = 48): string {
  let text = url;
  try {
    const u = new URL(url);
    text = u.host.replace(/^www\./, "") + u.pathname.replace(/\/$/, "") + u.search;
  } catch {
    // not a URL: show as given
  }
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Is this an http(s) URL the API will accept (syntax only: the API checks the rest)? */
export function isWebUrl(value: string): boolean {
  try {
    const u = new URL(value.trim());
    return (u.protocol === "http:" || u.protocol === "https:") && u.host !== "";
  } catch {
    return false;
  }
}

/** Split a clip's `reason` ("AI 8/10 ...; 5 reactions (...); 3.2 dB louder") into items. */
export function reasonParts(reason: string | null | undefined): string[] {
  return (reason ?? "")
    .split("; ")
    .map((part) => part.trim())
    .filter(Boolean);
}
