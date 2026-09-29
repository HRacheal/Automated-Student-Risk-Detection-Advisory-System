import { useRef, useState, type ChangeEvent } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import Icon from "../components/Icon";
import { AssignmentPill, Card, ErrorState, Field, Loaded, PageHeader, Pill, Skeleton } from "../components/ui";
import { dateTime, duration, fileSize, relative } from "../format";
import type { AssignmentDetail } from "../types";
import { useApi } from "../useApi";

export default function AssignmentDetailPage() {
  const { cmid } = useParams();
  const state = useApi<AssignmentDetail>(`/api/assignments/${cmid}`);
  return (
    <div className="page">
      <Loaded state={state} skeleton={<><PageHeader title="Assignment" crumbs={[{ label: "Assignments", to: "/assignments" }]} /><Skeleton rows={6} /></>}>
        {(a) => <AssignmentView a={a} onUpdate={state.setData} />}
      </Loaded>
    </div>
  );
}

function AssignmentView({ a, onUpdate }: { a: AssignmentDetail; onUpdate: (a: AssignmentDetail) => void }) {
  const due = a.extension_due_date || a.due_date;
  return (
    <>
      <PageHeader
        crumbs={[{ label: "My Courses", to: "/courses" }, { label: a.course_code, to: `/courses/${a.course_id}` },
                 { label: "Assignments", to: `/courses/${a.course_id}?tab=assignments` }, { label: a.name }]}
        title={a.name}
        subtitle={<>{a.course_code} · {a.course_title}</>}
      />
      <div className="detail-grid">
        <div className="detail-main">
          <Card title="Assignment details">
            <dl className="fields">
              <Field label="Course">{a.course_code} - {a.course_title}</Field>
              <Field label="Due">{dateTime(due)} {due && <span className="muted">({relative(due)})</span>}</Field>
              {a.extension_due_date && <Field label="Extension">Granted until {dateTime(a.extension_due_date)}</Field>}
              {a.cutoff_date && <Field label="Cut-off">{dateTime(a.cutoff_date)} <span className="muted small">- no submissions accepted after this</span></Field>}
              {a.opens && <Field label="Opened">{dateTime(a.opens)}</Field>}
              <Field label="Maximum grade">{a.max_grade ?? "—"}</Field>
            </dl>
            <h3 className="subhead">Description</h3>
            <p className="prewrap">{a.description || <span className="muted">No description provided in Moodle.</span>}</p>
            {a.attachments.length > 0 && (
              <>
                <h3 className="subhead">Attachments</h3>
                <FileList files={a.attachments} />
              </>
            )}
          </Card>
          <SubmissionForm a={a} onUpdate={onUpdate} />
        </div>
        <aside className="detail-side">
          <StatusCard a={a} />
        </aside>
      </div>
    </>
  );
}

function StatusCard({ a }: { a: AssignmentDetail }) {
  return (
    <Card title="Submission status" className="status-card">
      <div className="status-big"><AssignmentPill state={a.state} late={a.late} /></div>
      <dl className="fields">
        <Field label="Submission status">
          <strong className={a.state === "submitted" ? "text-success" : ""}>
            {a.state === "submitted" ? "SUBMITTED" : a.submission_status === "draft" ? "Draft (not submitted)" : "Not submitted"}
          </strong>
        </Field>
        <Field label="Submitted">{a.submitted_at ? dateTime(a.submitted_at) : "—"}</Field>
        {a.state === "submitted" && (
          <Field label="Timeliness">{a.late ? <span className="text-danger">Late by {duration(a.late_by_seconds)}</span> : <span className="text-success">On time</span>}</Field>
        )}
        <Field label="Grading status">{a.grading_status === "graded" ? "Graded" : a.grading_status === "notgraded" ? "Not graded" : a.grading_status ?? "—"}</Field>
        <Field label="Grade">{a.grade ?? <span className="muted">{a.submitted_at ? "Pending" : "—"}</span>}</Field>
        {a.graded_at && <Field label="Graded on">{dateTime(a.graded_at)}</Field>}
        {a.feedback.length > 0 && <Field label="Feedback">{a.feedback.map((f, i) => <p key={i} className="prewrap">{f}</p>)}</Field>}
      </dl>
      {a.submitted_files.length > 0 && (
        <>
          <h3 className="subhead">Submitted files</h3>
          <FileList files={a.submitted_files} />
        </>
      )}
      {a.submitted_text && (
        <>
          <h3 className="subhead">Online text</h3>
          <p className="prewrap small">{a.submitted_text}</p>
        </>
      )}
    </Card>
  );
}

function FileList({ files }: { files: { filename: string; size?: number | null; url: string | null }[] }) {
  return (
    <ul className="files">
      {files.map((f, i) => (
        <li key={i}>
          <Icon name="file" size={16} />
          {f.url ? <a href={f.url} target="_blank" rel="noopener noreferrer">{f.filename}</a> : <span>{f.filename}</span>}
          {f.size != null && <span className="muted small">{fileSize(f.size)}</span>}
        </li>
      ))}
    </ul>
  );
}

