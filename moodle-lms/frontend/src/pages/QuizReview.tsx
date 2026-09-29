import { useMemo } from "react";
import { useParams } from "react-router-dom";
import { initialAnswers, QuestionView } from "../components/QuestionView";
import { Card, Field, Loaded, PageHeader, Skeleton } from "../components/ui";
import { dateTime } from "../format";
import type { AttemptReview } from "../types";
import { useApi } from "../useApi";

export default function QuizReviewPage() {
  const { attemptId } = useParams();
  const state = useApi<AttemptReview>(`/api/quiz-attempts/${attemptId}/review`);
  const answers = useMemo(() => initialAnswers(state.data?.questions ?? []), [state.data]);
  return (
    <div className="page">
      <Loaded state={state} skeleton={<><PageHeader title="Attempt review" /><Skeleton rows={6} /></>}>
        {(r) => (
          <>
            <PageHeader title={`Review: ${r.quiz_name}`} subtitle={r.course_code}
              crumbs={[{ label: "Quizzes", to: "/quizzes" }, { label: `${r.course_code} · ${r.quiz_name}`, to: `/quizzes/${r.quiz_cmid}` }, { label: "Review" }]} />
            <Card>
              <dl className="fields fields-inline">
                <Field label="Started">{dateTime(r.started)}</Field>
                <Field label="Completed">{dateTime(r.finished)}</Field>
                <Field label="Grade">{r.grade != null ? `${r.grade} / ${r.max_grade}` : "Not available (hidden by the quiz settings)"}</Field>
                {r.additional.filter((a) => a.title && a.content && !/grade|started|completed/i.test(a.title)).map((a, i) => (
                  <Field key={i} label={a.title}>{a.content}</Field>
                ))}
              </dl>
            </Card>
            <div className="questions">
              {r.questions.map((q) => <Card key={q.slot}><QuestionView q={q} answers={answers} review /></Card>)}
            </div>
          </>
        )}
      </Loaded>
    </div>
  );
}
