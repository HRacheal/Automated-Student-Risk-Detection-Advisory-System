import { Link } from "react-router-dom";
import { dateTime, pct, shortDateTime } from "../format";
import type { AssignmentSummary, CourseGrades, CourseProgress, QuizSummary } from "../types";
import Icon, { moduleIcon } from "./Icon";
import { AssignmentPill, EmptyState, Pill, ProgressBar, QuizPill } from "./ui";

export function AssignmentTable({ items, showCourse = true }: { items: AssignmentSummary[]; showCourse?: boolean }) {
  if (!items.length) return <EmptyState title="No assignments here." icon="assignment" />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Assignment</th>
            {showCourse && <th>Course</th>}
            <th>Due</th>
            <th>Status</th>
            <th>Grade</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.cmid}>
              <td data-label="Assignment"><Link to={`/assignments/${a.cmid}`} className="strong-link">{a.name}</Link></td>
              {showCourse && <td data-label="Course">{a.course_code}</td>}
              <td data-label="Due">{dateTime(a.extension_due_date || a.due_date)}</td>
              <td data-label="Status">
                <AssignmentPill state={a.state} late={a.late} />
                {a.submitted_at && <div className="muted small">Submitted {shortDateTime(a.submitted_at)}</div>}
              </td>
              <td data-label="Grade">{a.grade ?? <span className="muted">{a.submitted_at ? "Pending" : "—"}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function QuizTable({ items, showCourse = true }: { items: QuizSummary[]; showCourse?: boolean }) {
  if (!items.length) return <EmptyState title="No quizzes here." icon="quiz" />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Quiz</th>
            {showCourse && <th>Course</th>}
            <th>Opens</th>
            <th>Closes</th>
            <th>Status</th>
            <th>Grade</th>
          </tr>
        </thead>
        <tbody>
          {items.map((q) => (
            <tr key={q.cmid}>
              <td data-label="Quiz"><Link to={`/quizzes/${q.cmid}`} className="strong-link">{q.name}</Link></td>
              {showCourse && <td data-label="Course">{q.course_code}</td>}
              <td data-label="Opens">{dateTime(q.opens)}</td>
              <td data-label="Closes">{dateTime(q.closes)}</td>
              <td data-label="Status"><QuizPill state={q.state} /></td>
              <td data-label="Grade">{q.grade != null ? `${q.grade} / ${q.max_grade}` : <span className="muted">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GradeTable({ grades }: { grades: CourseGrades }) {
  const link = (module: string | null, cmid: number | null) =>
    module === "assign" && cmid ? `/assignments/${cmid}` : module === "quiz" && cmid ? `/quizzes/${cmid}` : null;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr><th>Grade item</th><th>Grade</th><th>Range</th><th>Percentage</th><th>Feedback</th></tr>
        </thead>
        <tbody>
          {grades.items.map((g) => {
            const to = link(g.module, g.cmid);
            return (
              <tr key={g.id}>
                <td data-label="Grade item">
                  <span className="inline-icon"><Icon name={moduleIcon(g.module)} size={14} /></span>
                  {to ? <Link to={to} className="strong-link">{g.name}</Link> : g.name}
                </td>
                <td data-label="Grade">{g.hidden ? <Pill tone="muted">Hidden</Pill> : g.grade != null ? g.grade_formatted : <span className="muted">Pending</span>}</td>
                <td data-label="Range">{g.range ?? "—"}</td>
                <td data-label="Percentage">{g.percentage ?? "—"}</td>
                <td data-label="Feedback">{g.feedback || <span className="muted">—</span>}</td>
              </tr>
            );
          })}
        </tbody>
        {grades.course_total && (
          <tfoot>
            <tr>
              <th>Course total</th>
              <th>{grades.course_total.grade != null ? grades.course_total.grade_formatted : "—"}</th>
              <th>{grades.course_total.range ?? "—"}</th>
              <th>{grades.course_total.percentage ?? "—"}</th>
              <th />
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

const TYPE_LABEL: Record<string, string> = { assign: "Assignments", quiz: "Quizzes", resource: "Resources", page: "Pages", url: "Links", forum: "Forums" };

export function ProgressDetail({ p, showRemainingOnly = false }: { p: CourseProgress; showRemainingOnly?: boolean }) {
  if (!p.completion_enabled) return <EmptyState title="Moodle completion tracking is not enabled for this course." icon="progress" />;
  const list = showRemainingOnly ? p.activities.filter((a) => a.tracked && !a.completed) : p.activities;
  return (
    <div className="progress-detail">
      <ProgressBar value={p.percentage} label={`${p.course_code} progress`} />
      <div className="progress-stats">
        <div><strong>{p.completed}</strong><span>Completed</span></div>
        <div><strong>{p.remaining}</strong><span>Remaining</span></div>
        {Object.entries(p.by_type).map(([t, v]) => (
          <div key={t}><strong>{v.completed}/{v.total}</strong><span>{TYPE_LABEL[t] ?? t}</span></div>
        ))}
        <div><strong>{p.last_access ? shortDateTime(p.last_access) : "Never"}</strong><span>Last access</span></div>
      </div>
      {list.length === 0 ? <EmptyState title="All tracked activities are complete." /> : (
        <ul className="list compact">
          {list.map((a) => (
            <li key={a.cmid} className="list-row static">
              <span className={`list-icon ${a.completed ? "done" : ""}`}><Icon name={a.completed ? "check" : moduleIcon(a.module)} /></span>
              <span className="list-main">
                <strong>{a.name}</strong>
                <span className="muted small">{a.section}{a.rules.length ? ` · ${a.rules.join(", ")}` : ""}</span>
              </span>
              {!a.tracked ? <Pill tone="muted">Not tracked</Pill> : a.completed
                ? <Pill tone="success">Done {a.completed_at ? shortDateTime(a.completed_at) : ""}</Pill>
                : <Pill tone="info">To do</Pill>}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">Percentage calculated by Moodle ({pct(p.percentage)}).</p>
    </div>
  );
}