function SubmissionForm({ a, onUpdate }: { a: AssignmentDetail; onUpdate: (a: AssignmentDetail) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [staged, setStaged] = useState(a.staged_files);
  const [text, setText] = useState<string>(a.submitted_text);
  const [busy, setBusy] = useState<"upload" | "submit" | "clear" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (!a.submissions_enabled) return null;
  if (!a.can_edit) {
    const reason = a.state === "closed" ? "The cut-off date has passed; Moodle no longer accepts submissions for this assignment."
      : a.state === "not_open" ? `Submissions open ${dateTime(a.opens)}.`
      : a.locked ? "Your submission is locked." : a.state === "submitted" ? "Your submission has been received and can no longer be changed."
      : "This assignment is not accepting submissions.";
    return (
      <Card title="Submit assignment">
        {done && <div className="banner banner-success"><Icon name="check" /> {done}</div>}
        <p className="muted"><Icon name="lock" size={14} /> {reason}</p>
      </Card>
    );
  }

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setError(null);
    setDone(null);
    setBusy("upload");
    try {
      for (const file of files) {
        if (a.max_bytes && file.size > a.max_bytes) throw new Error(`${file.name} is larger than ${fileSize(a.max_bytes)}.`);
        const form = new FormData();
        form.append("file", file, file.name);
        const r = await api<{ staged_files: { filename: string; size: number }[] }>(`/api/assignments/${a.cmid}/files`, { form });
        setStaged(r.staged_files);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const clear = async () => {
    setBusy("clear");
    try {
      const r = await api<{ staged_files: [] }>(`/api/assignments/${a.cmid}/files`, { method: "DELETE" });
      setStaged(r.staged_files);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const submit = async () => {
    const replacing = a.submitted_files.length > 0 && staged.length > 0;
    const msg = `Submit "${a.name}" for ${a.course_code}?` + (replacing ? "\n\nYour newly uploaded files will replace the files you submitted before." : "")
      + (a.due_date && Date.now() / 1000 > (a.extension_due_date || a.due_date) ? "\n\nThe due date has passed - this will be recorded as a late submission." : "");
    if (!window.confirm(msg)) return;
    setError(null);
    setBusy("submit");
    try {
      const updated = await api<AssignmentDetail>(`/api/assignments/${a.cmid}/submit`, { body: { text: a.online_text ? text : null } });
      setStaged([]);
      setDone(`Submitted to Moodle on ${dateTime(updated.submitted_at)}${updated.late ? " (late)" : ""}.`);
      onUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submission failed. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const canSubmit = staged.length > 0 || (a.online_text && text.trim().length > 0);
  return (
    <Card title={a.submitted_at ? "Edit submission" : "Submit assignment"}>
      {done && <div className="banner banner-success"><Icon name="check" /> {done}</div>}
      {a.state === "overdue" && <div className="banner banner-warning"><Icon name="alert" /> This assignment is overdue. Late submissions are accepted until {dateTime(a.cutoff_date)}.</div>}
      {a.file_submissions && (
        <div className="upload-block">
          <h3 className="subhead">File submission</h3>
          <p className="muted small">
            Up to {a.max_files ?? "several"} file{a.max_files === 1 ? "" : "s"}{a.max_bytes ? `, ${fileSize(a.max_bytes)} each` : ""}
            {a.accepted_types ? ` · Accepted: ${a.accepted_types}` : ""}. Files are stored in Moodle when you click Submit.
          </p>
          <input ref={inputRef} type="file" multiple hidden onChange={upload} />
          <div className="btn-row">
            <button className="btn btn-secondary" onClick={() => inputRef.current?.click()}
                    disabled={busy !== null || (a.max_files != null && staged.length >= a.max_files)}>
              <Icon name="upload" size={16} /> {busy === "upload" ? "Uploading…" : "Upload Assignment"}
            </button>
            {staged.length > 0 && <button className="btn btn-ghost btn-sm" onClick={clear} disabled={busy !== null}>Remove uploaded files</button>}
          </div>
          {staged.length > 0 && (
            <ul className="files staged">
              {staged.map((f) => <li key={f.filename}><Icon name="file" size={16} /><span>{f.filename}</span><span className="muted small">{fileSize(f.size)}</span><Pill tone="info">Ready to submit</Pill></li>)}
            </ul>
          )}
        </div>
      )}
      {a.online_text && (
        <div className="upload-block">
          <label className="subhead" htmlFor="onlinetext">Online text {a.file_submissions && <span className="muted small">(optional)</span>}</label>
          <textarea id="onlinetext" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer here…" />
        </div>
      )}
      {error && <ErrorState error={error} />}
      <div className="btn-row">
        <button className="btn btn-primary" onClick={submit} disabled={busy !== null || !canSubmit}>
          {busy === "submit" ? "Submitting to Moodle…" : "Submit Assignment"}
        </button>
      </div>
    </Card>
  );
}
