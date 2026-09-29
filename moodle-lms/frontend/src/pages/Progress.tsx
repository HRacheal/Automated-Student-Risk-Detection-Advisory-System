import { Link } from "react-router-dom";
import { ProgressDetail } from "../components/tables";
import { Card, EmptyState, Loaded, PageHeader, Skeleton } from "../components/ui";
import type { CourseProgress } from "../types";
import { useApi } from "../useApi";

export default function ProgressPage() {
  const state = useApi<{ courses: CourseProgress[] }>("/api/progress");
  return (
    <div className="page">
      <PageHeader title="Progress" subtitle="Activity completion tracked by Moodle for each of your courses (remaining activities listed)" />
      <Loaded state={state} skeleton={<Skeleton rows={6} />}>
        {(d) => d.courses.length === 0 ? <EmptyState title="No courses." icon="progress" /> : (
          <div className="progress-grid">
            {[...d.courses].sort((a, b) => a.course_code.localeCompare(b.course_code)).map((p) => (
              <Card key={p.course_id} title={<Link to={`/courses/${p.course_id}?tab=progress`}>{p.course_code} <span className="title-light">{p.course_title}</span></Link>}>
                <ProgressDetail p={p} showRemainingOnly />
              </Card>
            ))}
          </div>
        )}
      </Loaded>
    </div>
  );
}
