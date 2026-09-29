import type { Question } from "../types";
import { Pill } from "./ui";

export type Answers = Record<string, string>;

export function initialAnswers(questions: Question[]): Answers {
  const a: Answers = {};
  for (const q of questions) {
    for (const f of q.fields) {
      if (f.kind === "radio") { if (f.value != null) a[f.name] = f.value; }
      else if (f.kind === "checkbox") a[f.name] = f.checked ? f.value : "0";
      else a[f.name] = f.value ?? "";
    }
  }
  return a;
}

function stateTone(stateClass: string | null) {
  if (!stateClass) return "muted";
  if (stateClass.includes("incorrect")) return "danger";
  if (stateClass.includes("partial")) return "warning";
  if (stateClass.includes("correct")) return "success";
  if (stateClass.includes("answersaved") || stateClass.includes("complete")) return "info";
  return "muted";
}

/** Renders one Moodle question from structured data (never Moodle HTML). */
export function QuestionView({ q, answers, onChange, review = false, moodleUrl }: {
  q: Question; answers: Answers; onChange?: (name: string, value: string) => void; review?: boolean; moodleUrl?: string;
}) {
  const disabled = review || q.readonly || !onChange;
  return (
    <article className="question" aria-labelledby={`q-${q.slot}`}>
      <header className="question-head">
        <h3 id={`q-${q.slot}`}>Question {q.number ?? q.slot}</h3>
        <span className="question-meta">
          {q.status && <Pill tone={review ? stateTone(q.state_class) : "muted"}>{q.status}</Pill>}
          {review && q.mark != null && q.max_mark != null && <span className="muted small">Mark {q.mark} / {q.max_mark}</span>}
          {!review && q.max_mark != null && <span className="muted small">Marked out of {q.max_mark}</span>}
        </span>
      </header>
      <p className="question-text prewrap">{q.text}</p>
      {!q.supported ? (
        <p className="banner banner-muted">This question type cannot be answered here.{" "}
          {moodleUrl && <a href={moodleUrl} target="_blank" rel="noopener noreferrer">Open the quiz in Moodle</a>}</p>
      ) : (
        <fieldset className="answers" disabled={disabled}>
          <legend className="sr-only">Answer for question {q.number ?? q.slot}</legend>
          {q.fields.map((f) => {
            if (f.kind === "radio") {
              return f.options.map((o) => (
                <label key={`${f.name}-${o.value}`} className={`choice ${answers[f.name] === o.value ? "selected" : ""}`}>
                  <input type="radio" name={f.name} value={o.value} checked={answers[f.name] === o.value}
                         onChange={() => onChange?.(f.name, o.value)} />
                  <span>{o.value === "-1" ? "Clear my choice" : o.label}</span>
                </label>
              ));
            }
            if (f.kind === "checkbox") {
              return (
                <label key={f.name} className={`choice ${answers[f.name] === f.value ? "selected" : ""}`}>
                  <input type="checkbox" name={f.name} checked={answers[f.name] === f.value}
                         onChange={(e) => onChange?.(f.name, e.target.checked ? f.value : "0")} />
                  <span>{f.label}</span>
                </label>
              );
            }
            if (f.kind === "select") {
              return (
                <label key={f.name} className="text-answer">
                  <span className="small muted">{f.label}</span>
                  <select value={answers[f.name] ?? ""} onChange={(e) => onChange?.(f.name, e.target.value)}>
                    {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>
              );
            }
            return (
              <label key={f.name} className="text-answer">
                <span className="small muted">Answer</span>
                {f.kind === "textarea"
                  ? <textarea rows={6} value={answers[f.name] ?? ""} onChange={(e) => onChange?.(f.name, e.target.value)} />
                  : <input value={answers[f.name] ?? ""} onChange={(e) => onChange?.(f.name, e.target.value)} />}
              </label>
            );
          })}
        </fieldset>
      )}
      {review && (q.feedback.specific || q.feedback.general || q.feedback.right_answer) && (
        <div className="feedback">
          {q.feedback.specific && <p>{q.feedback.specific}</p>}
          {q.feedback.general && <p>{q.feedback.general}</p>}
          {q.feedback.right_answer && <p className="strong">{q.feedback.right_answer}</p>}
        </div>
      )}
    </article>
  );
}
