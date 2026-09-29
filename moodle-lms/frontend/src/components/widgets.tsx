import { Link } from "react-router-dom";
import { api } from "../api";
import { dateTime, relative, shortDateTime } from "../format";
import type { ActivityEvent, CoachSummary, CourseCard, DeadlineItem, NotificationItem } from "../types";
import { useApi } from "../useApi";
import Icon from "./Icon";
import { AssignmentPill, EmptyState, ErrorState, Pill, ProgressBar, QuizPill, RiskBadge, Skeleton } from "./ui";

const COURSE_COLORS = ["#2a6f97", "#6a4c93", "#1b998b", "#c05746", "#3d5a80", "#8a5a44", "#2d6a4f", "#9c6644"];

export function courseColor(code?: string | null) {
  let h = 0;
  for (const ch of code || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COURSE_COLORS[h % COURSE_COLORS.length];
}

export function CourseTile({ course }: { course: CourseCard }) {
  const next = course.next_activity;
  const last = course.last_activity;
  return (
    <Link to={`/courses/${course.id}`} className="course-tile">
      <div className="course-banner" style={{ background: courseColor(course.code) }}>
        <span className="course-code">{course.code}</span>
        {course.term && <span className="course-term">{course.term}</span>}
      </div>
      <div className="course-tile-body">
        <h3>{course.title}</h3>
        <p className="muted small">{course.instructors.length ? course.instructors.join(", ") : "Instructor not listed"}</p>
        <ProgressBar value={course.progress} label="Course progress" size="sm" />
        <p className="small">
          {course.completed ? <Pill tone="success">Completed</Pill>
            : course.completion_enabled
              ? <span className="muted">{course.completed_activities} of {course.tracked_activities} activities complete</span>
              : <span className="muted">Completion not tracked</span>}
        </p>
        <dl className="tile-meta">
          <div>
            <dt>Upcoming</dt>
            <dd>{next ? <>{next.name} · <span className={next.state === "overdue" ? "text-danger" : ""}>
              {next.state === "overdue" ? "overdue" : `due ${shortDateTime(next.due)}`}</span></> : "Nothing due"}</dd>
          </div>
          <div>
            <dt>Last activity</dt>
            <dd>{last ? <>{last.title}: {last.activity} · {relative(last.timestamp)}</> : "No activity yet"}</dd>
          </div>
        </dl>
      </div>
    </Link>
  );
}

export function DeadlineList({ items, empty = "Nothing due in the next few weeks." }: { items: DeadlineItem[]; empty?: string }) {
  if (!items.length) return <EmptyState title={empty} />;
  return (
    <ul className="list">
      {items.map((e) => (
        <li key={`${e.kind}-${e.cmid}`}>
          <Link to={e.link} className="list-row">
            <span className={`list-icon kind-${e.kind}`}><Icon name={e.kind === "quiz" ? "quiz" : "assignment"} /></span>
            <span className="list-main">
              <strong>{e.course_code} · {e.name}</strong>
              <span className="muted small">
                {e.kind === "quiz" ? "Closes" : "Due"} {dateTime(e.due)} · {relative(e.due)}
              </span>
            </span>
            {e.kind === "quiz" ? <QuizPill state={e.state} /> : <AssignmentPill state={e.state} />}
          </Link>
        </li>
      ))}
    </ul>
  );
}

const ACTIVITY_ICON: Record<string, string> = {
  assignment_submitted: "upload", assignment_overdue: "alert", quiz_completed: "quiz", quiz_started: "quiz",
  grade_received: "grades", course_accessed: "courses", activity_completed: "check",
};

export function ActivityList({ items }: { items: ActivityEvent[] }) {
  if (!items.length) return <EmptyState title="No learning activity recorded in Moodle yet." icon="activity" />;
  return (
    <ol className="timeline">
      {items.map((e, i) => {
        const body = (
          <>
            <span className={`timeline-dot type-${e.type}`}><Icon name={ACTIVITY_ICON[e.type] || "activity"} size={14} /></span>
            <span className="list-main">
              <strong>{e.title}</strong>
              <span className="small">{e.course_code} · {e.activity}</span>
              <span className="muted small">{dateTime(e.timestamp)}{e.status ? ` · ${e.status}` : ""}</span>
            </span>
          </>
        );
        return <li key={i}>{e.link ? <Link to={e.link} className="timeline-row">{body}</Link> : <div className="timeline-row">{body}</div>}</li>;
      })}
    </ol>
  );
}

const NOTE_ICON: Record<string, string> = {
  due_soon: "clock", overdue: "alert", submitted: "upload", grade_released: "grades", quiz_result: "quiz",
  announcement: "bell",
};

export function NotificationList({ items, onRead }: { items: NotificationItem[]; onRead?: (n: NotificationItem) => void }) {
  if (!items.length) return <EmptyState title="No notifications." icon="bell" />;
  return (
    <ul className="list">
      {items.map((n) => {
        const inner = (
          <>
            <span className={`list-icon note-${n.type}`}><Icon name={NOTE_ICON[n.type] || "bell"} /></span>
            <span className="list-main">
              <strong>{n.title}</strong>
              {n.body && <span className="small">{n.body}</span>}
              <span className="muted small">
                {n.source === "moodle" ? "Moodle notification" : "From your Moodle dates"} · {dateTime(n.timestamp)}
              </span>
            </span>
            {!n.read && <span className="unread-dot" aria-label="Unread" />}
          </>
        );
        return (
          <li key={n.id}>
            {n.link ? <Link to={n.link} className="list-row" onClick={() => onRead?.(n)}>{inner}</Link>
              : <div className="list-row" onClick={() => onRead?.(n)}>{inner}</div>}
          </li>
        );
      })}
    </ul>
  );
}

export async function markRead(n: NotificationItem) {
  if (n.source === "moodle" && n.moodle_id && !n.read) {
    await api(`/api/notifications/${n.moodle_id}/read`, { method: "POST" }).catch(() => undefined);
  }
}

export function CoachCard({ compact = false }: { compact?: boolean }) {
  const coach = useApi<CoachSummary>("/api/mycoach");
  return (
    <section className="card coach-card">
      <div className="card-head">
        <h2><Icon name="coach" /> My Coach</h2>
      </div>
      <div className="card-body">
        {coach.loading && !coach.data ? <Skeleton rows={2} /> : coach.error ? (
          <ErrorState error={coach.error} onRetry={coach.reload} />
        ) : coach.data && (
          <>
            {coach.data.available ? (
              <>
                <div className="coach-risk">
                  <span className="muted small">Academic Risk</span>
                  <RiskBadge level={coach.data.risk_level} />
                </div>
                <p className="small">
                  {coach.data.open_indicators
                    ? `${coach.data.open_indicators} open indicator${coach.data.open_indicators > 1 ? "s" : ""} from My Coach.`
                    : "No open indicators."}
                </p>
                {!compact && coach.data.indicators && coach.data.indicators.length > 0 && (
                  <ul className="coach-indicators">
                    {coach.data.indicators.map((i, k) => <li key={k}><Pill tone={i.severity === "HIGH" ? "danger" : "warning"}>{i.severity}</Pill> {i.title}</li>)}
                  </ul>
                )}
              </>
            ) : (
              <p className="small muted">{coach.data.message}</p>
            )}
            <a className="btn btn-primary btn-block" href={coach.data.portal_url} target="_blank" rel="noopener noreferrer">
              Open My Coach <Icon name="external" size={14} />
            </a>
          </>
        )}
      </div>
    </section>
  );
}
