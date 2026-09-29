// Dates are shown in the Moodle site's timezone (sent by the backend), not the browser's.
let zone = "Africa/Nairobi";

export function setTimeZone(tz: string) {
  zone = tz || zone;
}

export function getTimeZone() {
  return zone;
}

const cache = new Map<string, Intl.DateTimeFormat>();
function fmt(key: string, opts: Intl.DateTimeFormatOptions) {
  const k = `${zone}|${key}`;
  let f = cache.get(k);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", { timeZone: zone, ...opts });
    cache.set(k, f);
  }
  return f;
}

export function dateTime(ts?: number | null) {
  if (!ts) return "—";
  return fmt("dt", { month: "long", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .format(new Date(ts * 1000));
}

export function shortDateTime(ts?: number | null) {
  if (!ts) return "—";
  return fmt("sdt", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .format(new Date(ts * 1000));
}

export function dateOnly(ts?: number | null) {
  if (!ts) return "—";
  return fmt("d", { month: "long", day: "numeric", year: "numeric" }).format(new Date(ts * 1000));
}

export function timeOnly(ts?: number | null) {
  if (!ts) return "";
  return fmt("t", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(ts * 1000));
}

/** Calendar parts of a timestamp in the site timezone. */
export function zonedParts(ts: number) {
  const parts = fmt("parts", { year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(ts * 1000));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  return { year: get("year"), month: get("month"), day: get("day") };
}

export function relative(ts?: number | null) {
  if (!ts) return "";
  const diff = ts - Date.now() / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 45) return rtf.format(Math.round(diff / 86400), "day");
  return rtf.format(Math.round(diff / (86400 * 30)), "month");
}

export function duration(seconds?: number | null) {
  if (!seconds) return "";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return [d && `${d} day${d > 1 ? "s" : ""}`, h && `${h} hour${h > 1 ? "s" : ""}`, !d && m && `${m} min`]
    .filter(Boolean).join(" ") || "under a minute";
}

export function fileSize(bytes?: number | null) {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function pct(value?: number | null) {
  return value == null ? "—" : `${Math.round(value)}%`;
}
