import { Link } from "react-router-dom";
import { GradeTable } from "../components/tables";
import { Card, EmptyState, Loaded, PageHeader, ProgressBar, Skeleton } from "../components/ui";
import type { CourseGrades } from "../types";
import { useApi } from "../useApi";

export default function GradesPage() {
  const state = useApi<{ courses: CourseGrades[] }>("/api/grades");
  return (
    <div className="page">
      <PageHeader title="Grades" subtitle="Your grades as recorded in the Moodle gradebook. Items without a grade show as Pending." />
      <Loaded state={state} skeleton={<Skeleton rows={6} />}>
        {(d) => d.courses.length === 0 ? <EmptyState title="No courses with grades." icon="grades" /> : (
          <div className="stack">
            {[...d.courses].sort((a, b) => a.course_code.localeCompare(b.course_code)).map((g) => (
              <Card key={g.course_id} pad={false}
                title={<Link to={`/courses/${g.course_id}?tab=grades`}>{g.course_code} <span className="title-light">{g.course_title}</span></Link>}
                action={<div className="grade-head">
                  <span className="small muted">Course total</span>
                  <strong>{g.course_total?.percentage ?? "—"}</strong>
                </div>}>
                {g.items.length ? <GradeTable grades={g} /> : <div className="card-body"><EmptyState title="No grade items yet." icon="grades" /></div>}
                <div className="card-foot">
                  <span className="small muted">Course progress</span>
                  <ProgressBar value={g.progress} size="sm" label={`${g.course_code} progress`} />
                </div>
              </Card>
            ))}
          </div>
        )}
      </Loaded>
    </div>
  );
}
