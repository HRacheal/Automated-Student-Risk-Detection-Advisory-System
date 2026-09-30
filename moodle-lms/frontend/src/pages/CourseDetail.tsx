import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import Icon, { moduleIcon } from "../components/Icon";
import { AssignmentTable, GradeTable, ProgressDetail, QuizTable } from "../components/tables";
import { AssignmentPill, Card, EmptyState, Loaded, PageHeader, Pill, ProgressBar, QuizPill, Skeleton } from "../components/ui";
import { courseColor } from "../components/widgets";
import { api, apiUrl } from "../api";
import { dateOnly, dateTime } from "../format";
import type { CourseDetail, CourseGrades, Module } from "../types";
import { useApi } from "../useApi";

const TABS = ["content", "assignments", "quizzes", "grades", "progress"] as const;
type Tab = (typeof TABS)[number];

export default function CourseDetailPage() {
  const { courseId } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.includes(params.get("tab") as Tab) ? params.get("tab") : "content") as Tab;
  const state = useApi<CourseDetail>(`/api/courses/${courseId}`);
  const grades = useApi<CourseGrades>(tab === "grades" ? `/api/grades/${courseId}` : null);

  return (
    <div className="page">
      <Loaded state={state} skeleton={<><PageHeader title="Course" crumbs={[{ label: "My Courses", to: "/courses" }]} /><Skeleton rows={6} /></>}>
        {(c) => (
          <>
            <PageHeader crumbs={[{ label: "My Courses", to: "/courses" }, { label: c.code }]} title={<>{c.code} <span className="title-light">{c.title}</span></>} />
            <section className="course-hero" style={{ borderTopColor: courseColor(c.code) }}>
              <div className="course-hero-main">
                <p>{c.summary || "No course description in Moodle."}</p>
                <dl className="inline-dl">
                  <div><dt>Instructor</dt><dd>{c.instructors.join(", ") || "Not listed"}</dd></div>
                  {c.term && <div><dt>Term</dt><dd>{c.term}</dd></div>}
                  <div><dt>Dates</dt><dd>{dateOnly(c.start_date)} – {dateOnly(c.end_date)}</dd></div>
                  <div><dt>Last access</dt><dd>{dateTime(c.last_access)}</dd></div>
                </dl>
              </div>
              <div className="course-hero-progress">
                <span className="muted small">Course progress</span>
                <ProgressBar value={c.progress} label="Course progress" />
                <span className="small muted">{c.progress_detail.completed} of {c.progress_detail.tracked} activities complete</span>
              </div>
            </section>

            <div className="tabs" role="tablist">
              {TABS.map((t) => (
                <button key={t} role="tab" aria-selected={tab === t} className={`tab ${tab === t ? "active" : ""}`}
                        onClick={() => setParams(t === "content" ? {} : { tab: t }, { replace: true })}>
                  {t[0].toUpperCase() + t.slice(1)}
                  {t === "assignments" && <span className="tab-count">{c.assignments.length}</span>}
                  {t === "quizzes" && <span className="tab-count">{c.quizzes.length}</span>}
                </button>
              ))}
            </div>

            {tab === "content" && <CourseContent course={c} onChanged={state.reload} />}
            {tab === "assignments" && <Card pad={false}><AssignmentTable items={c.assignments} showCourse={false} /></Card>}
            {tab === "quizzes" && <Card pad={false}><QuizTable items={c.quizzes} showCourse={false} /></Card>}
            {tab === "grades" && (
              <Card pad={false}>
                <Loaded state={grades}>
                  {(g) => g.items.length ? <GradeTable grades={g} /> : <EmptyState title="No grade items in this course yet." icon="grades" />}
                </Loaded>
              </Card>
            )}
            {tab === "progress" && <Card><ProgressDetail p={c.progress_detail} /></Card>}
          </>
        )}
      </Loaded>
    </div>
  );
}

function CourseContent({ course, onChanged }: { course: CourseDetail; onChanged: () => void }) {
  const sections = course.sections.filter((s) => s.modules.length || s.summary || s.number === 0);
  if (!sections.some((s) => s.modules.length)) return <EmptyState title="This course has no learning activities yet." icon="courses" />;
  return (
    <div className="sections">
      {sections.map((s) => (
        <section key={s.id} className="section">
          <h2 className="section-title">{s.name}</h2>
          {s.summary && <p className="muted">{s.summary}</p>}
          {s.modules.length === 0 ? <p className="muted small">No activities in this section.</p> : (
            <ul className="modules">
              {s.modules.map((m) => <ModuleRow key={m.cmid} m={m} onChanged={onChanged} />)}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}

function ModuleRow({ m, onChanged }: { m: Module; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const to = m.module === "assign" ? `/assignments/${m.cmid}` : m.module === "quiz" ? `/quizzes/${m.cmid}` : null;
  const toggle = async () => {
    setBusy(true);
    try {
      await api(`/api/activities/${m.cmid}/completion`, { body: { completed: !m.completion.completed } });
      onChanged();
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="module">
      <span className={`module-icon mod-${m.module}`}><Icon name={moduleIcon(m.module)} /></span>
      <div className="module-main">
        <div className="module-title">
          {to ? <Link to={to} className="strong-link">{m.name}</Link>
            : m.files[0]?.url ? <a href={apiUrl(m.files[0].url)} className="strong-link" target="_blank" rel="noopener noreferrer">{m.name}</a>
            : <span className="strong">{m.name}</span>}
          <span className="muted small">{m.module_label?.replace(/s$/, "")}</span>
        </div>
        {m.description && <p className="small muted">{m.description}</p>}
        {m.dates.length > 0 && (
          <p className="small">{m.dates.map((d, i) => <span key={i} className="module-date">{d.label} {dateTime(d.timestamp)}</span>)}</p>
        )}
        {!to && m.moodle_url && m.files.length === 0 && (
          <a className="small" href={m.moodle_url} target="_blank" rel="noopener noreferrer">Open in Moodle <Icon name="external" size={12} /></a>
        )}
      </div>
      <div className="module-status">
        {m.assignment && <AssignmentPill state={m.assignment.state} late={m.assignment.late} />}
        {m.quiz && <QuizPill state={m.quiz.state} />}
        {m.completion.tracked && (m.completion.manual ? (
          <button className={`btn btn-sm ${m.completion.completed ? "btn-success" : "btn-secondary"}`} onClick={toggle} disabled={busy}>
            <Icon name="check" size={14} /> {m.completion.completed ? "Done" : "Mark as done"}
          </button>
        ) : m.completion.completed ? <Pill tone="success"><Icon name="check" size={12} /> Complete</Pill> : <Pill tone="muted">Not complete</Pill>)}
      </div>
    </li>
  );
}
