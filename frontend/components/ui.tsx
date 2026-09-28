import type { ReactNode } from "react";
import type { AlertStatus, Risk } from "@/lib/types";

export const RISK_META: Record<Risk, { icon: string; label: string; badge: string; dot: string; text: string; ring: string }> = {
  HIGH: {
    icon: "🔴",
    label: "High",
    badge: "bg-red-50 text-red-700 ring-red-200",
    dot: "bg-red-500",
    text: "text-red-700",
    ring: "border-l-red-500",
  },
  MODERATE: {
    icon: "🟡",
    label: "Moderate",
    badge: "bg-amber-50 text-amber-800 ring-amber-200",
    dot: "bg-amber-400",
    text: "text-amber-700",
    ring: "border-l-amber-400",
  },
  LOW: {
    icon: "🟢",
    label: "Low",
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    dot: "bg-emerald-500",
    text: "text-emerald-700",
    ring: "border-l-emerald-500",
  },
};

export function RiskBadge({ level, size = "sm" }: { level: Risk | null | undefined; size?: "sm" | "lg" }) {
  const m = RISK_META[(level || "LOW") as Risk];
  const cls = size === "lg" ? "px-3 py-1.5 text-sm" : "px-2 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ring-1 ring-inset ${m.badge} ${cls}`}>
      <span aria-hidden>{m.icon}</span>
      {m.label.toUpperCase()}
    </span>
  );
}

const STATUS_STYLE: Record<string, string> = {
  active: "bg-red-50 text-red-700 ring-red-200",
  acknowledged: "bg-blue-50 text-blue-700 ring-blue-200",
  resolved: "bg-slate-100 text-slate-600 ring-slate-200",
  auto_resolved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  planned: "bg-slate-100 text-slate-700 ring-slate-200",
  in_progress: "bg-blue-50 text-blue-700 ring-blue-200",
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  ok: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  completed_run: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  partial: "bg-amber-50 text-amber-800 ring-amber-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
  error: "bg-red-50 text-red-700 ring-red-200",
  unavailable: "bg-slate-100 text-slate-600 ring-slate-300",
  not_configured: "bg-slate-100 text-slate-600 ring-slate-300",
  disabled: "bg-slate-100 text-slate-600 ring-slate-300",
  running: "bg-blue-50 text-blue-700 ring-blue-200",
};

export function StatusBadge({ status }: { status: AlertStatus | string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        STATUS_STYLE[status] || "bg-slate-100 text-slate-700 ring-slate-200"
      }`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

const SOURCE_STYLE: Record<string, string> = {
  rosario: "bg-sky-50 text-sky-700 ring-sky-200",
  moodle: "bg-orange-50 text-orange-700 ring-orange-200",
  demo: "bg-violet-50 text-violet-700 ring-violet-200",
};
const SOURCE_LABEL: Record<string, string> = { rosario: "RosarioSIS", moodle: "Moodle", demo: "DEMO data" };

export function SourceBadge({ source }: { source: string }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset ${
        SOURCE_STYLE[source] || "bg-slate-50 text-slate-600 ring-slate-200"
      }`}
    >
      {SOURCE_LABEL[source] || source}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>{children}</div>;
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
      <Spinner /> {label}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
      {message}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {children && <div className="mt-1 text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { dateStyle: "medium" });
}

export function timeAgo(value: string | null | undefined) {
  if (!value) return "never";
  const diff = Date.now() - new Date(value).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} h ago`;
  return `${Math.round(hrs / 24)} d ago`;
}

export const inputCls =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-700/20";

export const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-brand-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-60";

export const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60";
