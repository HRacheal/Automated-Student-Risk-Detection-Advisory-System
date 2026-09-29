import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import Icon from "../components/Icon";
import { initialAnswers, QuestionView, type Answers } from "../components/QuestionView";
import { Card, ErrorState, Loaded, PageHeader, Pill, Skeleton } from "../components/ui";
import { dateTime } from "../format";
import type { AttemptPage } from "../types";
import { useApi } from "../useApi";

interface Summary { questions: { slot: number; number: string | null; status: string; page: number; answered: boolean }[] }

export default function QuizAttemptPage() {
  const { attemptId } = useParams();
  const [params, setParams] = useSearchParams();
  const page = Math.max(0, Number(params.get("page") || 0));
  const showSummary = params.get("summary") === "1";
  const state = useApi<AttemptPage>(showSummary ? null : `/api/quiz-attempts/${attemptId}?page=${page}`);
  const summary = useApi<Summary>(showSummary ? `/api/quiz-attempts/${attemptId}/summary` : null);
  const navigate = useNavigate();
  const [answers, setAnswers] = useState<Answers>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ quiz: string; course: string; cmid: number; pages: number } | null>(null);

  useEffect(() => {
    if (state.data) {
      setAnswers(initialAnswers(state.data.questions));
      setMeta({ quiz: state.data.quiz_name, course: state.data.course_code, cmid: state.data.quiz_cmid, pages: state.data.pages });
      if (state.data.state === "finished") navigate(`/quizzes/${state.data.quiz_cmid}`, { replace: true });
    }
  }, [state.data, navigate]);

  const savePage = async () => {
    await api(`/api/quiz-attempts/${attemptId}`, { body: { page, answers, finish: false } });
  };

  const go = async (target: { page?: number; summary?: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      if (!showSummary) await savePage();
      setParams(target.summary ? { summary: "1" } : { page: String(target.page ?? 0) });
      window.scrollTo(0, 0);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Your answers could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    if (!window.confirm("Submit all your answers and finish this attempt?\n\nYou will not be able to change your answers after this.")) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/quiz-attempts/${attemptId}/finish`, { method: "POST" });
      navigate(meta ? `/quizzes/${meta.cmid}?submitted=1` : "/quizzes", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The attempt could not be submitted.");
      setBusy(false);
    }
  };

  const crumbs = [{ label: "Quizzes", to: "/quizzes" }, ...(meta ? [{ label: `${meta.course} · ${meta.quiz}`, to: `/quizzes/${meta.cmid}` }] : []), { label: "Attempt" }];

  if (showSummary) {
    return (
      <div className="page">
        <PageHeader crumbs={crumbs} title="Summary of attempt" subtitle={meta?.quiz} />
        <Loaded state={summary} skeleton={<Skeleton rows={4} />}>
          {(s) => (
            <Card>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Question</th><th>Status</th><th /></tr></thead>
                  <tbody>
                    {s.questions.map((q) => (
                      <tr key={q.slot}>
                        <td data-label="Question">{q.number ?? q.slot}</td>
                        <td data-label="Status"><Pill tone={q.answered ? "success" : "warning"}>{q.status}</Pill></td>
                        <td><button className="btn btn-ghost btn-sm" onClick={() => setParams({ page: String(q.page) })}>Change answer</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {error && <ErrorState error={error} />}
              <div className="btn-row">
                <button className="btn btn-secondary" onClick={() => setParams({ page: "0" })} disabled={busy}>Return to attempt</button>
                <button className="btn btn-primary" onClick={finish} disabled={busy}>{busy ? "Submitting…" : "Submit all and finish"}</button>
              </div>
            </Card>
          )}
        </Loaded>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader crumbs={crumbs} title={meta?.quiz ?? "Quiz attempt"}
        subtitle={state.data ? <>Page {page + 1} of {state.data.pages} · started {dateTime(state.data.started)}</> : undefined} />
      <Loaded state={state} skeleton={<Skeleton rows={6} />}>
        {(d) => (
          <>
            {d.messages.length > 0 && <div className="banner banner-muted">{d.messages.map((m, i) => <p key={i}>{m}</p>)}</div>}
            <div className="questions">
              {d.questions.map((q) => (
                <Card key={q.slot}>
                  <QuestionView q={q} answers={answers} onChange={(name, value) => setAnswers((a) => ({ ...a, [name]: value }))} />
                </Card>
              ))}
            </div>
            {error && <ErrorState error={error} />}
            <div className="btn-row attempt-nav">
              {page > 0 && <button className="btn btn-secondary" onClick={() => go({ page: page - 1 })} disabled={busy}><Icon name="chevronLeft" size={16} /> Previous page</button>}
              <span className="spacer" />
              {d.next_page >= 0
                ? <button className="btn btn-primary" onClick={() => go({ page: d.next_page })} disabled={busy}>Next page <Icon name="chevronRight" size={16} /></button>
                : <button className="btn btn-primary" onClick={() => go({ summary: true })} disabled={busy}>{busy ? "Saving…" : "Finish attempt…"}</button>}
            </div>
            <p className="muted small">Answers are saved to Moodle when you change page. <Link to={`/quizzes/${d.quiz_cmid}`}>Back to quiz</Link></p>
          </>
        )}
      </Loaded>
    </div>
  );
}
