import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ApiError } from "../api";
import type { ApiState } from "../useApi";
import Icon from "./Icon";

export function PageHeader({ title, subtitle, crumbs, actions }: {
  title: ReactNode; subtitle?: ReactNode; crumbs?: { label: string; to?: string }[]; actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      {crumbs && crumbs.length > 0 && (
        <nav className="crumbs" aria-label="Breadcrumb">
          {crumbs.map((c, i) => (
            <span key={i}>
              {c.to ? <Link to={c.to}>{c.label}</Link> : <span>{c.label}</span>}
              {i < crumbs.length - 1 && <span className="crumb-sep">/</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="page-header-row">
        <div>
          <h1>{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
    </header>
  );
}

export function Card({ title, action, children, className = "", pad = true }: {
  title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {action}
        </div>
      )}
      <div className={pad ? "card-body" : ""}>{children}</div>
    </section>
  );
}

export function Loading({ label = "Loading from Moodle…" }: { label?: string }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-wrap" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" />)}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error | string; onRetry?: () => void }) {
  const message = typeof error === "string" ? error : error.message;
  return (
    <div className="state state-error" role="alert">
      <Icon name="alert" size={22} />
      <div>
        <p className="state-title">{message}</p>
        {onRetry && <button className="btn btn-secondary btn-sm" onClick={onRetry}><Icon name="refresh" size={14} /> Try again</button>}
      </div>
    </div>
  );
}

export function EmptyState({ title, children, icon = "check" }: { title: string; children?: ReactNode; icon?: string }) {
  return (
    <div className="state state-empty">
      <Icon name={icon} size={22} />
      <div>
        <p className="state-title">{title}</p>
        {children && <div className="state-text">{children}</div>}
      </div>
    </div>
  );
}

/** Renders loading / error states for a useApi() result, then the children with the data. */
export function Loaded<T>({ state, children, skeleton }: {
  state: ApiState<T>; children: (data: T) => ReactNode; skeleton?: ReactNode;
}) {
  if (state.loading && !state.data) return <>{skeleton ?? <Loading />}</>;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (!state.data) return null;
  return <>{children(state.data)}</>;
}

export function ProgressBar({ value, label, size = "md" }: { value: number | null; label?: string; size?: "sm" | "md" }) {
  if (value == null) {
    return <div className="progress-na">{label ?? "Progress"}: not tracked in Moodle</div>;
  }
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className={`progress progress-${size}`}>
      <div className="progress-track" role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0}
           aria-valuemax={100} aria-label={label ?? "Progress"}>
        <div className="progress-fill" style={{ width: `${v}%` }} />
      </div>
      <span className="progress-value">{Math.round(v)}%</span>
    </div>
  );
}

const ASSIGN_STATE: Record<string, { label: string; tone: string }> = {
  submitted: { label: "Submitted", tone: "success" },
  draft: { label: "Draft - not submitted", tone: "warning" },
  open: { label: "Not submitted", tone: "info" },
  overdue: { label: "Overdue", tone: "danger" },
  closed: { label: "Closed - not submitted", tone: "muted-danger" },
  not_open: { label: "Not open yet", tone: "muted" },
};

const QUIZ_STATE: Record<string, { label: string; tone: string }> = {
  open: { label: "Open", tone: "info" },
  in_progress: { label: "In progress", tone: "warning" },
  attempted: { label: "Attempted", tone: "success" },
  completed: { label: "Completed", tone: "success" },
  closed: { label: "Closed - not attempted", tone: "muted-danger" },
  not_open: { label: "Not open yet", tone: "muted" },
};

export function Pill({ tone = "muted", children }: { tone?: string; children: ReactNode }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function AssignmentPill({ state, late }: { state: string; late?: boolean }) {
  const s = ASSIGN_STATE[state] ?? { label: state, tone: "muted" };
  return (
    <span className="pill-group">
      <Pill tone={s.tone}>{s.label}</Pill>
      {late && <Pill tone="warning">Late</Pill>}
    </span>
  );
}

export function QuizPill({ state }: { state: string }) {
  const s = QUIZ_STATE[state] ?? { label: state, tone: "muted" };
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

export function RiskBadge({ level }: { level?: string | null }) {
  if (!level) return <Pill tone="muted">Not available</Pill>;
  const tone = level === "HIGH" ? "danger" : level === "MODERATE" ? "warning" : "success";
  return <span className={`risk risk-${tone}`}>{level}</span>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
