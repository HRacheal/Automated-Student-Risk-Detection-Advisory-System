import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { AssignmentTable } from "../components/tables";
import { Card, Loaded, PageHeader, Skeleton } from "../components/ui";
import type { AssignmentSummary } from "../types";
import { useApi } from "../useApi";

const FILTERS: { key: string; label: string; match: (a: AssignmentSummary) => boolean }[] = [
  { key: "todo", label: "To do", match: (a) => ["open", "draft", "overdue"].includes(a.state) },
  { key: "overdue", label: "Overdue", match: (a) => a.state === "overdue" },
  { key: "submitted", label: "Submitted", match: (a) => a.state === "submitted" },
  { key: "closed", label: "Missed", match: (a) => a.state === "closed" },
  { key: "all", label: "All", match: () => true },
];

export default function AssignmentsPage() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.find((f) => f.key === params.get("filter")) ?? FILTERS[0];
  const course = params.get("course") || "";
  const state = useApi<{ assignments: AssignmentSummary[] }>("/api/assignments");
  const courses = useMemo(() => [...new Set((state.data?.assignments ?? []).map((a) => a.course_code))].sort(), [state.data]);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next, { replace: true });
  };

  return (
    <div className="page">
      <PageHeader title="Assignments" subtitle="All assignments across your courses, with live submission status from Moodle" />
      <div className="toolbar">
        <div className="segmented" role="tablist">
          {FILTERS.map((f) => {
            const n = state.data?.assignments.filter((a) => f.match(a) && (!course || a.course_code === course)).length;
            return (
              <button key={f.key} role="tab" aria-selected={f.key === filter.key} className={f.key === filter.key ? "active" : ""}
                      onClick={() => set("filter", f.key === "todo" ? "" : f.key)}>
                {f.label}{n != null && <span className="tab-count">{n}</span>}
              </button>
            );
          })}
        </div>
        <select value={course} onChange={(e) => set("course", e.target.value)} aria-label="Filter by course">
          <option value="">All courses</option>
          {courses.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <Loaded state={state} skeleton={<Skeleton rows={6} />}>
        {(d) => (
          <Card pad={false}>
            <AssignmentTable items={d.assignments.filter((a) => filter.match(a) && (!course || a.course_code === course))} />
          </Card>
        )}
      </Loaded>
    </div>
  );
}
