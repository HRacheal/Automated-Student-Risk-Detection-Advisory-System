import { useState } from "react";
import { Card, Loaded, PageHeader, Skeleton } from "../components/ui";
import { ActivityList } from "../components/widgets";
import type { ActivityEvent } from "../types";
import { useApi } from "../useApi";

const TYPES: Record<string, string> = {
  "": "All activity", assignment_submitted: "Submissions", quiz_completed: "Quiz attempts", grade_received: "Grades",
  course_accessed: "Course access", assignment_overdue: "Overdue", activity_completed: "Completions",
};

export default function ActivityPage() {
  const state = useApi<{ activity: ActivityEvent[] }>("/api/activity");
  const [type, setType] = useState("");
  return (
    <div className="page">
      <PageHeader title="Recent Activity" subtitle="Your learning activity as recorded by Moodle" />
      <div className="toolbar">
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter activity">
          {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <Loaded state={state} skeleton={<Skeleton rows={8} />}>
        {(d) => <Card><ActivityList items={d.activity.filter((e) => !type || e.type === type || (type === "quiz_completed" && e.type === "quiz_started"))} /></Card>}
      </Loaded>
    </div>
  );
}
