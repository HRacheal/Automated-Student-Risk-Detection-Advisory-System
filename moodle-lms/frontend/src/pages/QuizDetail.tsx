import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import Icon from "../components/Icon";
import { Card, EmptyState, ErrorState, Field, Loaded, PageHeader, Pill, QuizPill, Skeleton } from "../components/ui";
import { dateTime, duration, relative } from "../format";
import type { QuizDetail } from "../types";
import { useApi } from "../useApi";

export default function QuizDetailPage() {
  const { cmid } = useParams();
  const state = useApi<QuizDetail>(`/api/quizzes/${cmid}`);
  return (
    <div className="page">
      <Loaded state={state} skeleton={<><PageHeader title="Quiz" crumbs={[{ label: "Quizzes", to: "/quizzes" }]} /><Skeleton rows={6} /></>}>
        {(q) => <QuizView q={q} />}
      </Loaded>
    </div>
  );
}

function QuizView({ q }: { q: QuizDetail }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blocked = [...q.prevent_access, ...q.prevent_new_attempt];
  const canStart = q.can_attempt && !q.in_progress_attempt && blocked.length === 0 && q.state !== "closed" && q.state !== "not_open";

  const start = async () => {
    if (!q.in_progress_attempt) {
      const left = q.attempts_allowed ? q.attempts_allowed - q.attempts_used : null;
      const msg = `Start "${q.name}" now?` + (left != null ? `\n\nYou have ${left} attempt${left === 1 ? "" : "s"} remaining.` : "")
        + (q.time_limit ? `\nTime limit: ${duration(q.time_limit)}.` : "");
      if (!window.confirm(msg)) return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ attempt_id: number }>(`/api/quizzes/${q.cmid}/start`, { method: "POST" });
      navigate(`/quiz-attempts/${r.attempt_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the quiz.");
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        crumbs={[{ label: "My Courses", to: "/courses" }, { label: q.course_code, to: `/courses/${q.course_id}` },
                 { label: "Quizzes", to: `/courses/${q.course_id}?tab=quizzes` }, { label: q.name }]}
        title={q.name}
        subtitle={<>{q.course_code} · {q.course_title}</>}
      />
      <div className="detail-grid">
        <div className="detail-main">
          <Card title="Quiz information">
            <dl className="fields">
              <Field label="Opens">{dateTime(q.opens)}</Field>
              <Field label="Closes">{dateTime(q.closes)} {q.closes && <span className="muted">({relative(q.closes)})</span>}</Field>
              <Field label="Time limit">{q.time_limit ? duration(q.time_limit) : "No time limit"}</Field>
              <Field label="Attempts allowed">{q.attempts_allowed ?? "Unlimited"}</Field>
              {q.grade_method && <Field label="Grading method">{q.grade_method}</Field>}
              <Field label="Maximum grade">{q.max_grade ?? "—"}</Field>
            </dl>
            <h3 className="subhead">Instructions</h3>
            <p className="prewrap">{q.description || <span className="muted">No instructions provided in Moodle.</span>}</p>
            {q.rules.length > 0 && (
              <ul className="rules">{q.rules.map((r, i) => <li key={i}><Icon name="check" size={14} /> {r}</li>)}</ul>
            )}
          </Card>

          <Card title="Your attempts" pad={false}>
            {q.attempts.length === 0 ? <div className="card-body"><EmptyState title="You have not attempted this quiz." icon="quiz" /></div> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Attempt</th><th>Status</th><th>Started</th><th>Submitted</th><th>Grade</th><th /></tr></thead>
                  <tbody>
                    {q.attempts.map((t) => (
                      <tr key={t.id}>
                        <td data-label="Attempt">{t.number}</td>
                        <td data-label="Status">{t.state === "finished" ? <Pill tone="success">Finished</Pill> : t.state === "inprogress" ? <Pill tone="warning">In progress</Pill> : <Pill tone="muted">{t.state}</Pill>}</td>
                        <td data-label="Started">{dateTime(t.started)}</td>
                        <td data-label="Submitted">{dateTime(t.finished)}</td>
                        <td data-label="Grade">{t.grade != null ? `${t.grade} / ${q.max_grade}` : <span className="muted">Not available</span>}</td>
                        <td>
                          {t.state === "finished" && q.can_review && <Link className="btn btn-secondary btn-sm" to={`/quiz-attempts/${t.id}/review`}>Review</Link>}
                          {t.state === "inprogress" && <Link className="btn btn-primary btn-sm" to={`/quiz-attempts/${t.id}`}>Continue</Link>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <aside className="detail-side">
          <Card title="Status" className="status-card">
            <div className="status-big"><QuizPill state={q.state} /></div>
            <dl className="fields">
              <Field label="Attempts used">{q.attempts_used}{q.attempts_allowed ? ` of ${q.attempts_allowed}` : ""}</Field>
              <Field label="Your grade">{q.grade != null ? <strong>{q.grade} / {q.max_grade}</strong> : <span className="muted">Not available</span>}</Field>
              {q.overall_feedback && <Field label="Feedback">{q.overall_feedback}</Field>}
            </dl>
            {blocked.length > 0 && !q.in_progress_attempt && (
              <div className="banner banner-muted">{blocked.map((b, i) => <p key={i}>{b}</p>)}</div>
            )}
            {error && <ErrorState error={error} />}
            {q.in_progress_attempt ? (
              <Link className="btn btn-primary btn-block" to={`/quiz-attempts/${q.in_progress_attempt}`}>Continue attempt</Link>
            ) : canStart ? (
              <button className="btn btn-primary btn-block" onClick={start} disabled={busy}>{busy ? "Starting…" : q.attempts_used ? "Re-attempt quiz" : "Start attempt"}</button>
            ) : null}
          </Card>
        </aside>
      </div>
    </>
  );
}
