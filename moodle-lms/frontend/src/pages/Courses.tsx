import { useMemo, useState } from "react";
import Icon from "../components/Icon";
import { EmptyState, Loaded, PageHeader, Skeleton } from "../components/ui";
import { CourseTile } from "../components/widgets";
import type { Dashboard } from "../types";
import { useApi } from "../useApi";

export default function CoursesPage() {
  // The dashboard payload carries each course's progress, next and last activity.
  const state = useApi<Dashboard>("/api/dashboard");
  const [q, setQ] = useState("");
  const courses = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (state.data?.courses ?? []).filter((c) =>
      !needle || c.code.toLowerCase().includes(needle) || c.title.toLowerCase().includes(needle));
  }, [state.data, q]);

  return (
    <div className="page">
      <PageHeader title="My Courses" subtitle="Courses you are enrolled in on Moodle"
        actions={
          <label className="search">
            <Icon name="search" size={16} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search courses" aria-label="Search courses" />
          </label>
        } />
      <Loaded state={state} skeleton={<Skeleton rows={4} />}>
        {() => courses.length === 0
          ? <EmptyState title={q ? "No course matches your search." : "You are not enrolled in any Moodle course."} icon="courses" />
          : <div className="course-grid course-grid-lg">{courses.map((c) => <CourseTile key={c.id} course={c} />)}</div>}
      </Loaded>
    </div>
  );
}
