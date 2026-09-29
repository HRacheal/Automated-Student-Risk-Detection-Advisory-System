import { useSearchParams } from "react-router-dom";
import { QuizTable } from "../components/tables";
import { Card, Loaded, PageHeader, Skeleton } from "../components/ui";
import type { QuizSummary } from "../types";
import { useApi } from "../useApi";

const FILTERS: { key: string; label: string; match: (q: QuizSummary) => boolean }[] = [
  { key: "available", label: "Available", match: (q) => ["open", "in_progress", "not_open"].includes(q.state) },
  { key: "done", label: "Completed", match: (q) => ["attempted", "completed"].includes(q.state) },
  { key: "missed", label: "Closed", match: (q) => q.state === "closed" },
  { key: "all", label: "All", match: () => true },
];

export default function QuizzesPage() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.find((f) => f.key === params.get("filter")) ?? FILTERS[0];
  const state = useApi<{ quizzes: QuizSummary[] }>("/api/quizzes");
  return (
    <div className="page">
      <PageHeader title="Quizzes" subtitle="Quizzes in your courses, with your attempts and results from Moodle" />
      <div className="toolbar">
        <div className="segmented" role="tablist">
          {FILTERS.map((f) => (
            <button key={f.key} role="tab" aria-selected={f.key === filter.key} className={f.key === filter.key ? "active" : ""}
                    onClick={() => setParams(f.key === "available" ? {} : { filter: f.key }, { replace: true })}>
              {f.label}{state.data && <span className="tab-count">{state.data.quizzes.filter(f.match).length}</span>}
            </button>
          ))}
        </div>
      </div>
      <Loaded state={state} skeleton={<Skeleton rows={6} />}>
        {(d) => <Card pad={false}><QuizTable items={d.quizzes.filter(filter.match)} /></Card>}
      </Loaded>
    </div>
  );
}
